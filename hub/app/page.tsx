"use client";

import { useMemo, useState, useEffect, useRef } from "react";
import {
  categoryDefinitions,
  type CategoryKey,
  cloneConfig,
  countEnabledRules,
  defaultGovernanceConfig,
  generateClaudeMd,
  generateReviewMd,
  generateYaml,
  isCloudConfigured,
  severityBreakdown,
  type AiProvider,
  type GovernanceConfig,
  type RuleConfig,
  type Severity
} from "../lib/governance";

// ─── Types ───────────────────────────────────────────────────────────────────

type PreviewMode = "yaml" | "review" | "claude";
type WorkspaceTab = CategoryKey | "artifacts" | "run";
type ScanScope = "single" | "all";

const severityOptions: Severity[] = ["error", "warning", "info"];
const aiProviderOptions: { value: AiProvider; label: string }[] = [
  { value: "claude", label: "Claude (Anthropic)" },
  { value: "openai", label: "OpenAI" },
  { value: "gemini", label: "Google (Gemini)" },
  { value: "none", label: "None — disable AI review" }
];

const claudeModels: Array<{ value: string; label: string }> = [
  { value: "claude-sonnet-4-6", label: "Sonnet 4.6" },
  { value: "claude-opus-4-6", label: "Opus 4.6" },
  { value: "claude-haiku-4-5-20251001", label: "Haiku 4.5" },
];
const openaiModels: Array<{ value: string; label: string }> = [
  { value: "gpt-4o", label: "GPT-4o" },
  { value: "gpt-4o-mini", label: "GPT-4o mini" },
  { value: "gpt-4-turbo", label: "GPT-4 Turbo" },
];
const geminiModels: Array<{ value: string; label: string }> = [
  { value: "gemini-3.1-pro-preview", label: "Gemini 3.1 Pro" },
  { value: "gemini-3-flash-preview", label: "Gemini 3 Flash" },
  { value: "gemini-2.5-pro", label: "Gemini 2.5 Pro" },
  { value: "gemini-2.5-flash", label: "Gemini 2.5 Flash" },
];

const workspaceTabs: Array<{ key: WorkspaceTab; label: string; group?: string }> = [
  ...categoryDefinitions.map((category) => ({
    key: category.key,
    label: category.title.replace(" Rules", ""),
    group: category.key === "migration" || category.key === "reuse" ? "migration" : "standard"
  })),
  { key: "artifacts", label: "Artifacts" },
  { key: "run", label: "Run Scan" }
];

// ─── Explainer content ───────────────────────────────────────────────────────

const explainerSteps = [
  {
    title: "1. Configure your standards",
    body: "Use the rule categories to choose what to enforce — naming patterns, DAG structure, test coverage, SQL style, and legacy migration checks. Every rule has a default that works immediately."
  },
  {
    title: "2. Download three files",
    body: "Hit Download to get your `.dbt-governance.yml`, `REVIEW.md`, and `CLAUDE.md`. Commit all three to the root of your dbt repository."
  },
  {
    title: "3. CI catches violations automatically",
    body: "On every PR, `dbt-governance scan` reads your config and checks every changed model. Violations appear as inline annotations and can fail the CI check."
  },
  {
    title: "4. Claude Code Review adds semantic judgment",
    body: "Because `REVIEW.md` and `CLAUDE.md` are committed, Claude Code Review reads them on every PR and leaves inline comments for things a static scanner misses."
  }
];

const ecosystemTools = [
  {
    name: "dbt_project_evaluator",
    by: "dbt Labs",
    tagline: "The official dbt Labs governance framework — excellent for warehouse-backed audits",
    strengths: "Comprehensive DAG structure analysis using dbt models themselves. Deeply integrated with dbt metadata. The right tool for periodic, thorough audits when you have a live warehouse and want results expressed as dbt models you can query.",
    limitation: "Requires a full dbt run against a live warehouse — can't run pre-merge in CI. Rules live as SQL models inside dbt itself, making custom rules complex to add.",
    gap: "Central Governance runs via the dbt Cloud Discovery API or manifest.json — no warehouse required, runs in ~60s on every PR. Use dbt_project_evaluator for deep periodic audits; use Central Governance for pre-merge enforcement."
  },
  {
    name: "SQLFluff",
    by: "Open source",
    tagline: "The gold standard for SQL syntax and style linting — use it alongside this tool",
    strengths: "Exceptional at SQL syntax linting and consistent style enforcement. Handles Jinja and dbt templating beautifully. Highly configurable. The right tool for enforcing SELECT formatting, alias style, comma placement, and keyword casing across your whole project.",
    limitation: "Purely syntactic — knows nothing about model layering, DAG structure, test coverage, source definitions, or legacy migration anti-patterns. Cannot detect a staging model querying a mart, or a migrated Talend job with hardcoded schemas.",
    gap: "Central Governance handles architectural and semantic rules that SQLFluff cannot see: DAG integrity, test coverage, legacy anti-patterns, re-use detection. Run both in CI for full coverage — they don't overlap."
  },
  {
    name: "dbt Cloud recommendations",
    by: "dbt Labs (built-in)",
    tagline: "Advisory guidance inside dbt Cloud Explorer — great for individual developer awareness",
    strengths: "Zero setup — surfaced directly in dbt Cloud Explorer as developers browse models. Good for raising developer awareness of documentation and test gaps in real time without any CI configuration.",
    limitation: "Advisory only, not enforceable policy. Lives in the dbt Cloud UI; cannot fail a CI check, cannot be versioned in git, and cannot be applied consistently as a single shared standard across all projects in an account.",
    gap: "Central Governance turns the same intent into enforceable, version-controlled policy that fails PRs automatically. One configuration, distributed to every project in your account."
  },
  {
    name: "Great Expectations / Soda",
    by: "Data quality testing",
    tagline: "Runtime data quality validation — validates what's actually in your tables",
    strengths: "The right tools for validating actual data values in production: row counts, nullability, referential integrity, value ranges, freshness. Catches bad data after it has been loaded — an essential quality layer.",
    limitation: "Test data at runtime, not model structure before merge. Cannot enforce naming conventions, DAG patterns, SQL style, or detect legacy migration anti-patterns in code.",
    gap: "Central Governance enforces code-level standards pre-merge. Entirely complementary layers — use both. Central Governance prevents bad models from merging; Great Expectations / Soda catches bad data after models run."
  }
];

const operationalAnswers = [
  {
    question: "What exactly is `.dbt-governance.yml`?",
    answer:
      "A YAML file that lives in the root of your dbt repo. It declares which rules are active, their severities, and thresholds. The `dbt-governance` CLI reads it to know what to enforce."
  },
  {
    question: "What does a developer see on a PR?",
    answer:
      "A CI check posts inline annotations on the PR diff. Claude Code Review reads REVIEW.md and leaves additional comments for issues that need judgment."
  },
  {
    question: "Does it need a warehouse or a full dbt run?",
    answer:
      "No. It queries the dbt Cloud Discovery API or reads a local manifest.json — never connects to your warehouse. Runs on every PR, including ones not yet deployed."
  },
  {
    question: "Can we apply this to an existing dbt project?",
    answer:
      "Yes — this is the primary use case. You'll immediately see a governance score and a list of violations to work through, including any legacy migration debt."
  }
];

const exampleFlow = [
  {
    step: "A developer opens a PR adding a new staging model named `payments.sql`",
    detail:
      "The file is in models/staging/stripe/ but the team standard requires stg_<source>__<entity> naming. The developer may not have known this rule existed."
  },
  {
    step: "CI runs `dbt-governance scan` in under 30 seconds",
    detail:
      "The scanner finds the naming violation and posts an inline annotation: \"ERROR [naming.staging_prefix] — rename to stg_stripe__payments.sql\". The CI check fails, blocking merge."
  },
  {
    step: "Claude Code Review adds a contextual comment",
    detail:
      "Claude also notices the model contains a CASE WHEN that categorises payment types — business logic that belongs in an intermediate model. It leaves an inline comment explaining why and suggesting where to move it."
  },
  {
    step: "The developer fixes both issues and the PR merges clean",
    detail:
      "No Slack back-and-forth, no delayed code review. The governance policy enforced itself — the same way for every developer across every project that uses this config."
  }
];

// ─── Scan types ───────────────────────────────────────────────────────────────

interface ScanViolation {
  rule_id: string;
  severity: "error" | "warning" | "info";
  model_name: string;
  file_path: string;
  line_number: number | null;
  message: string;
  suggestion: string | null;
  ai_generated?: boolean;
}

