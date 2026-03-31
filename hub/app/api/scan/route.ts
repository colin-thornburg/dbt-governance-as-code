import { NextRequest, NextResponse } from "next/server";
import { execFile } from "child_process";
import { writeFile, unlink, readFile } from "fs/promises";
import { tmpdir } from "os";
import { join, resolve } from "path";
import { promisify } from "util";

const execFileAsync = promisify(execFile);

export async function POST(request: NextRequest) {
  const body = await request.json();
  const { configYaml, mode, manifestPath, withAi } = body as {
    configYaml: string;
    mode: "cloud" | "local";
    manifestPath?: string;
    withAi?: boolean;
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
    } else {
      args.push("--cloud");
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
            const val = trimmed.slice(eqIdx + 1).trim();
            if (val && !env[key]) env[key] = val;
          }
        }
      } catch { /* file not found */ }
    }

    let stdout = "";
    let exitCode = 0;

    try {
      const result = await execFileAsync("dbt-governance", args, {
        env,
        cwd: projectRoot,
        timeout: 120_000,
        maxBuffer: 10 * 1024 * 1024,
      });
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
        const msg = err.stderr ?? err.message ?? "";
        if (msg.includes("command not found") || err.code === "ENOENT") {
          return NextResponse.json({
            success: false,
            error:
              "dbt-governance is not installed or not in PATH.\n\nFix: pip install dbt-governance",
          });
        }
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
