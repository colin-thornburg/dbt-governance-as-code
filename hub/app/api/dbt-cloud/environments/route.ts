import { NextRequest, NextResponse } from "next/server";
import { readFileSync } from "fs";
import { resolve } from "path";

function loadToken(): string | null {
  const fromEnv = process.env.DBT_CLOUD_API_TOKEN?.trim();
  if (fromEnv) return fromEnv;
  const candidates = [
    resolve(process.cwd(), ".env"),
    resolve(process.cwd(), "..", ".env"),
  ];
  for (const p of candidates) {
    try {
      const content = readFileSync(p, "utf8");
      for (const line of content.split("\n")) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith("#")) continue;
        const eqIdx = trimmed.indexOf("=");
        if (eqIdx > 0) {
          const key = trimmed.slice(0, eqIdx).trim();
          const val = trimmed.slice(eqIdx + 1).trim();
          const stripped = val.replace(/^["']|["']$/g, "");
          if (key === "DBT_CLOUD_API_TOKEN" && stripped) return stripped;
        }
      }
    } catch { /* file not found */ }
  }
  return null;
}

async function cloudGet(url: string, token: string): Promise<Record<string, unknown>> {
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
  });
  if (!res.ok) {
    throw new Error(`dbt Cloud API returned ${res.status} for ${url}. Check your Account ID and token permissions.`);
  }
  return res.json() as Promise<Record<string, unknown>>;
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const accountId = searchParams.get("account_id");
  const apiBaseUrl = (searchParams.get("api_base_url") || "https://cloud.getdbt.com").replace(/\/$/, "");

  if (!accountId || accountId === "0") {
    return NextResponse.json({ error: "account_id is required" }, { status: 400 });
  }

  const token = loadToken();
  if (!token) {
    return NextResponse.json(
      { error: "DBT_CLOUD_API_TOKEN not found in environment or .env file" },
      { status: 401 }
    );
  }

  const base = `${apiBaseUrl}/api/v3/accounts/${accountId}`;

  try {
    // Fetch environments and projects in parallel
    const [envData, projData] = await Promise.all([
      cloudGet(`${base}/environments/`, token),
      cloudGet(`${base}/projects/`, token),
    ]);

    // Build a project_id → project_name lookup
    const projectNames = new Map<number, string>(
      ((projData["data"] ?? []) as Record<string, unknown>[]).map((p) => [
        p["id"] as number,
        (p["name"] as string) ?? `Project ${p["id"]}`,
      ])
    );

    const environments = ((envData["data"] ?? []) as Record<string, unknown>[]).map((env) => {
      const projectId = env["project_id"] as number;
      // dbt Cloud uses "type" = "deployment" | "development" and sometimes
      // "deployment_type" for more detail (e.g. "production", "staging").
      const rawType = (env["type"] as string | undefined) ?? "";
      const deploymentType = (env["deployment_type"] as string | undefined) ?? "";
      // Prefer the more specific deployment_type if present
      const displayType = deploymentType || rawType || "deployment";

      return {
        id: env["id"] as number,
        name: (env["name"] as string) ?? `Environment ${env["id"]}`,
        project_id: projectId,
        project_name: projectNames.get(projectId) ?? `Project ${projectId}`,
        type: displayType,
      };
    });

    // Sort: deployment envs first, then by project name, then env name
    environments.sort((a, b) => {
      const aDeploy = a.type !== "development" ? 0 : 1;
      const bDeploy = b.type !== "development" ? 0 : 1;
      if (aDeploy !== bDeploy) return aDeploy - bDeploy;
      const proj = a.project_name.localeCompare(b.project_name);
      if (proj !== 0) return proj;
      return a.name.localeCompare(b.name);
    });

    return NextResponse.json({ environments });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to reach dbt Cloud API" },
      { status: 500 }
    );
  }
}