interface ScanResult {
  scan_id: string;
  timestamp: string;
  project: string;
  summary: {
    models_scanned: number;
    rules_evaluated: number;
    errors: number;
    warnings: number;
    info: number;
    score: number;
  };
  violations: ScanViolation[];
}

// ─── Component ───────────────────────────────────────────────────────────────

export default function Home() {
  const [config, setConfig] = useState<GovernanceConfig>(cloneConfig(defaultGovernanceConfig));
  const [previewMode, setPreviewMode] = useState<PreviewMode>("yaml");
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("naming");
  const [copiedLabel, setCopiedLabel] = useState<string>("");
  const [copiedCommand, setCopiedCommand] = useState<string>("");
  const [showExplainer, setShowExplainer] = useState<boolean>(false);
  const [explainerTab, setExplainerTab] = useState<"flow" | "setup" | "experience" | "faq">("flow");
  const [showSettings, setShowSettings] = useState<boolean>(false);

  // Scan runner state
  const [scanMode, setScanMode] = useState<"cloud" | "local">("cloud");
  const [scanScope, setScanScope] = useState<ScanScope>("single");
  const [manifestPath, setManifestPath] = useState("target/manifest.json");
  const [withAiScan, setWithAiScan] = useState(false);
  const [isScanning, setIsScanning] = useState(false);
  const [scanResult, setScanResult] = useState<ScanResult | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);

  // Project name inline editing
  const nameRef = useRef<HTMLInputElement>(null);

  const isDownloadReady = config.project.name.trim().length > 0;
  const cloudConfigured = isCloudConfigured(config);

  const enabledRuleCount = useMemo(() => countEnabledRules(config), [config]);
  const severities = useMemo(() => severityBreakdown(config), [config]);
  const yamlPreview = useMemo(() => generateYaml(config), [config]);
  const reviewPreview = useMemo(() => generateReviewMd(config), [config]);
  const claudePreview = useMemo(() => generateClaudeMd(config), [config]);

  // Close drawer/modal on Escape
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setShowSettings(false);
        setShowExplainer(false);
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);

  function updateConfig(updater: (current: GovernanceConfig) => void) {
    setConfig((current) => {
      const next = cloneConfig(current);
      updater(next);
      return next;
    });
  }

  function updateRule(categoryKey: CategoryKey, ruleKey: string, updater: (rule: RuleConfig) => void) {
    updateConfig((next) => {
      const category = next[categoryKey];
      if (!category || typeof category !== "object" || !("rules" in category)) return;
      updater((category.rules as Record<string, RuleConfig>)[ruleKey]);
    });
  }

  function previewContent(): string {
    if (previewMode === "review") return reviewPreview;
    if (previewMode === "claude") return claudePreview;
    return yamlPreview;
  }

  async function copyPreview() {
    await navigator.clipboard.writeText(previewContent());
    setCopiedLabel(`${previewMode.toUpperCase()} copied`);
    window.setTimeout(() => setCopiedLabel(""), 1500);
  }

  async function copyCommand(text: string, key: string) {
    await navigator.clipboard.writeText(text);
    setCopiedCommand(key);
    window.setTimeout(() => setCopiedCommand(""), 1500);
  }

  async function runScan() {
    setIsScanning(true);
    setScanResult(null);
    setScanError(null);
    try {
      const response = await fetch("/api/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          configYaml: yamlPreview,
          mode: scanMode,
          manifestPath: scanMode === "local" ? manifestPath : undefined,
          withAi: withAiScan
        })
      });
      const data = await response.json();
      if (data.success) {
        setScanResult(data.result as ScanResult);
      } else {
        setScanError(data.error ?? "Scan failed");
      }
    } catch (err: unknown) {
      setScanError(err instanceof Error ? err.message : "Network error");
    } finally {
      setIsScanning(false);
    }
  }

  function scoreLabel(score: number): string {
    if (score >= 90) return "Excellent";
    if (score >= 75) return "Good";
    if (score >= 60) return "Needs Work";
    return "Failing";
  }

  function scoreClass(score: number): string {
    if (score >= 90) return "score-excellent";
    if (score >= 75) return "score-good";
    if (score >= 60) return "score-warn";
    return "score-fail";
  }

  function downloadFile(filename: string, content: string) {
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  }

  function modelsForProvider(provider: AiProvider): Array<{ value: string; label: string }> {
    if (provider === "claude") return claudeModels;
    if (provider === "openai") return openaiModels;
    if (provider === "gemini") return geminiModels;
    return [];
  }

  const activeCategory = categoryDefinitions.find((c) => c.key === activeTab);

  // Tab focus description for the status panel
  const tabFocus =
    activeTab === "artifacts"
      ? "Generate exportable artifacts"
      : activeTab === "run"
        ? "Run the scanner"
        : `Tune ${activeCategory?.title ?? "rules"}`;

  // Migration tab hint — shown when there are migration/reuse categories
  const isMigrationTab = activeTab === "migration" || activeTab === "reuse";

  return (
    <main className="shell">
      <div className="backdrop backdrop-one" />
      <div className="backdrop backdrop-two" />

      {/* ─────────────────── Hero ─────────────────── */}
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">Central Governance Console</p>
          <h1>Design governance once. Export it everywhere.</h1>
          <p className="lede">
            Configure dbt standards in one place — naming, structure, testing, SQL style, and legacy migration
            debt — then export the exact YAML and review artifacts your whole team enforces.
          </p>
        </div>

        <div className="hero-panel">
          <div className="metric">
            <span>Enabled rules</span>
            <strong>{enabledRuleCount}</strong>
          </div>
          <div className="metric">
            <span>Error rules</span>
            <strong>{severities.error}</strong>
          </div>
          <div className="metric">
            <span>Warning rules</span>
            <strong>{severities.warning}</strong>
          </div>
          <div className="metric">
            <span>Info rules</span>
            <strong>{severities.info}</strong>
          </div>
        </div>
      </section>

      {/* ─────────────────── Workspace ─────────────────── */}
      <section className="workspace">

        {/* ── Left nav ── */}
        <aside className="workspace-nav panel">

          {/* Project identity strip */}
          <div className="identity-strip">
            <input
              ref={nameRef}
              className="identity-name"
              value={config.project.name}
              onChange={(e) => updateConfig((next) => { next.project.name = e.target.value; })}
              placeholder="Project name…"
              aria-label="Project name"
            />
            <textarea
              className="identity-desc"
              rows={2}
              value={config.project.description}
              onChange={(e) => updateConfig((next) => { next.project.description = e.target.value; })}
              placeholder="Short description…"
            />
          </div>

          {/* Settings button + connection status */}
          <div className="nav-actions">
            <button
              className="settings-trigger"
              onClick={() => setShowSettings(true)}
              title="Connection, AI provider, and scan defaults"
            >
              <span className="settings-icon">⚙</span>
              Settings
              <span className={`conn-dot ${cloudConfigured ? "conn-ok" : "conn-off"}`} />
            </button>
            <button className="ghost-button small" onClick={() => setShowExplainer(true)}>
              How it works
            </button>
          </div>

          {/* Rule category tabs */}
          <div className="tab-list">
            <p className="tab-group-label">Rule Categories</p>
            {workspaceTabs
              .filter((t) => t.group === "standard")
              .map((tab) => (
                <button
                  key={tab.key}
                  className={tab.key === activeTab ? "tab-button active" : "tab-button"}
                  onClick={() => setActiveTab(tab.key)}
                >
                  <strong>{tab.label}</strong>
                </button>
              ))}

            <p className="tab-group-label migration-label">Migration &amp; Re-use</p>
            {workspaceTabs
              .filter((t) => t.group === "migration")
              .map((tab) => (
                <button
                  key={tab.key}
                  className={
                    tab.key === activeTab
                      ? "tab-button active migration-tab"
                      : "tab-button migration-tab"
                  }
                  onClick={() => setActiveTab(tab.key)}
                >
                  <strong>{tab.label}</strong>
                </button>
              ))}

            <p className="tab-group-label">Output</p>
            {workspaceTabs
              .filter((t) => !t.group)
              .map((tab) => (
                <button
                  key={tab.key}
                  className={tab.key === activeTab ? "tab-button active" : "tab-button"}
                  onClick={() => setActiveTab(tab.key)}
                >
                  <strong>{tab.label}</strong>
                </button>
              ))}
          </div>
        </aside>

        {/* ── Main workspace ── */}
        <div className="workspace-main">

          {/* Rule category panel */}
          {activeCategory && (
            <section className={`panel category-panel${isMigrationTab ? " migration-panel" : ""}`}>
              {isMigrationTab && (
                <div className="migration-banner">
                  <strong>
                    {activeTab === "migration"
                      ? "Legacy Migration Report"
                      : "Re-use Opportunities"}
                  </strong>
                  <p>
                    {activeTab === "migration"
                      ? "These rules surface technical debt carried in from Talend, Informatica, SSIS, and other ETL tools. Every violation includes a specific remediation step — hand this report to a team and they know exactly what to fix."
                      : "These rules detect where independent pipelines are doing the same work. The output is a consolidation roadmap — which models to merge and what the shared intermediate should look like."}
                  </p>
                </div>
              )}

              <div className="panel-header">
                <div>
                  <p className="panel-kicker" style={{ color: activeCategory.accent }}>
                    {activeCategory.title}
                  </p>
                  <h2>{activeCategory.description}</h2>
                </div>
                <label className="switch">
                  <span>Category enabled</span>
                  <input
                    type="checkbox"
                    checked={config[activeCategory.key].enabled}
                    onChange={(e) =>
                      updateConfig((next) => { next[activeCategory.key].enabled = e.target.checked; })
                    }
                  />
                </label>
              </div>

              <div className="rule-list">
                {activeCategory.rules.map((rule) => {
                  const ruleState = config[activeCategory.key].rules[rule.key];
                  return (
                    <article className="rule-card" key={rule.key}>
                      <div className="rule-topline">
                        <label className="rule-checkbox">
                          <input
                            type="checkbox"
                            checked={ruleState.enabled}
                            onChange={(e) =>
                              updateRule(activeCategory.key, rule.key, (current) => {
                                current.enabled = e.target.checked;
                              })
                            }
                          />
                          <div>
                            <strong>{rule.label}</strong>
                            <p>{rule.helper}</p>
                          </div>
                        </label>

                        <select
                          value={ruleState.severity}
                          onChange={(e) =>
                            updateRule(activeCategory.key, rule.key, (current) => {
                              current.severity = e.target.value as Severity;
                            })
                          }
                        >
                          {severityOptions.map((s) => (
                            <option key={s} value={s}>{s}</option>
                          ))}
                        </select>
                      </div>

                      {rule.fields && (
                        <div className="rule-fields">
                          {rule.fields.map((field) => (
                            <label key={field.key}>
                              <span>{field.label}</span>
                              {field.type === "number" ? (
                                <input
                                  type="number"
                                  value={String(ruleState[field.key] ?? "")}
                                  onChange={(e) =>
                                    updateRule(activeCategory.key, rule.key, (current) => {
                                      current[field.key] = Number(e.target.value);
                                    })
                                  }
                                />
                              ) : (
                                <input
                                  value={
                                    field.type === "list"
                                      ? ((ruleState[field.key] as string[]) ?? []).join(", ")
                                      : String(ruleState[field.key] ?? "")
                                  }
                                  onChange={(e) =>
                                    updateRule(activeCategory.key, rule.key, (current) => {
                                      current[field.key] =
                                        field.type === "list"
                                          ? e.target.value.split(",").map((s) => s.trim()).filter(Boolean)
                                          : e.target.value;
                                    })
                                  }
                                />
                              )}
                            </label>
                          ))}
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            </section>
          )}

          {/* Artifacts panel */}
          {activeTab === "artifacts" && (
            <div className="panel sticky-panel">
              <div className="panel-header compact">
                <div>
                  <p className="panel-kicker">Generated Artifacts</p>
                  <h2>Live previews and downloads</h2>
                </div>
                <div className="chip-row">
                  {(["yaml", "review", "claude"] as PreviewMode[]).map((mode) => (
                    <button
                      key={mode}
                      className={mode === previewMode ? "chip active" : "chip"}
                      onClick={() => setPreviewMode(mode)}
                    >
                      {mode === "yaml" ? ".dbt-governance.yml" : mode === "review" ? "REVIEW.md" : "CLAUDE.md"}
                    </button>
                  ))}
                </div>
              </div>

              <div className="action-row">
                <button className="primary-button" onClick={() => downloadFile(".dbt-governance.yml", yamlPreview)}>
                  Download YAML
                </button>
                <button className="primary-button secondary" onClick={() => downloadFile("REVIEW.md", reviewPreview)}>
                  Download REVIEW.md
                </button>
                <button className="primary-button secondary" onClick={() => downloadFile("CLAUDE.md", claudePreview)}>
                  Download CLAUDE.md
                </button>
                <button className="ghost-button" onClick={copyPreview}>
                  {copiedLabel || "Copy active preview"}
                </button>
              </div>

              <div className="preview-frame">
                <pre>{previewContent()}</pre>
              </div>
            </div>
          )}

          {/* Run Scan panel */}
          {activeTab === "run" && (
            <div className="panel run-panel">
              <div className="panel-header">
                <div>
                  <p className="panel-kicker">Run Scan</p>
                  <h2>Run the scanner against your dbt project</h2>
                </div>
              </div>

              {/* Scan scope toggle */}
              <div className="scan-scope-row">
                <p className="scan-scope-label">Scan scope</p>
                <div className="mode-toggle">
                  <button
                    className={scanScope === "single" ? "mode-btn active" : "mode-btn"}
                    onClick={() => setScanScope("single")}
                  >
                    This project
                  </button>
                  <button
                    className={scanScope === "all" ? "mode-btn active" : "mode-btn"}
                    onClick={() => setScanScope("all")}
                  >
                    All projects in account
                  </button>
                </div>
              </div>

              {/* Single project scan */}
              {scanScope === "single" && (
                <div className="scan-launcher">
                  <p className="panel-kicker">Run from this UI</p>
                  <p className="run-intro">
                    Runs <code className="inline-code">dbt-governance scan</code> on your server.
                    Requires <code className="inline-code">dbt-governance</code> installed in the same Python
                    environment as this app.
                  </p>

                  <div className="scan-controls">
                    <div className="mode-toggle">
                      <button
                        className={scanMode === "cloud" ? "mode-btn active" : "mode-btn"}
                        onClick={() => setScanMode("cloud")}
                      >
                        Cloud mode
                      </button>
                      <button
                        className={scanMode === "local" ? "mode-btn active" : "mode-btn"}
                        onClick={() => setScanMode("local")}
                      >
                        Local mode
                      </button>
                    </div>

                    {scanMode === "local" && (
                      <label className="scan-field">
                        <span>Path to manifest.json</span>
                        <input
                          value={manifestPath}
                          onChange={(e) => setManifestPath(e.target.value)}
                          placeholder="target/manifest.json"
                        />
                      </label>
                    )}

                    {scanMode === "cloud" && (
                      <p className="scan-hint">
                        {cloudConfigured ? (
                          <>
                            Scans environment <strong>{config.dbt_cloud.environment_id}</strong> in account{" "}
                            <strong>{config.dbt_cloud.account_id}</strong>.
                          </>
                        ) : (
                          <>
                            <span className="warn-inline">⚠ dbt Cloud not configured.</span>{" "}
                            Open <button className="inline-link" onClick={() => setShowSettings(true)}>Settings</button>{" "}
                            to enter your Account ID and Environment ID.
                          </>
                        )}
                      </p>
                    )}

                    <label className="scan-ai-toggle">
                      <input
                        type="checkbox"
                        checked={withAiScan}
                        onChange={(e) => setWithAiScan(e.target.checked)}
                      />
                      <span>
                        Enable AI review{" "}
                        <span className="scan-hint-inline">
                          (requires API key for selected provider)
                        </span>
                      </span>
                    </label>

                    <button
                      className="primary-button scan-run-btn"
                      onClick={runScan}
                      disabled={isScanning || !isDownloadReady || (scanMode === "cloud" && !cloudConfigured)}
                    >
                      {isScanning ? <span className="scan-spinner">Scanning…</span> : "Run Scan →"}
                    </button>
                  </div>

                  {scanError && (
                    <div className="scan-error">
                      <strong>Scan failed</strong>
                      <pre>{scanError}</pre>
                    </div>
                  )}

                  {scanResult && (
                    <div className="scan-results">
                      <div className="scan-score-row">
                        <div className={`scan-score ${scoreClass(scanResult.summary.score)}`}>
                          <span className="score-num">{scanResult.summary.score}</span>
                          <span className="score-denom">/100</span>
                          <span className="score-label">{scoreLabel(scanResult.summary.score)}</span>
                        </div>
                        <div className="scan-meta">
                          <div className="scan-counts">
                            <span className="count-badge sev-error">{scanResult.summary.errors} errors</span>
                            <span className="count-badge sev-warning">{scanResult.summary.warnings} warnings</span>
                            <span className="count-badge sev-info">{scanResult.summary.info} info</span>
                          </div>
                          <p className="scan-meta-line">
                            {scanResult.summary.models_scanned} models · {scanResult.summary.rules_evaluated} rules ·{" "}
                            {new Date(scanResult.timestamp).toLocaleTimeString()}
                          </p>
                        </div>
                      </div>

                      {scanResult.violations.length === 0 ? (
                        <div className="scan-clean">All rules passed — no violations found.</div>
                      ) : (
                        <div className="violations-list">
                          {scanResult.violations.map((v, i) => (
                            <div key={i} className={`violation-row vrow-${v.severity}`}>
                              <div className="violation-top">
                                <span className={`sev-badge sev-${v.severity}`}>{v.severity}</span>
                                <code className="violation-rule">{v.rule_id}</code>
                                <span className="violation-model">{v.model_name}</span>
                              </div>
                              <p className="violation-msg">{v.message}</p>
                              {v.suggestion && <p className="violation-suggestion">→ {v.suggestion}</p>}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* All projects scan */}
              {scanScope === "all" && (
                <div className="all-projects-pane">
                  <div className="all-projects-header">
                    <p className="run-intro">
                      Scan every environment in account{" "}
                      <strong>{config.dbt_cloud.account_id > 0 ? config.dbt_cloud.account_id : "—"}</strong>.
                      The scanner runs sequentially and produces a governance score for each project,
                      letting you see your entire dbt Cloud account's health in one pass.
                    </p>
                    {!cloudConfigured && (
                      <div className="scan-hint warn-card">
                        <strong>Account not configured.</strong>{" "}
                        <button className="inline-link" onClick={() => setShowSettings(true)}>
                          Open Settings
                        </button>{" "}
                        to enter your dbt Cloud account ID and API token.
                      </div>
                    )}
                  </div>

                  {/* Preview of what the output looks like */}
                  <div className="projects-table-wrap">
                    <p className="panel-kicker">Example output — governance scores across all environments</p>
                    <table className="projects-table">
                      <thead>
                        <tr>
                          <th>Environment</th>
                          <th>Project</th>
                          <th>Models</th>
                          <th>Score</th>
                          <th>Errors</th>
                          <th>Warnings</th>
                          <th>Migration debt</th>
                        </tr>
                      </thead>
                      <tbody>
                        {[
                          { env: "Production", project: "acme_core", models: 147, score: 84, errors: 3, warnings: 12, migration: 0 },
                          { env: "Production", project: "legacy_finance", models: 89, score: 41, errors: 18, warnings: 31, migration: 14 },
                          { env: "Production", project: "marketing_attribution", models: 62, score: 67, errors: 7, warnings: 19, migration: 3 },
                          { env: "Staging", project: "acme_core", models: 147, score: 82, errors: 4, warnings: 13, migration: 0 }
                        ].map((row, i) => (
                          <tr key={i}>
                            <td><span className="env-badge">{row.env}</span></td>
                            <td><code className="proj-name">{row.project}</code></td>
                            <td>{row.models}</td>
                            <td>
                              <span className={`score-pill ${row.score >= 75 ? "score-good" : row.score >= 60 ? "score-warn" : "score-fail"}`}>
                                {row.score}
                              </span>
                            </td>
                            <td className="cell-error">{row.errors}</td>
                            <td className="cell-warn">{row.warnings}</td>
                            <td className={row.migration > 0 ? "cell-migration" : "cell-clean"}>
                              {row.migration > 0 ? `${row.migration} issues` : "Clean"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <p className="table-note">
                      The <em>legacy_finance</em> project shows 14 migration issues — models carried over from a
                      Talend migration with hardcoded schemas and no ref() calls. This view makes that prioritization
                      obvious at a glance.
                    </p>
                  </div>

                  <div className="run-divider"><span>Terminal command</span></div>

                  <div className="run-step">
                    <div className="run-step-num">→</div>
                    <div className="run-step-body">
                      <strong>Scan all environments in your account</strong>
                      <p>
                        Pass{" "}
                        <code className="inline-code">--all-projects</code> to iterate every environment in your
                        dbt Cloud account and produce a combined report. Output includes per-project scores and a
                        consolidated violations list filterable by migration category.
                      </p>
                      <div className="cmd-block">
                        <code>
                          {`dbt-governance scan --cloud --all-projects --account-id ${config.dbt_cloud.account_id || "YOUR_ACCOUNT_ID"} --output json --output-file all-projects.json`}
                        </code>
                        <button
                          className="cmd-copy"
                          onClick={() =>
                            copyCommand(
                              `dbt-governance scan --cloud --all-projects --account-id ${config.dbt_cloud.account_id || "YOUR_ACCOUNT_ID"} --output json --output-file all-projects.json`,
                              "all-projects"
                            )
                          }
                        >
                          {copiedCommand === "all-projects" ? "Copied!" : "Copy"}
                        </button>
                      </div>
                      <p className="cmd-hint">
                        Requires <code className="inline-code">DBT_CLOUD_API_TOKEN</code> with account-level
                        read permissions. The scanner fetches the environment list from the Admin API, then runs
                        one scan per environment.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Terminal instructions — shared for single project */}
              {scanScope === "single" && (
                <>
                  <div className="run-divider"><span>Or run from the terminal</span></div>

                  <div className="run-steps">
                    <div className="run-step">
                      <div className="run-step-num">1</div>
                      <div className="run-step-body">
                        <strong>Install the scanner</strong>
                        <p>Requires Python 3.11+.</p>
                        <div className="cmd-block">
                          <code>pip install dbt-governance</code>
                          <button className="cmd-copy" onClick={() => copyCommand("pip install dbt-governance", "install")}>
                            {copiedCommand === "install" ? "Copied!" : "Copy"}
                          </button>
                        </div>
                      </div>
                    </div>

                    <div className="run-step">
                      <div className="run-step-num">2</div>
                      <div className="run-step-body">
                        <strong>Download and commit your config files</strong>
                        <p>Use the download bar below to get all three files, then commit them to your dbt project root.</p>
                        <div className="file-list">
                          <span className="file-badge">.dbt-governance.yml</span>
                          <span className="file-badge">REVIEW.md</span>
                          <span className="file-badge">CLAUDE.md</span>
                        </div>
                      </div>
                    </div>

                    <div className="run-step">
                      <div className="run-step-num">3</div>
                      <div className="run-step-body">
                        <strong>Set your API tokens</strong>
                        <p>
                          Create a <code className="inline-code">.env</code> file or set CI secrets.
                          Generate a dbt Cloud service token with <strong>Metadata Only</strong> permissions at{" "}
                          <span className="mono-hint">cloud.getdbt.com → Settings → Service Tokens</span>.
                        </p>
                        <div className="cmd-block">
                          <code>{`DBT_CLOUD_API_TOKEN=your_service_token_here\n# AI review (optional, matches your provider in Settings)\nANTHROPIC_API_KEY=your_key_here`}</code>
                          <button
                            className="cmd-copy"
                            onClick={() => copyCommand("DBT_CLOUD_API_TOKEN=your_service_token_here\nANTHROPIC_API_KEY=your_key_here", "env")}
                          >
                            {copiedCommand === "env" ? "Copied!" : "Copy"}
                          </button>
                        </div>
                      </div>
                    </div>

                    <div className="run-step">
                      <div className="run-step-num">4</div>
                      <div className="run-step-body">
                        <strong>Run the scan</strong>
                        <div className="cmd-block">
                          <code>dbt-governance scan --cloud --config .dbt-governance.yml</code>
                          <button className="cmd-copy" onClick={() => copyCommand("dbt-governance scan --cloud --config .dbt-governance.yml", "scan")}>
                            {copiedCommand === "scan" ? "Copied!" : "Copy"}
                          </button>
                        </div>
                        <div className="cmd-block secondary-cmd">
                          <code>dbt-governance scan --local --manifest target/manifest.json</code>
                          <button className="cmd-copy" onClick={() => copyCommand("dbt-governance scan --local --manifest target/manifest.json", "scan-local")}>
                            {copiedCommand === "scan-local" ? "Copied!" : "Copy"}
                          </button>
                        </div>
                        <p className="cmd-hint">Cloud mode (top) queries the dbt Cloud API. Local mode (bottom) reads a manifest.json from disk.</p>
                      </div>
                    </div>

                    <div className="run-step">
                      <div className="run-step-num">5</div>
                      <div className="run-step-body">
                        <strong>Add to GitHub Actions</strong>
                        <p>Runs on every PR touching a model or YAML file. No dbt installation needed.</p>
                        <div className="cmd-block multiline">
                          <code>{`name: dbt Governance
on:
  pull_request:
    paths: ['models/**', 'macros/**', '*.yml']

jobs:
  governance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install dbt-governance
      - name: Scan
        run: dbt-governance scan --cloud --config .dbt-governance.yml
        env:
          DBT_CLOUD_API_TOKEN: \${{ secrets.DBT_CLOUD_API_TOKEN }}`}</code>
                          <button
                            className="cmd-copy top"
                            onClick={() =>
                              copyCommand(
                                "name: dbt Governance\non:\n  pull_request:\n    paths: ['models/**', 'macros/**', '*.yml']\n\njobs:\n  governance:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-python@v5\n        with: { python-version: '3.11' }\n      - run: pip install dbt-governance\n      - name: Scan\n        run: dbt-governance scan --cloud --config .dbt-governance.yml\n        env:\n          DBT_CLOUD_API_TOKEN: ${{ secrets.DBT_CLOUD_API_TOKEN }}",
                                "gha"
                              )
                            }
                          >
                            {copiedCommand === "gha" ? "Copied!" : "Copy"}
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        {/* ── Right status panel ── */}
        <aside className="workspace-side">
          <div className="panel status-panel">
            <div className="panel-header compact">
              <div>
                <p className="panel-kicker">Current Focus</p>
                <h2>{tabFocus}</h2>
              </div>
            </div>

            <div className="metric-stack">
              <div className="mini-metric">
                <span>Total enabled</span>
                <strong>{enabledRuleCount}</strong>
              </div>
              <div className="mini-metric">
                <span>Error</span>
                <strong>{severities.error}</strong>
              </div>
              <div className="mini-metric">
                <span>Warning</span>
                <strong>{severities.warning}</strong>
              </div>
              <div className="mini-metric">
                <span>Info</span>
                <strong>{severities.info}</strong>
              </div>
            </div>

            {/* Context-aware guidance */}
            <div className="note-card side-note">
              {activeTab === "naming" && (
                <>
                  <strong>Start here</strong>
                  <p>Naming rules are your first line of defence. Lock these down before anything else — they tell every developer what a dbt model is supposed to look like.</p>
                </>
              )}
              {activeTab === "structure" && (
                <>
                  <strong>Protect your DAG</strong>
                  <p>Layer-skipping and direct source refs in marts are the most common structural debt. Set these to error to block them at the PR gate.</p>
                </>
              )}
              {activeTab === "testing" && (
                <>
                  <strong>Baseline contracts</strong>
                  <p>Primary key tests are non-negotiable. Start strict here — teams rarely push back once they understand these prevent silent data quality failures.</p>
                </>
              )}
              {activeTab === "documentation" && (
                <>
                  <strong>Legibility at scale</strong>
                  <p>Mart-level documentation has the highest ROI — analysts hit these models daily. Focus requirements there first.</p>
                </>
              )}
              {activeTab === "materialization" && (
                <>
                  <strong>Performance guardrails</strong>
                  <p>Incremental models without unique_key are the most common source of silent data duplication. Make that an error.</p>
                </>
              )}
              {activeTab === "style" && (
                <>
                  <strong>Readability at PR time</strong>
                  <p>Hardcoded schemas break cross-environment portability and are the most common style violation after a migration.</p>
                </>
              )}
              {activeTab === "migration" && (
                <>
                  <strong>Migration debt scanner</strong>
                  <p>Run these against your production environment to produce a Legacy Migration Report. Every violation comes with an exact fix. Hand it to a team and they have a sprint's worth of clearly-scoped work.</p>
                </>
              )}
              {activeTab === "reuse" && (
                <>
                  <strong>Find the redundancy</strong>
                  <p>After a legacy migration, teams typically have 3-5x more staging models than they need. These rules surface exactly where to consolidate.</p>
                </>
              )}
              {activeTab === "artifacts" && (
                <>
                  <strong>Three files, one commit</strong>
                  <p>Download all three files and commit them to your dbt repo root. That's the full setup — no additional infrastructure needed.</p>
                </>
              )}
              {activeTab === "run" && (
                <>
                  <strong>Run a live scan</strong>
                  <p>
                    {cloudConfigured
                      ? `Your dbt Cloud connection is configured (env ${config.dbt_cloud.environment_id}). Hit Run Scan to see live violations.`
                      : "Open Settings to configure your dbt Cloud connection, then run a live scan to see your current governance score."}
                  </p>
                </>
              )}
            </div>
          </div>
        </aside>
      </section>

      {/* ─────────────────── Bottom bar ─────────────────── */}
      <div className="bottom-bar">
        <div className="bottom-bar-inner">
          <div className="bottom-bar-status">
            {isDownloadReady ? (
              <span className="dl-status ready">
                <span className="dl-dot" />
                {enabledRuleCount} rules configured — ready to download
              </span>
            ) : (
              <span className="dl-status warn">Enter a project name to enable downloads</span>
            )}
          </div>
          <div className="bottom-bar-actions">
            <button className="primary-button" disabled={!isDownloadReady} onClick={() => downloadFile(".dbt-governance.yml", yamlPreview)}>
              Download .dbt-governance.yml
            </button>
            <button className="primary-button secondary" disabled={!isDownloadReady} onClick={() => downloadFile("REVIEW.md", reviewPreview)}>
              Download REVIEW.md
            </button>
            <button className="primary-button secondary" disabled={!isDownloadReady} onClick={() => downloadFile("CLAUDE.md", claudePreview)}>
              Download CLAUDE.md
            </button>
          </div>
        </div>
      </div>

      {/* ─────────────────── Settings Drawer ─────────────────── */}
      {showSettings && (
        <div className="drawer-overlay" role="dialog" aria-modal="true" aria-label="Settings">
          <div className="drawer-backdrop" onClick={() => setShowSettings(false)} />
          <div className="settings-drawer">
            <div className="drawer-header">
              <div>
                <p className="panel-kicker">Admin Settings</p>
                <h2>Connection, AI provider &amp; scan defaults</h2>
              </div>
              <button className="ghost-button" onClick={() => setShowSettings(false)}>
                Close ✕
              </button>
            </div>

            {/* ── Connection ── */}
            <div className="drawer-section">
              <div className="drawer-section-header">
                <span className="drawer-section-icon">⚡</span>
                <strong>dbt Cloud Connection</strong>
                <span className={`conn-dot ${cloudConfigured ? "conn-ok" : "conn-off"}`} />
                <span className="conn-label">{cloudConfigured ? "Configured" : "Not configured"}</span>
              </div>

              <label className="drawer-toggle-row">
                <span>Enable dbt Cloud mode</span>
                <input
                  type="checkbox"
                  checked={config.dbt_cloud.enabled}
                  onChange={(e) => updateConfig((next) => { next.dbt_cloud.enabled = e.target.checked; })}
                />
              </label>

              <div className="drawer-form-grid">
                <label>
                  <span>Account ID</span>
                  <input
                    type="number"
                    placeholder="e.g. 257364"
                    value={config.dbt_cloud.account_id || ""}
                    onChange={(e) => updateConfig((next) => { next.dbt_cloud.account_id = Number(e.target.value); })}
                  />
                </label>
                <label>
                  <span>Environment ID</span>
                  <input
                    type="number"
                    placeholder="e.g. 432623"
                    value={config.dbt_cloud.environment_id || ""}
                    onChange={(e) => updateConfig((next) => { next.dbt_cloud.environment_id = Number(e.target.value); })}
                  />
                </label>
                <label className="span-2">
                  <span>API base URL</span>
                  <input
                    value={config.dbt_cloud.api_base_url}
                    onChange={(e) => updateConfig((next) => { next.dbt_cloud.api_base_url = e.target.value; })}
                  />
                </label>
                <label className="span-2">
                  <span>Discovery API URL</span>
                  <input
                    value={config.dbt_cloud.discovery_api_url}
                    onChange={(e) => updateConfig((next) => { next.dbt_cloud.discovery_api_url = e.target.value; })}
                  />
                </label>
                <label>
                  <span>State type</span>
                  <select
                    value={config.dbt_cloud.state_type}
                    onChange={(e) =>
                      updateConfig((next) => {
                        next.dbt_cloud.state_type = e.target.value as "applied" | "definition";
                      })
                    }
                  >
                    <option value="applied">applied (executed state)</option>
                    <option value="definition">definition (logical state)</option>
                  </select>
                </label>
                <div className="drawer-checkboxes">
                  <label className="drawer-toggle-row compact">
                    <span>Include catalog</span>
                    <input
                      type="checkbox"
                      checked={config.dbt_cloud.include_catalog}
                      onChange={(e) => updateConfig((next) => { next.dbt_cloud.include_catalog = e.target.checked; })}
                    />
                  </label>
                  <label className="drawer-toggle-row compact">
                    <span>Include execution info</span>
                    <input
                      type="checkbox"
                      checked={config.dbt_cloud.include_execution_info}
                      onChange={(e) => updateConfig((next) => { next.dbt_cloud.include_execution_info = e.target.checked; })}
                    />
                  </label>
                </div>
              </div>

              <div className="drawer-hint">
                Set <code className="inline-code">DBT_CLOUD_API_TOKEN</code> in your shell or{" "}
                <code className="inline-code">.env</code> file. Generate a service token with{" "}
                <strong>Metadata Only</strong> permissions at cloud.getdbt.com → Settings → Service Tokens.
              </div>
            </div>

            {/* ── AI Provider ── */}
            <div className="drawer-section">
              <div className="drawer-section-header">
                <span className="drawer-section-icon">✦</span>
                <strong>AI Provider</strong>
              </div>

              <div className="drawer-form-grid">
                <label className="span-2">
                  <span>Provider</span>
                  <select
                    value={config.ai_provider.provider}
                    onChange={(e) => {
                      const provider = e.target.value as AiProvider;
                      updateConfig((next) => {
                        next.ai_provider.provider = provider;
                        const models = provider === "claude" ? claudeModels : provider === "openai" ? openaiModels : provider === "gemini" ? geminiModels : [];
                        next.ai_provider.model = models[0]?.value ?? "";
                      });
                    }}
                  >
                    {aiProviderOptions.map((opt) => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                </label>

                {config.ai_provider.provider !== "none" && (
                  <>
                    <label className="span-2">
                      <span>Model</span>
                      <select
                        value={config.ai_provider.model}
                        onChange={(e) => updateConfig((next) => { next.ai_provider.model = e.target.value; })}
                      >
                        {modelsForProvider(config.ai_provider.provider).map((m) => (
                          <option key={m.value} value={m.value}>{m.label}</option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span>Max tokens per review</span>
                      <input
                        type="number"
                        value={config.ai_provider.max_tokens_per_review}
                        onChange={(e) =>
                          updateConfig((next) => { next.ai_provider.max_tokens_per_review = Number(e.target.value); })
                        }
                      />
                    </label>
                  </>
                )}
              </div>

              {config.ai_provider.provider !== "none" && (
                <div className="drawer-hint">
                  Set{" "}
                  {config.ai_provider.provider === "claude"
                    ? <code className="inline-code">ANTHROPIC_API_KEY</code>
                    : config.ai_provider.provider === "openai"
                      ? <code className="inline-code">OPENAI_API_KEY</code>
                      : <code className="inline-code">GEMINI_API_KEY</code>
                  }{" "}
                  in your environment. AI review runs only when{" "}
                  <code className="inline-code">--with-ai</code> is passed to the scanner.
                </div>
              )}
            </div>

            {/* ── Scan Defaults ── */}
            <div className="drawer-section">
              <div className="drawer-section-header">
                <span className="drawer-section-icon">⚙</span>
                <strong>Scan Defaults</strong>
              </div>

              <div className="drawer-form-grid">
                <label>
                  <span>Fail CI on severity</span>
                  <select
                    value={config.global.fail_on}
                    onChange={(e) =>
                      updateConfig((next) => { next.global.fail_on = e.target.value as Severity; })
                    }
                  >
                    {severityOptions.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Default severity</span>
                  <select
                    value={config.global.severity_default}
                    onChange={(e) =>
                      updateConfig((next) => { next.global.severity_default = e.target.value as Severity; })
                    }
                  >
                    {severityOptions.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </label>
                <label className="span-2 drawer-toggle-row">
                  <span>Scan changed files only (PR mode)</span>
                  <input
                    type="checkbox"
                    checked={config.global.changed_files_only}
                    onChange={(e) => updateConfig((next) => { next.global.changed_files_only = e.target.checked; })}
                  />
                </label>
                <label className="span-2">
                  <span>Excluded paths (comma-separated)</span>
                  <input
                    value={config.global.exclude_paths.join(", ")}
                    onChange={(e) =>
                      updateConfig((next) => {
                        next.global.exclude_paths = e.target.value
                          .split(",")
                          .map((s) => s.trim())
                          .filter(Boolean);
                      })
                    }
                  />
                </label>
              </div>
            </div>

            {/* ── Danger zone ── */}
            <div className="drawer-section drawer-danger">
              <button
                className="ghost-button danger"
                onClick={() => {
                  setConfig(cloneConfig(defaultGovernanceConfig));
                  setShowSettings(false);
                }}
              >
                Reset all to defaults
              </button>
              <p className="drawer-hint">Resets all rules, settings, and connection config to factory defaults.</p>
            </div>
          </div>
        </div>
      )}

      {/* ─────────────────── Explainer Modal ─────────────────── */}
      {showExplainer && (
        <div className="guide-overlay" role="dialog" aria-modal="true">
          <div className="guide-backdrop" onClick={() => setShowExplainer(false)} />
          <div className="guide-modal">
            <div className="panel-header compact">
              <div>
                <p className="panel-kicker">How it works</p>
                <h2>From config to enforced standards — on every PR</h2>
              </div>
              <button className="ghost-button" onClick={() => setShowExplainer(false)}>Close</button>
            </div>

            {/* ── Tab nav ── */}
            <nav className="guide-tab-nav">
              {(["flow", "setup", "experience", "faq"] as const).map((tab) => (
                <button
                  key={tab}
                  className={`guide-tab-btn${explainerTab === tab ? " active" : ""}`}
                  onClick={() => setExplainerTab(tab)}
                >
                  {{ flow: "Architecture", setup: "Setup Guide", experience: "Developer Experience", faq: "FAQ" }[tab]}
                </button>
              ))}
            </nav>

            {/* ── Architecture tab ── */}
            {explainerTab === "flow" && (
              <div className="guide-tab-panel">
                <p className="panel-kicker" style={{ marginBottom: 12 }}>End-to-end data flow</p>
                <svg viewBox="0 0 760 392" className="arch-diagram" role="img" aria-label="Architecture diagram">
                  <defs>
                    <marker id="ah" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
                      <polygon points="0 0, 8 3, 0 6" fill="#8a96a8" />
                    </marker>
                  </defs>

                  {/* Central Governance */}
                  <rect x="280" y="18" width="200" height="44" rx="10" fill="rgba(212,168,67,0.1)" stroke="#d4a843" strokeWidth="1.5" />
                  <text x="380" y="36" textAnchor="middle" fontFamily="system-ui,-apple-system,sans-serif" fontSize="12" fontWeight="600" fill="#1a2030">Central Governance</text>
                  <text x="380" y="53" textAnchor="middle" fontFamily="system-ui,-apple-system,sans-serif" fontSize="10" fill="#64738b">this app — configure your standards</text>

                  {/* Arrow: Central Governance → config files */}
                  <line x1="380" y1="62" x2="380" y2="80" stroke="#8a96a8" strokeWidth="1.5" markerEnd="url(#ah)" />
                  <text x="392" y="75" fontFamily="system-ui,-apple-system,sans-serif" fontSize="9" fill="#8a96a8">Download 3 files</text>

                  {/* Config files box */}
                  <rect x="160" y="82" width="440" height="58" rx="10" fill="rgba(255,255,255,0.72)" stroke="rgba(39,47,75,0.18)" strokeWidth="1.5" />
                  <text x="380" y="104" textAnchor="middle" fontFamily="system-ui,-apple-system,sans-serif" fontSize="11.5" fontWeight="600" fill="#1a2030">.dbt-governance.yml  ·  REVIEW.md  ·  CLAUDE.md</text>
                  <text x="380" y="121" textAnchor="middle" fontFamily="system-ui,-apple-system,sans-serif" fontSize="10" fill="#64738b">Commit all three to the root of your dbt repo</text>
                  <text x="380" y="134" textAnchor="middle" fontFamily="system-ui,-apple-system,sans-serif" fontSize="9.5" fill="#b87800">One-time manual step — everything else is automated</text>

                  {/* Arrow: config → repo */}
                  <line x1="380" y1="140" x2="380" y2="160" stroke="#8a96a8" strokeWidth="1.5" markerEnd="url(#ah)" />

                  {/* dbt repo */}
                  <rect x="280" y="162" width="200" height="40" rx="10" fill="rgba(42,122,122,0.1)" stroke="#2a7a7a" strokeWidth="1.5" />
                  <text x="380" y="179" textAnchor="middle" fontFamily="system-ui,-apple-system,sans-serif" fontSize="12" fontWeight="600" fill="#1a2030">Your dbt repo</text>
                  <text x="380" y="195" textAnchor="middle" fontFamily="system-ui,-apple-system,sans-serif" fontSize="9.5" fill="#64738b">GitHub / GitLab / Bitbucket</text>

                  {/* Branch lines from repo */}
                  <line x1="380" y1="202" x2="380" y2="216" stroke="#8a96a8" strokeWidth="1.5" />
                  <line x1="175" y1="216" x2="585" y2="216" stroke="#8a96a8" strokeWidth="1" strokeDasharray="4,3" />
                  <line x1="175" y1="216" x2="175" y2="246" stroke="#8a96a8" strokeWidth="1.5" markerEnd="url(#ah)" />
                  <line x1="585" y1="216" x2="585" y2="246" stroke="#8a96a8" strokeWidth="1.5" markerEnd="url(#ah)" />
                  <text x="175" y="234" textAnchor="middle" fontFamily="system-ui,-apple-system,sans-serif" fontSize="9" fill="#8a96a8">On every PR</text>
                  <text x="585" y="234" textAnchor="middle" fontFamily="system-ui,-apple-system,sans-serif" fontSize="9" fill="#8a96a8">On every PR</text>

                  {/* Left: GitHub Actions / scan */}
                  <rect x="28" y="248" width="294" height="98" rx="10" fill="rgba(160,66,45,0.07)" stroke="#a0422d" strokeWidth="1.5" />
                  <text x="42" y="270" fontFamily="system-ui,-apple-system,sans-serif" fontSize="11" fontWeight="700" fill="#a0422d">GitHub Actions  (setup required)</text>
                  <text x="42" y="288" fontFamily="system-ui,-apple-system,sans-serif" fontSize="10.5" fontWeight="600" fill="#1a2030">dbt-governance scan</text>
                  <text x="42" y="305" fontFamily="system-ui,-apple-system,sans-serif" fontSize="10" fill="#64738b">· 30+ deterministic rules, runs in ~60s</text>
                  <text x="42" y="320" fontFamily="system-ui,-apple-system,sans-serif" fontSize="10" fill="#64738b">· SARIF output → inline PR annotations</text>
                  <text x="42" y="335" fontFamily="system-ui,-apple-system,sans-serif" fontSize="10" fill="#64738b">· Fails CI on error-severity violations</text>

                  {/* Right: Claude Code Review */}
                  <rect x="438" y="248" width="294" height="98" rx="10" fill="rgba(212,168,67,0.07)" stroke="#d4a843" strokeWidth="1.5" />
                  <text x="452" y="270" fontFamily="system-ui,-apple-system,sans-serif" fontSize="11" fontWeight="700" fill="#b87800">Claude Code Review  (optional)</text>
                  <text x="452" y="288" fontFamily="system-ui,-apple-system,sans-serif" fontSize="10.5" fontWeight="600" fill="#1a2030">Reads REVIEW.md + CLAUDE.md</text>
                  <text x="452" y="305" fontFamily="system-ui,-apple-system,sans-serif" fontSize="10" fill="#64738b">· Semantic judgment on every PR</text>
                  <text x="452" y="320" fontFamily="system-ui,-apple-system,sans-serif" fontSize="10" fill="#64738b">· Catches what static rules miss</text>
                  <text x="452" y="335" fontFamily="system-ui,-apple-system,sans-serif" fontSize="10" fill="#64738b">· Inline comments with context and fixes</text>

                  {/* Data source arrow */}
                  <line x1="130" y1="356" x2="130" y2="348" stroke="#8a96a8" strokeWidth="1" markerEnd="url(#ah)" strokeDasharray="3,2" />

                  {/* Data sources */}
                  <rect x="28" y="358" width="152" height="26" rx="6" fill="rgba(255,255,255,0.65)" stroke="rgba(39,47,75,0.12)" strokeWidth="1" />
                  <text x="104" y="375" textAnchor="middle" fontFamily="system-ui,-apple-system,sans-serif" fontSize="9.5" fill="#1a2030" fontWeight="500">dbt Cloud API</text>
                  <text x="194" y="375" textAnchor="middle" fontFamily="system-ui,-apple-system,sans-serif" fontSize="9" fill="#8a96a8">or</text>
                  <rect x="208" y="358" width="126" height="26" rx="6" fill="rgba(255,255,255,0.65)" stroke="rgba(39,47,75,0.12)" strokeWidth="1" strokeDasharray="4,2" />
                  <text x="271" y="375" textAnchor="middle" fontFamily="system-ui,-apple-system,sans-serif" fontSize="9.5" fill="#64738b">manifest.json (local)</text>

                  {/* Claude requires ANTHROPIC_API_KEY */}
                  <rect x="438" y="358" width="294" height="26" rx="6" fill="rgba(212,168,67,0.06)" stroke="rgba(212,168,67,0.2)" strokeWidth="1" />
                  <text x="585" y="375" textAnchor="middle" fontFamily="system-ui,-apple-system,sans-serif" fontSize="9.5" fill="#8a96a8">Requires: ANTHROPIC_API_KEY in repo secrets</text>
                </svg>

                <div className="arch-legend">
                  <div className="legend-item"><span className="legend-swatch legend-gold" />Central Governance (this app)</div>
                  <div className="legend-item"><span className="legend-swatch legend-teal" />Your dbt repo</div>
                  <div className="legend-item"><span className="legend-swatch legend-brick" />CI enforcement — requires GitHub Actions setup (see Setup Guide tab)</div>
                  <div className="legend-item"><span className="legend-swatch legend-amber" />AI review — requires ANTHROPIC_API_KEY secret</div>
                </div>
              </div>
            )}

            {/* ── Setup Guide tab ── */}
            {explainerTab === "setup" && (
              <div className="guide-tab-panel">
                <p className="panel-kicker" style={{ marginBottom: 4 }}>Complete setup checklist</p>
                <p className="setup-intro">Steps marked <span className="step-badge ext">External</span> require action in your git provider or CI system outside this app.</p>

                <div className="setup-steps">

                  <div className="setup-step">
                    <div className="step-num">1</div>
                    <div className="step-content">
                      <div className="step-title">Configure and download your files <span className="step-badge app">This app</span></div>
                      <p className="step-desc">Use the rule categories in the sidebar to configure your standards, then click <strong>Download Config</strong>, <strong>Download REVIEW.md</strong>, and <strong>Download CLAUDE.md</strong> in the Artifacts tab. You get three files.</p>
                    </div>
                  </div>

                  <div className="setup-step">
                    <div className="step-num">2</div>
                    <div className="step-content">
                      <div className="step-title">Commit the three files to your dbt repo <span className="step-badge ext">Your repo</span></div>
                      <p className="step-desc">Place all three files in the <strong>root directory</strong> of your dbt project. Claude Code automatically reads <code>CLAUDE.md</code> from the repo root — placement matters.</p>
                      <pre className="code-block">{`git add .dbt-governance.yml REVIEW.md CLAUDE.md
git commit -m "chore: add dbt governance config"
git push`}</pre>
                    </div>
                  </div>

                  <div className="setup-step">
                    <div className="step-num ext">3</div>
                    <div className="step-content">
                      <div className="step-title">Create a GitHub Actions workflow <span className="step-badge ext">GitHub</span></div>
                      <p className="step-desc">Create <code>.github/workflows/dbt-governance.yml</code> in your dbt repo. This runs the scanner on every PR that touches model files.</p>
                      <pre className="code-block">{`name: dbt Governance
on:
  pull_request:
    branches: [main, develop]
    paths:
      - 'models/**'
      - '.dbt-governance.yml'
      - 'dbt_project.yml'
jobs:
  scan:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write   # required for SARIF upload
      pull-requests: write     # required for PR annotations
    steps:
      - uses: actions/checkout@v4
      - name: Install dbt-governance
        run: pip install dbt-governance
      - name: Run governance scan
        env:
          DBT_CLOUD_API_TOKEN: \${{ secrets.DBT_CLOUD_API_TOKEN }}
          DBT_CLOUD_ACCOUNT_ID: \${{ secrets.DBT_CLOUD_ACCOUNT_ID }}
          DBT_CLOUD_ENVIRONMENT_ID: \${{ secrets.DBT_CLOUD_ENVIRONMENT_ID }}
        run: |
          dbt-governance scan \\
            --output sarif \\
            --output-file governance.sarif
      - name: Upload results to GitHub code scanning
        uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: governance.sarif
          category: dbt-governance`}</pre>
                    </div>
                  </div>

                  <div className="setup-step">
                    <div className="step-num ext">4</div>
                    <div className="step-content">
                      <div className="step-title">Add GitHub repository secrets <span className="step-badge ext">GitHub</span></div>
                      <p className="step-desc">Go to your dbt repo → <strong>Settings → Secrets and variables → Actions → New repository secret</strong>. Add these three secrets:</p>
                      <div className="secrets-list">
                        <div className="secret-row">
                          <span className="secret-name">DBT_CLOUD_API_TOKEN</span>
                          <span className="secret-desc">Your dbt Cloud service token — Settings → API Tokens in dbt Cloud</span>
                        </div>
                        <div className="secret-row">
                          <span className="secret-name">DBT_CLOUD_ACCOUNT_ID</span>
                          <span className="secret-desc">Numeric account ID visible in the dbt Cloud URL: cloud.getdbt.com/accounts/12345</span>
                        </div>
                        <div className="secret-row">
                          <span className="secret-name">DBT_CLOUD_ENVIRONMENT_ID</span>
                          <span className="secret-desc">Production environment ID — from Environments page in dbt Cloud</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="setup-step">
                    <div className="step-num ext">5</div>
                    <div className="step-content">
                      <div className="step-title">Enable GitHub code scanning <span className="step-badge ext">GitHub</span></div>
                      <p className="step-desc">For SARIF results to appear as inline PR annotations, go to your repo → <strong>Settings → Code security and analysis → Code scanning → Enable</strong>. Requires GitHub Advanced Security for private repos.</p>
                      <p className="step-desc">If you skip this step, violations still fail CI — they just appear in the Actions log instead of as inline PR annotations.</p>
                    </div>
                  </div>

                  <div className="setup-step">
                    <div className="step-num ext">6</div>
                    <div className="step-content">
                      <div className="step-title">Set up Claude Code Review <span className="step-badge opt">Optional</span></div>
                      <p className="step-desc">Once <code>CLAUDE.md</code> and <code>REVIEW.md</code> are committed, you have two options:</p>
                      <p className="step-desc"><strong>Option A — GitHub Action (automated on every PR):</strong> Create <code>.github/workflows/claude-review.yml</code>:</p>
                      <pre className="code-block">{`name: Claude Code Review
on:
  pull_request:
    paths: ['models/**', 'dbt_project.yml']
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: anthropics/claude-code-action@beta
        with:
          anthropic_api_key: \${{ secrets.ANTHROPIC_API_KEY }}`}</pre>
                      <p className="step-desc" style={{ marginTop: 8 }}>Add <code>ANTHROPIC_API_KEY</code> to your GitHub repository secrets (from <strong>console.anthropic.com → API keys</strong>).</p>
                      <p className="step-desc"><strong>Option B — Developer-side:</strong> Developers with Claude Code installed automatically get <code>CLAUDE.md</code> context when they run <code>claude</code> in the repo. No CI setup needed.</p>
                    </div>
                  </div>

                  <div className="setup-step">
                    <div className="step-num">7</div>
                    <div className="step-content">
                      <div className="step-title">Run on-demand scans locally <span className="step-badge app">CLI</span></div>
                      <p className="step-desc">Install the CLI and create a <code>.env</code> file (do not commit it) to run scans locally against any existing project:</p>
                      <pre className="code-block">{`pip install dbt-governance

# .env (do not commit)
DBT_CLOUD_API_TOKEN=dbtc_xxxxxxxxxxxxxxxxxxxx
DBT_CLOUD_ACCOUNT_ID=12345
DBT_CLOUD_ENVIRONMENT_ID=67890

# Full scan
dbt-governance scan

# Legacy migration report only
dbt-governance scan --category migration

# Re-use analysis only
dbt-governance scan --category reuse

# Scan without dbt Cloud (local manifest.json)
dbt-governance scan --manifest-path target/manifest.json`}</pre>
                    </div>
                  </div>

                  <div className="setup-step">
                    <div className="step-num ext">8</div>
                    <div className="step-content">
                      <div className="step-title">GitLab CI alternative <span className="step-badge ext">GitLab</span></div>
                      <p className="step-desc">If you use GitLab instead of GitHub, add this to your <code>.gitlab-ci.yml</code>. Add the three secrets under <strong>Settings → CI/CD → Variables</strong>.</p>
                      <pre className="code-block">{`dbt-governance:
  stage: lint
  image: python:3.11-slim
  script:
    - pip install dbt-governance
    - dbt-governance scan
  variables:
    DBT_CLOUD_API_TOKEN: $DBT_CLOUD_API_TOKEN
    DBT_CLOUD_ACCOUNT_ID: $DBT_CLOUD_ACCOUNT_ID
    DBT_CLOUD_ENVIRONMENT_ID: $DBT_CLOUD_ENVIRONMENT_ID
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"`}</pre>
                    </div>
                  </div>

                  <div className="setup-step">
                    <div className="step-num ext">9</div>
                    <div className="step-content">
                      <div className="step-title">Azure DevOps / Azure Pipelines alternative <span className="step-badge ext">Azure DevOps</span></div>
                      <p className="step-desc">Add an <code>azure-pipelines.yml</code> to your dbt repo. The scanner and CI failure work without any paid add-ons. Inline SARIF annotations on the PR diff require <strong>Azure DevOps Advanced Security</strong> — without it, violations still fail the pipeline and the SARIF is published as a build artifact.</p>
                      <pre className="code-block">{`# azure-pipelines.yml
trigger: none
pr:
  branches:
    include: [main, develop]
  paths:
    include:
      - models/**
      - .dbt-governance.yml
      - dbt_project.yml

pool:
  vmImage: ubuntu-latest

steps:
  - task: UsePythonVersion@0
    inputs:
      versionSpec: '3.11'
    displayName: Use Python 3.11

  - script: pip install dbt-governance
    displayName: Install dbt-governance

  - script: |
      dbt-governance scan \\
        --output sarif \\
        --output-file governance.sarif
    displayName: Run governance scan
    env:
      DBT_CLOUD_API_TOKEN: $(DBT_CLOUD_API_TOKEN)
      DBT_CLOUD_ACCOUNT_ID: $(DBT_CLOUD_ACCOUNT_ID)
      DBT_CLOUD_ENVIRONMENT_ID: $(DBT_CLOUD_ENVIRONMENT_ID)

  # With Azure DevOps Advanced Security — inline PR annotations
  - task: AdvancedSecurity-Publish@1
    inputs:
      SarifFile: governance.sarif
    displayName: Upload SARIF (Advanced Security)
    condition: always()

  # Without Advanced Security — publish as downloadable artifact instead
  # - task: PublishBuildArtifacts@1
  #   inputs:
  #     PathtoPublish: governance.sarif
  #     ArtifactName: governance-results
  #   condition: always()`}</pre>
                      <p className="step-desc" style={{ marginTop: 8 }}>Add the three pipeline variables under <strong>Pipelines → Library → Variable Groups</strong> or directly on the pipeline under <strong>Variables → New variable</strong> — mark each as secret.</p>
                    </div>
                  </div>

                </div>
              </div>
            )}

            {/* ── Developer Experience tab ── */}
            {explainerTab === "experience" && (
              <div className="guide-grid">
                <div className="explainer-block">
                  <p className="panel-kicker">The four steps</p>
                  {explainerSteps.map((step) => (
                    <div className="step-row" key={step.title}>
                      <strong>{step.title}</strong>
                      <p>{step.body}</p>
                    </div>
                  ))}
                </div>
                <div className="explainer-block example-block full-span">
                  <p className="panel-kicker">Walk-through example</p>
                  <h3>What a developer actually experiences on a pull request</h3>
                  {exampleFlow.map((item) => (
                    <div className="step-row" key={item.step}>
                      <strong>{item.step}</strong>
                      <p>{item.detail}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ── FAQ tab ── */}
            {explainerTab === "faq" && (
              <div className="guide-grid">
                <div className="explainer-block">
                  <p className="panel-kicker">Common questions</p>
                  {operationalAnswers.map((item) => (
                    <div className="step-row" key={item.question}>
                      <strong>{item.question}</strong>
                      <p>{item.answer}</p>
                    </div>
                  ))}
                </div>
                <div className="explainer-block full-span">
                  <p className="panel-kicker">The dbt ecosystem — and where this tool fits</p>
                  <p className="eco-intro">These are all good tools. This is a dbt-built product designed to fill the gaps none of them cover. Use them together.</p>
                  <div className="eco-grid">
                    {ecosystemTools.map((tool) => (
                      <div className="eco-card" key={tool.name}>
                        <div className="eco-card-header">
                          <strong className="eco-name">{tool.name}</strong>
                          <span className="eco-by">{tool.by}</span>
                        </div>
                        <p className="eco-tagline">{tool.tagline}</p>
                        <div className="eco-row">
                          <span className="eco-label">Great for</span>
                          <p>{tool.strengths}</p>
                        </div>
                        <div className="eco-row">
                          <span className="eco-label">Scope limit</span>
                          <p>{tool.limitation}</p>
                        </div>
                        <div className="eco-row fills">
                          <span className="eco-label">Gap filled</span>
                          <p>{tool.gap}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
