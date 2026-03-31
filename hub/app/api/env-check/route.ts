import { NextResponse } from "next/server";
import { readFileSync } from "fs";
import { resolve } from "path";

const ENV_KEYS = [
  "DBT_CLOUD_API_TOKEN",
  "ANTHROPIC_API_KEY",
  "OPENAI_API_KEY",
  "GEMINI_API_KEY",
  "GITHUB_TOKEN",
] as const;

function loadDotenvKeys(): Set<string> {
  const found = new Set<string>();
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
          if (val.length > 0) found.add(key);
        }
      }
    } catch { /* file not found, skip */ }
  }
  return found;
}

export async function GET() {
  const dotenvKeys = loadDotenvKeys();
  const result: Record<string, boolean> = {};
  for (const key of ENV_KEYS) {
    result[key] = Boolean(process.env[key]?.trim()) || dotenvKeys.has(key);
  }
  return NextResponse.json(result);
}
