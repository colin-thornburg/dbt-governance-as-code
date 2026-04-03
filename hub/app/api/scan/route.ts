import { NextRequest, NextResponse } from "next/server";
import { execFile } from "child_process";
import { writeFile, unlink, readFile, access } from "fs/promises";
import { tmpdir } from "os";
import { join, resolve } from "path";
import { promisify } from "util";

const execFileAsync = promisify(execFile);

/** Find the dbt-governance binary, preferring the local .venv over PATH. */
async function findDbtGovernance(projectRoot: string): Promise<string | null> {
  // 1. Local .venv created by uv (most reliable for this monorepo)
  const venvBin =
    process.platform === "win32"
      ? join(projectRoot, ".venv", "Scripts", "dbt-governance.exe")
      : join(projectRoot, ".venv", "bin", "dbt-governance");
  try {
    await access(venvBin);
    return venvBin;
  } catch { /* not present */ }

  // 2. System / activated-venv PATH
  try {
    await execFileAsync("dbt-governance", ["--version"], { timeout: 5_000 });
    return "dbt-governance";
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code !== "ENOENT") return "dbt-governance";
  }

  return null;
}

/** Best-effort install of dbt-governance into the current Python environment. */
async function autoInstall(projectRoot: string): Promise<boolean> {
  // Try uv sync with all extras (re-installs from pyproject.toml, works in this monorepo)
  try {
    await execFileAsync("uv", ["sync", "--extra", "ai", "--extra", "openai", "--extra", "gemini"], {
      cwd: projectRoot,
      timeout: 120_000,
    });
    return true;
  } catch { /* uv not found or failed */ }

  // Try uv pip install with all extras
  try {
    await execFileAsync("uv", ["pip", "install", "dbt-governance[ai,openai,gemini]"], {
      cwd: projectRoot,
      timeout: 120_000,
    });
    return true;
  } catch { /* uv not found */ }

  // Try python / python3 -m pip (more reliable than bare pip/pip3)
  for (const py of ["python", "python3"]) {
    try {
      await execFileAsync(py, ["-m", "pip", "install", "dbt-governance[ai,openai,gemini]"], { timeout: 120_000 });
      return true;
    } catch { /* try next */ }
  }

  // Last resort: bare pip / pip3
  for (const pip of ["pip", "pip3"]) {
    try {
      await execFileAsync(pip, ["install", "dbt-governance[ai,openai,gemini]"], { timeout: 120_000 });
      return true;
    } catch { /* try next */ }
  }

  return false;
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const { configYaml, mode, manifestPath, projectDir, withAi, ruleCategories } = body as {
    configYaml: string;
    mode: "cloud" | "local";
    manifestPath?: string;
    projectDir?: string;
    withAi?: boolean;
    ruleCategories?: string[];
  };

  const tempConfigPath = join(tmpdir(), `dbt-governance-${Date.now()}.yml`);

  try {
    await writeFile(tempConfigPath, configYaml, "utf8");

    const args = ["scan", "--config", tempConfigPath, "--output", "json"];

    if (mode === "local") {
      args.push("--local");
      if (manifestPath) {
        args.push("--manifest", manifestPath);
      }
      if (projectDir) {
        args.push("--project-dir", projectDir);
      }
    } else {
      args.push("--cloud");
    }

    if (ruleCategories && ruleCategories.length > 0) {
      args.push("--rules", ruleCategories.join(","));
    }

    if (withAi) {
      args.push("--with-ai");
    }

    const projectRoot = resolve(process.cwd(), "..");
    const env = { ...process.env };
    for (const candidate of [resolve(projectRoot, ".env"), resolve(process.cwd(), ".env")]) {
      try {
        const content = await readFile(candidate, "utf8");
        for (const line of content.split("\n")) {
          const trimmed = line.trim();
          if (!trimmed || trimmed.startsWith("#")) continue;
          const eqIdx = trimmed.indexOf("=");
          if (eqIdx > 0) {
            const key = trimmed.slice(0, eqIdx).trim();
            const val = trimmed.slice(eqIdx + 1).trim().replace(/^["']|["']$/g, "");
            if (val && !env[key]) env[key] = val;
          }
        }
      } catch { /* file not found */ }
    }

    const execOpts = {
      env,
      cwd: projectRoot,
      timeout: 120_000,
      maxBuffer: 10 * 1024 * 1024,
    };

    let stdout = "";
    let exitCode = 0;

    // Resolve the binary path (checks .venv before PATH)
    let bin = await findDbtGovernance(projectRoot);

    if (!bin) {
      // Not found anywhere — try to install, then look again
      await autoInstall(projectRoot);
      bin = await findDbtGovernance(projectRoot);
    }

    if (!bin) {
      return NextResponse.json({
        success: false,
        error:
          "dbt-governance could not be found or installed automatically.\n\nFix: pip install dbt-governance",
      });
    }

    try {
      const result = await execFileAsync(bin, args, execOpts);
      stdout = result.stdout;
    } catch (execError: unknown) {
      const err = execError as NodeJS.ErrnoException & {
        stdout?: string;
        stderr?: string;
        code?: number | string;
      };
      exitCode = typeof err.code === "number" ? err.code : 1;
      stdout = err.stdout ?? "";
      if (!stdout) {
        return NextResponse.json({
          success: false,
          error: err.stderr ?? err.message ?? "Unknown error",
        });
      }
    }

    try {
      const parsed = JSON.parse(stdout);
      return NextResponse.json({ success: true, result: parsed, exitCode });
    } catch {
      return NextResponse.json({
        success: false,
        error:
          "Scanner ran but did not return JSON. Make sure dbt-governance >= 0.1.0 is installed.",
        raw: stdout.slice(0, 2000),
      });
    }
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ success: false, error: message });
  } finally {
    await unlink(tempConfigPath).catch(() => {});
  }
}
