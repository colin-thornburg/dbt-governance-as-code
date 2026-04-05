"use client";

import { useMemo, useState, useEffect, useRef } from "react";
import {
  categoryDefinitions,
  type CategoryKey,
  cloneConfig,
  countEnabledRules,
  defaultGovernanceConfig,
  aiMdFilename,
  generateClaudeMd,
  generateCopilotMd,
  generateGeminiMd,
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

type PreviewMode = "yaml" | "review" | "claude" | "copilot";
type WorkspaceTab = CategoryKey | "artifacts" | "run";

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
  { value: "gemini-3.1-flash-lite-preview", label: "Gemini 3.1 Flash Lite" },
  { value: "gemini-2.5-pro", label: "Gemini 2.5 Pro" },
  { value: "gemini-2.5-flash", label: "Gemini 2.5 Flash" },
];

const workspaceTabs: Array<{ key: WorkspaceTab; label: string; group?: string }> = [
  ...categoryDefinitions.map((category) => ({
    key: category.key,
    label: category.title.replace(" Rules", ""),
    group: category.key === "reuse" ? "migration" : "standard"
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
    body: "Hit Download to get your `.dbt-governance.yml`, `REVIEW.md`, and your AI context file (`CLAUDE.md` for Anthropic/OpenAI, `GEMINI.md` for Google). Commit all three to the root of your dbt repository."
  },
  {
    title: "3. CI catches violations automatically",
    body: "On every PR, `dbt-governance scan` reads your config and checks every changed model. Violations appear as inline annotations and can fail the CI check."
  },
  {
    title: "4. AI Code Review adds semantic judgment",
    body: "Because `REVIEW.md` and your AI context file are committed, your AI assistant (Claude Code, Gemini CLI, etc.) reads them on every PR and leaves inline comments for things a static scanner misses."
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
  details?: {
    recommendation_type?: "pair" | "cluster";
    similarity_score?: number;
    confidence_band?: "high" | "medium" | "low";
    paired_model_name?: string;
    paired_file_path?: string;
    shared_inputs?: string[];
    shared_selected_columns?: string[];
    shared_aggregates?: string[];
    shared_filters?: string[];
    suggested_shared_model?: string;
    cluster_models?: string[];
    cluster_size?: number;
    cluster_average_score?: number;
    cluster_peak_score?: number;
    cluster_example_pairs?: Array<{
      left_model_name: string;
      right_model_name: string;
      similarity_score: number;
    }>;
  };
}

interface ReuseRecommendation {
  recommendation_type: "pair" | "cluster";
  priority: "high" | "medium" | "low";
  confidence_band: "high" | "medium" | "low";
  summary: string;
  suggested_shared_model?: string | null;
  model_names: string[];
  primary_model_name?: string | null;
  paired_model_name?: string | null;
  similarity_score?: number | null;
  cluster_average_score?: number | null;
  cluster_peak_score?: number | null;
  shared_inputs: string[];
  shared_selected_columns: string[];
  shared_aggregates: string[];
  shared_filters: string[];
  example_pairs: Array<Record<string, string | number>>;
}

interface ReuseReport {
  total_recommendations: number;
  cluster_count: number;
  remaining_pair_count: number;
  prioritized_actions: ReuseRecommendation[];
  clusters: ReuseRecommendation[];
  remaining_pairs: ReuseRecommendation[];
}

interface ScanResult {
  scan_id: string;
  timestamp: string;
  project_name: string;
  summary: {
    models_scanned: number;
    rules_evaluated: number;
    errors: number;
    warnings: number;
    info: number;
    score: number;
  };
  violations: ScanViolation[];
  reuse_report?: ReuseReport | null;
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
  const [namingInfoOpen, setNamingInfoOpen] = useState<boolean>(false);
  const [namingInfoPos, setNamingInfoPos] = useState<{ top: number; left: number } | null>(null);
  const namingIconRef = useRef<HTMLSpanElement>(null);
  const namingPopoverRef = useRef<HTMLDivElement>(null);

  const [structureInfoOpen, setStructureInfoOpen] = useState<boolean>(false);
  const [structureInfoPos, setStructureInfoPos] = useState<{ top: number; left: number } | null>(null);
  const structureIconRef = useRef<HTMLSpanElement>(null);
  const structurePopoverRef = useRef<HTMLDivElement>(null);

  const [testingInfoOpen, setTestingInfoOpen] = useState<boolean>(false);
  const [testingInfoPos, setTestingInfoPos] = useState<{ top: number; left: number } | null>(null);
  const testingIconRef = useRef<HTMLSpanElement>(null);
  const testingPopoverRef = useRef<HTMLDivElement>(null);

  const [documentationInfoOpen, setDocumentationInfoOpen] = useState<boolean>(false);
  const [documentationInfoPos, setDocumentationInfoPos] = useState<{ top: number; left: number } | null>(null);
  const documentationIconRef = useRef<HTMLSpanElement>(null);
  const documentationPopoverRef = useRef<HTMLDivElement>(null);

  const [materializationInfoOpen, setMaterializationInfoOpen] = useState<boolean>(false);
  const [materializationInfoPos, setMaterializationInfoPos] = useState<{ top: number; left: number } | null>(null);
  const materializationIconRef = useRef<HTMLSpanElement>(null);
  const materializationPopoverRef = useRef<HTMLDivElement>(null);

  const [styleInfoOpen, setStyleInfoOpen] = useState<boolean>(false);
  const [styleInfoPos, setStyleInfoPos] = useState<{ top: number; left: number } | null>(null);
  const styleIconRef = useRef<HTMLSpanElement>(null);
  const stylePopoverRef = useRef<HTMLDivElement>(null);

  const [artifactsInfoOpen, setArtifactsInfoOpen] = useState<boolean>(false);
  const [artifactsInfoPos, setArtifactsInfoPos] = useState<{ top: number; left: number } | null>(null);
  const artifactsIconRef = useRef<HTMLSpanElement>(null);
  const artifactsPopoverRef = useRef<HTMLDivElement>(null);

  // Scan runner state
  const [scanMode, setScanMode] = useState<"cloud" | "local">("cloud");
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [manifestPath, setManifestPath] = useState("target/manifest.json");
  const [projectDir, setProjectDir] = useState("");
  const [withAiScan, setWithAiScan] = useState(false);
  const [isScanning, setIsScanning] = useState(false);
  const [scanResult, setScanResult] = useState<ScanResult | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  // Environment selection
  const [selectedEnvIds, setSelectedEnvIds] = useState<Set<number>>(new Set());
  // Reuse-tab dedicated scan
  const [reuseResult, setReuseResult] = useState<ScanResult | null>(null);
  const [isReuseScanning, setIsReuseScanning] = useState(false);
  const [reuseError, setReuseError] = useState<string | null>(null);

  // Env var detection for settings drawer
  const [envVars, setEnvVars] = useState<Record<string, boolean>>({});
  const [envLoaded, setEnvLoaded] = useState(false);

  // dbt Cloud environment picker
  type CloudEnv = { id: number; name: string; project_id: number; project_name: string; type: string };
  const [cloudEnvs, setCloudEnvs] = useState<CloudEnv[]>([]);
  const [cloudEnvFetch, setCloudEnvFetch] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [cloudEnvError, setCloudEnvError] = useState<string>("");

  useEffect(() => {
    if (showSettings && !envLoaded) {
      fetch("/api/env-check")
        .then((r) => r.json())
        .then((data) => { setEnvVars(data); setEnvLoaded(true); })
        .catch(() => setEnvLoaded(true));
    }
  }, [showSettings, envLoaded]);

  // Reset environment list whenever account_id changes
  useEffect(() => {
    setCloudEnvFetch("idle");
    setCloudEnvs([]);
    setCloudEnvError("");
  }, [config.dbt_cloud.account_id]);

  // Project name inline editing
  const nameRef = useRef<HTMLInputElement>(null);

  const isDownloadReady = config.project.name.trim().length > 0;
  const cloudConfigured = isCloudConfigured(config);

  const enabledRuleCount = useMemo(() => countEnabledRules(config), [config]);
  const severities = useMemo(() => severityBreakdown(config), [config]);
  const yamlPreview = useMemo(() => generateYaml(config), [config]);
  const reviewPreview = useMemo(() => generateReviewMd(config), [config]);
  const aiMdPreview = useMemo(
    () => config.ai_provider.provider === "gemini" ? generateGeminiMd(config) : generateClaudeMd(config),
    [config]
  );
  const aiMdName = aiMdFilename(config.ai_provider.provider);
  const copilotMdPreview = useMemo(() => generateCopilotMd(config), [config]);

  // Derived from loaded environments
  const uniqueProjects = useMemo(() => {
    const map = new Map<number, string>();
    cloudEnvs.forEach(e => { if (!map.has(e.project_id)) map.set(e.project_id, e.project_name); });
    return Array.from(map.entries())
      .map(([id, name]) => ({ id, name }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [cloudEnvs]);
  const filteredEnvs = selectedProjectId
    ? cloudEnvs.filter(e => e.project_id === selectedProjectId)
    : cloudEnvs;
  const selectedProjectName = selectedProjectId
    ? (uniqueProjects.find(p => p.id === selectedProjectId)?.name ?? "Unknown project")
    : "all projects";

  // Close drawer/modal on Escape
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setShowSettings(false);
        setShowExplainer(false);
        setNamingInfoOpen(false);
        setStructureInfoOpen(false);
        setTestingInfoOpen(false);
        setDocumentationInfoOpen(false);
        setMaterializationInfoOpen(false);
        setStyleInfoOpen(false);
        setArtifactsInfoOpen(false);
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);

  useEffect(() => {
    if (!namingInfoOpen) return;
    function handleClickOutside(e: MouseEvent) {
      const target = e.target as Node;
      const inIcon = namingIconRef.current?.contains(target);
      const inPopover = namingPopoverRef.current?.contains(target);
      if (!inIcon && !inPopover) setNamingInfoOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [namingInfoOpen]);

  useEffect(() => {
    if (!structureInfoOpen) return;
    function handleClickOutside(e: MouseEvent) {
      const target = e.target as Node;
      if (!structureIconRef.current?.contains(target) && !structurePopoverRef.current?.contains(target)) {
        setStructureInfoOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [structureInfoOpen]);

  useEffect(() => {
    if (!testingInfoOpen) return;
    function handleClickOutside(e: MouseEvent) {
      const target = e.target as Node;
      if (!testingIconRef.current?.contains(target) && !testingPopoverRef.current?.contains(target)) {
        setTestingInfoOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [testingInfoOpen]);

  useEffect(() => {
    if (!documentationInfoOpen) return;
    function handleClickOutside(e: MouseEvent) {
      const target = e.target as Node;
      if (!documentationIconRef.current?.contains(target) && !documentationPopoverRef.current?.contains(target)) {
        setDocumentationInfoOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [documentationInfoOpen]);

  useEffect(() => {
    if (!materializationInfoOpen) return;
    function handleClickOutside(e: MouseEvent) {
      const target = e.target as Node;
      if (!materializationIconRef.current?.contains(target) && !materializationPopoverRef.current?.contains(target)) {
        setMaterializationInfoOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [materializationInfoOpen]);

  useEffect(() => {
    if (!styleInfoOpen) return;
    function handleClickOutside(e: MouseEvent) {
      const target = e.target as Node;
      if (!styleIconRef.current?.contains(target) && !stylePopoverRef.current?.contains(target)) {
        setStyleInfoOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [styleInfoOpen]);

  useEffect(() => {
    if (!artifactsInfoOpen) return;
    function handleClickOutside(e: MouseEvent) {
      const target = e.target as Node;
      if (!artifactsIconRef.current?.contains(target) && !artifactsPopoverRef.current?.contains(target)) {
        setArtifactsInfoOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [artifactsInfoOpen]);

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
    if (previewMode === "claude") return aiMdPreview;
    if (previewMode === "copilot") return copilotMdPreview;
    return yamlPreview;
  }

  async function copyPreview() {
    await navigator.clipboard.writeText(previewContent());
    setCopiedLabel(`${previewMode.toUpperCase()} copied`);
    window.setTimeout(() => setCopiedLabel(""), 1500);
  }

  // Common production environment name patterns
  const PROD_PATTERNS = ["prod", "production", "prd", "main", "master", "release", "live", "primary", "default"];
  function isProdEnv(name: string): boolean {
    const n = name.toLowerCase().replace(/[^a-z0-9]/g, "");
    return PROD_PATTERNS.some(p => n === p || n.startsWith(p) || n.endsWith(p));
  }

  function selectProdEnvs() {
    const scope = selectedProjectId ? cloudEnvs.filter(e => e.project_id === selectedProjectId) : cloudEnvs;
    const prodIds = new Set(scope.filter(e => isProdEnv(e.name)).map(e => e.id));
    setSelectedEnvIds(prodIds.size > 0 ? prodIds : new Set(scope.map(e => e.id)));
  }
  function selectAllEnvs() {
    const scope = selectedProjectId ? cloudEnvs.filter(e => e.project_id === selectedProjectId) : cloudEnvs;
    setSelectedEnvIds(new Set(scope.map(e => e.id)));
  }
  function clearEnvs() { setSelectedEnvIds(new Set()); }
  function toggleEnv(id: number, checked: boolean) {
    setSelectedEnvIds(prev => {
      const next = new Set(prev);
      if (checked) next.add(id); else next.delete(id);
      return next;
    });
  }

  async function fetchCloudEnvironments() {
    if (!config.dbt_cloud.account_id) return;
    setCloudEnvFetch("loading");
    setCloudEnvError("");
    try {
      const params = new URLSearchParams({
        account_id: String(config.dbt_cloud.account_id),
        api_base_url: config.dbt_cloud.api_base_url,
      });
      const res = await fetch(`/api/dbt-cloud/environments?${params}`);
      const data = await res.json() as { environments?: { id: number; name: string; project_id: number; project_name: string; type: string }[]; error?: string };
      if (data.error) throw new Error(data.error);
      const envs = data.environments ?? [];
      setCloudEnvs(envs);
      setCloudEnvFetch("done");
      // Auto-select production environments for multi-env scanning
      const prodIds = new Set(envs.filter(e => {
        const n = e.name.toLowerCase().replace(/[^a-z0-9]/g, "");
        return ["prod","production","prd","main","master","release","live","primary","default"].some(
          p => n === p || n.startsWith(p) || n.endsWith(p)
        );
      }).map(e => e.id));
      if (prodIds.size > 0) setSelectedEnvIds(prodIds);
      else if (envs.length > 0) setSelectedEnvIds(new Set(envs.map(e => e.id)));
      // Auto-select first real env for config if currently unset
      if (config.dbt_cloud.environment_id === 0 && envs.length > 0) {
        const firstProd = envs.find(e => prodIds.has(e.id)) ?? envs[0];
        updateConfig((next) => { next.dbt_cloud.environment_id = firstProd.id; });
      }
    } catch (e) {
      setCloudEnvError(e instanceof Error ? e.message : "Failed to fetch environments");
      setCloudEnvFetch("error");
    }
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
      // For cloud mode, use the first selected environment
      let configYamlForScan = yamlPreview;
      if (scanMode === "cloud" && selectedEnvIds.size > 0) {
        const firstEnvId = Array.from(selectedEnvIds)[0];
        const configForScan = cloneConfig(config);
        configForScan.dbt_cloud.environment_id = firstEnvId;
        configYamlForScan = generateYaml(configForScan);
      }
      const response = await fetch("/api/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          configYaml: configYamlForScan,
          mode: scanMode,
          manifestPath: scanMode === "local" ? manifestPath : undefined,
          projectDir: scanMode === "local" && projectDir ? projectDir : undefined,
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

  async function runReuseScan() {
    setIsReuseScanning(true);
    setReuseResult(null);
    setReuseError(null);
    try {
      let configYamlForScan = yamlPreview;
      if (scanMode === "cloud" && selectedEnvIds.size > 0) {
        const firstEnvId = Array.from(selectedEnvIds)[0];
        const configForScan = cloneConfig(config);
        configForScan.dbt_cloud.environment_id = firstEnvId;
        configYamlForScan = generateYaml(configForScan);
      }
      const response = await fetch("/api/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          configYaml: configYamlForScan,
          mode: scanMode,
          manifestPath: scanMode === "local" ? manifestPath : undefined,
          projectDir: scanMode === "local" && projectDir ? projectDir : undefined,
          withAi: false,
          ruleCategories: ["reuse"],
        }),
      });
      const data = await response.json();
      if (data.success) {
        setReuseResult(data.result as ScanResult);
      } else {
        setReuseError(data.error ?? "Scan failed");
      }
    } catch (err: unknown) {
      setReuseError(err instanceof Error ? err.message : "Network error");
    } finally {
      setIsReuseScanning(false);
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

  function confidenceTone(confidence?: "high" | "medium" | "low"): string {
    if (confidence === "high") return "conf-high";
    if (confidence === "medium") return "conf-medium";
    return "conf-low";
  }

  function priorityTone(priority?: "high" | "medium" | "low"): string {
    if (priority === "high") return "conf-high";
    if (priority === "medium") return "conf-medium";
    return "conf-low";
  }

  function applyReusePreset(minScore: number, maxMatchesPerModel: number) {
    updateConfig((next) => {
      const pairRule = next.reuse.rules.model_similarity_candidates;
      if (pairRule) {
        pairRule.enabled = true;
        pairRule.min_score = minScore;
        pairRule.max_matches_per_model = maxMatchesPerModel;
      }
      const clusterRule = next.reuse.rules.model_similarity_clusters;
      if (clusterRule) {
        clusterRule.enabled = true;
      }
    });
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

  function reuseReportMarkdown(result: ScanResult): string {
    const report = result.reuse_report;
    const riskLabel = (() => {
      const highPriorityCount = report?.prioritized_actions.filter((action) => action.priority === "high").length ?? 0;
      const clusterCount = report?.cluster_count ?? 0;
      const totalRecommendations = report?.total_recommendations ?? 0;
      if (highPriorityCount >= 3 || clusterCount >= 2) return "High";
      if (highPriorityCount >= 1 || totalRecommendations >= 3) return "Moderate";
      return "Low";
    })();
    const lines = [
      "# Reuse Remediation Report",
      "",
      "<!-- Auto-generated by dbt-governance -->",
      "",
      `Project: ${result.project_name || "—"}`,
      `Generated at: ${result.timestamp}`,
      "",
    ];

    if (!report || report.total_recommendations === 0) {
      lines.push(
        "## Executive Summary",
        "",
        "No material re-use remediation work is currently prioritized from this scan.",
        "",
        "Governance recommendation: keep monitoring new models and review future scan results for emerging consolidation opportunities.",
        "",
        "## Summary",
        "",
        "No ranked re-use recommendations were found in this scan.",
        "",
        "This means the scanner did not detect any high-confidence pairwise or cluster-level consolidation opportunities.",
        "",
      );
      return lines.join("\n");
    }

    const topActions = report.prioritized_actions.slice(0, 3);
    const highPriorityActions = report.prioritized_actions.filter((action) => action.priority === "high");

    lines.push(
      "## Executive Summary",
      "",
      `- Re-use remediation risk: ${riskLabel}`,
      `- Highest-priority actions: ${highPriorityActions.length}`,
      `- Multi-model clusters to address: ${report.cluster_count}`,
      `- Remaining pair consolidations: ${report.remaining_pair_count}`,
      "",
      "Recommended leadership focus:",
      ...topActions.map((action) => {
        const focusTarget =
          action.recommendation_type === "cluster"
            ? `${action.model_names.length}-model cluster`
            : `${action.primary_model_name} + ${action.paired_model_name}`;
        const sharedModel = action.suggested_shared_model ?? "a shared intermediate";
        return `- ${action.priority[0].toUpperCase()}${action.priority.slice(1)} priority ${action.recommendation_type}: consolidate ${focusTarget} into \`${sharedModel}\`.`;
      }),
      "",
      "Governance recommendation: assign the top items first, starting with clusters because they usually remove the most duplicated transformation logic in the least time.",
      "",
      "## Summary",
      "",
      `- Total recommendations: ${report.total_recommendations}`,
      `- Clusters: ${report.cluster_count}`,
      `- Remaining pairs: ${report.remaining_pair_count}`,
      "",
      "Work the queue in order. Clusters are listed first because they usually remove the most redundant transformation logic in the least time.",
      "",
      "## Prioritized Actions",
      "",
    );

    report.prioritized_actions.forEach((action, index) => {
      lines.push(`### ${index + 1}. ${action.recommendation_type === "cluster" ? "Cluster" : "Pair"} Recommendation`, "");
      lines.push(`- Priority: ${action.priority}`);
      lines.push(`- Confidence: ${action.confidence_band}`);
      if (action.recommendation_type === "cluster" && typeof action.cluster_average_score === "number") {
        lines.push(`- Average similarity: ${action.cluster_average_score.toFixed(2)}`);
      }
      if (action.recommendation_type === "cluster" && typeof action.cluster_peak_score === "number") {
        lines.push(`- Peak similarity: ${action.cluster_peak_score.toFixed(2)}`);
      }
      if (action.recommendation_type === "pair" && typeof action.similarity_score === "number") {
        lines.push(`- Similarity score: ${action.similarity_score.toFixed(2)}`);
      }
      if (action.model_names.length) {
        lines.push(`- Models: ${action.model_names.join(", ")}`);
      }
      if (action.suggested_shared_model) {
        lines.push(`- Suggested shared model: \`${action.suggested_shared_model}\``);
      }
      lines.push("", action.summary);

      const signalLines = [
        action.shared_inputs.length ? `- Shared inputs: ${action.shared_inputs.join(", ")}` : "",
        action.shared_selected_columns.length ? `- Shared columns: ${action.shared_selected_columns.join(", ")}` : "",
        action.shared_aggregates.length ? `- Shared aggregates: ${action.shared_aggregates.join(", ")}` : "",
        action.shared_filters.length ? `- Shared filters: ${action.shared_filters.join(", ")}` : "",
      ].filter(Boolean);
      if (signalLines.length) {
        lines.push("", "Signals:", ...signalLines);
      }

      if (action.example_pairs.length) {
        lines.push("", "Example strong links:");
        action.example_pairs.forEach((pair) => {
          const left = String(pair.left_model_name ?? "");
          const right = String(pair.right_model_name ?? "");
          const score = Number(pair.similarity_score ?? 0);
          lines.push(`- \`${left}\` <-> \`${right}\` (${score.toFixed(2)})`);
        });
      }

      lines.push("");
    });

    return lines.join("\n");
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

  // Reuse tab — shown when the reuse category is active
  const isMigrationTab = activeTab === "reuse";

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

        <div className="rules-stat-bar">
          <span className="rules-stat rules-stat-total">
            <strong>{enabledRuleCount}</strong> rules enabled
          </span>
          <span className="rules-stat-divider" />
          <span className="rules-stat">
            <span className="stat-dot stat-dot-error" />
            <strong>{severities.error}</strong> error
          </span>
          <span className="rules-stat">
            <span className="stat-dot stat-dot-warning" />
            <strong>{severities.warning}</strong> warning
          </span>
          <span className="rules-stat">
            <span className="stat-dot stat-dot-info" />
            <strong>{severities.info}</strong> info
          </span>
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

            <p className="tab-group-label migration-label">Re-use</p>
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
                  <strong>Re-use Opportunities</strong>
                  <p>
                    These rules detect where independent pipelines are doing the same work. Similarity scoring ranks the strongest consolidation candidates first, with confidence bands and suggested shared intermediates so governance teams can act quickly.
                  </p>
                </div>
              )}

              {activeTab === "reuse" && (
                <div className="reuse-explainer">
                  <div className="reuse-explainer-copy">
                    <strong>Similarity scoring makes re-use easy to tune</strong>
                    <p>
                      Start with a minimum score around <code className="inline-code">0.72</code> for migration triage.
                      Raise it toward <code className="inline-code">0.85</code> when you only want near-duplicates.
                      Confidence bands help teams separate obvious consolidation work from broader discovery, and cluster recommendations show when several models should collapse into one shared intermediate instead of being reviewed only as isolated pairs.
                    </p>
                  </div>
                  <div className="reuse-score-guide">
                    <span className="score-chip conf-high">High confidence: 0.85+</span>
                    <span className="score-chip conf-medium">Medium confidence: 0.70-0.84</span>
                    <span className="score-chip conf-low">Low confidence: below 0.70</span>
                  </div>
                  <div className="reuse-preset-row">
                    <button className="ghost-button small" onClick={() => applyReusePreset(0.85, 2)}>
                      Conservative preset
                    </button>
                    <button className="ghost-button small" onClick={() => applyReusePreset(0.72, 3)}>
                      Balanced preset
                    </button>
                    <button className="ghost-button small" onClick={() => applyReusePreset(0.65, 5)}>
                      Discovery preset
                    </button>
                  </div>

                  {/* Dedicated reuse scan */}
                  <div className="reuse-scan-launcher">
                    <div className="reuse-scan-intro">
                      <strong>Scan for redundant models</strong>
                      <p>Select the projects and environments to scan, then run. Only re-use rules are evaluated — no naming, structure, or style checks.</p>
                    </div>

                    {/* Mode toggle */}
                    <div className="mode-toggle reuse-mode-toggle">
                      <button
                        className={scanMode === "cloud" ? "mode-btn active" : "mode-btn"}
                        onClick={() => setScanMode("cloud")}
                      >Cloud</button>
                      <button
                        className={scanMode === "local" ? "mode-btn active" : "mode-btn"}
                        onClick={() => setScanMode("local")}
                      >Local</button>
                    </div>

                    {/* Cloud: project → env selector */}
                    {scanMode === "cloud" && (
                      <>
                        {!cloudConfigured ? (
                          <p className="scan-hint">
                            <button className="inline-link" onClick={() => setShowSettings(true)}>Configure dbt Cloud</button>
                            {" "}in Settings to load environments.
                          </p>
                        ) : cloudEnvFetch === "loading" ? (
                          <p className="env-picker-hint">Loading environments…</p>
                        ) : cloudEnvFetch !== "done" ? (
                          <div className="env-picker-fetch-row">
                            <button className="ghost-button small" onClick={fetchCloudEnvironments}>
                              Load environments from dbt Cloud
                            </button>
                            {cloudEnvFetch === "error" && (
                              <span className="env-picker-error">{cloudEnvError}</span>
                            )}
                          </div>
                        ) : (
                          <>
                            {/* Project picker */}
                            <div className="reuse-picker-section">
                              <span className="reuse-picker-label">Project</span>
                              <div className="project-picker">
                                {uniqueProjects.map(p => (
                                  <button
                                    key={p.id}
                                    className={`project-card${selectedProjectId === p.id ? " project-card-active" : ""}`}
                                    onClick={() => {
                                      setSelectedProjectId(p.id);
                                      const projEnvs = cloudEnvs.filter(e => e.project_id === p.id);
                                      const prodIds = new Set(projEnvs.filter(e => isProdEnv(e.name)).map(e => e.id));
                                      setSelectedEnvIds(prodIds.size > 0 ? prodIds : new Set(projEnvs.map(e => e.id)));
                                    }}
                                  >
                                    {p.name}
                                    <span className="project-card-count">
                                      {cloudEnvs.filter(e => e.project_id === p.id).length} env{cloudEnvs.filter(e => e.project_id === p.id).length !== 1 ? "s" : ""}
                                    </span>
                                  </button>
                                ))}
                                {uniqueProjects.length > 1 && (
                                  <button
                                    className={`project-card project-card-all${!selectedProjectId ? " project-card-active" : ""}`}
                                    onClick={() => {
                                      setSelectedProjectId(null);
                                      const allProdIds = new Set(cloudEnvs.filter(e => isProdEnv(e.name)).map(e => e.id));
                                      setSelectedEnvIds(allProdIds.size > 0 ? allProdIds : new Set(cloudEnvs.map(e => e.id)));
                                    }}
                                  >
                                    All projects
                                    <span className="project-card-count">{cloudEnvs.length} envs</span>
                                  </button>
                                )}
                              </div>
                            </div>

                            {/* Environment checklist */}
                            <div className="reuse-picker-section">
                              <div className="reuse-picker-label-row">
                                <span className="reuse-picker-label">
                                  {selectedProjectId ? `Environments in ${selectedProjectName}` : "Environments"}
                                </span>
                                <div className="env-filter-row">
                                  <button className="env-filter-btn" onClick={selectProdEnvs}>★ Prod only</button>
                                  <button className="env-filter-btn" onClick={selectAllEnvs}>All</button>
                                  <button className="env-filter-btn" onClick={clearEnvs}>None</button>
                                </div>
                              </div>
                              <div className="env-checklist">
                                {filteredEnvs.map(env => {
                                  const isProd = isProdEnv(env.name);
                                  const isDev = env.type === "development";
                                  return (
                                    <label
                                      key={env.id}
                                      className={`env-check-row${isProd ? " env-is-prod" : ""}${selectedEnvIds.has(env.id) ? " env-checked" : ""}`}
                                    >
                                      <input
                                        type="checkbox"
                                        checked={selectedEnvIds.has(env.id)}
                                        onChange={(e) => toggleEnv(env.id, e.target.checked)}
                                      />
                                      <span className="env-check-body">
                                        <span className="env-check-name">{env.name}</span>
                                        {!selectedProjectId && (
                                          <span className="env-check-project">{env.project_name}</span>
                                        )}
                                      </span>
                                      {isProd && <span className="env-badge-prod">prod</span>}
                                      <span className={`env-badge-type${isDev ? " env-badge-dev" : ""}`}>
                                        {env.type}
                                      </span>
                                      <span className="env-check-id">#{env.id}</span>
                                    </label>
                                  );
                                })}
                              </div>
                              {Array.from(selectedEnvIds).some(id => cloudEnvs.find(e => e.id === id)?.type === "development") && (
                                <div className="env-dev-warning" style={{ marginTop: 8 }}>
                                  <strong>⚠ Development environment selected</strong>
                                  <p>Discovery API only covers deployment environments with successful job runs.</p>
                                </div>
                              )}
                              <div className="env-multiselect-footer">
                                <span className="env-count">
                                  {selectedEnvIds.size} of {filteredEnvs.length} selected
                                </span>
                                <button className="ghost-button small" onClick={fetchCloudEnvironments}>↻ Refresh</button>
                              </div>
                            </div>
                          </>
                        )}
                      </>
                    )}

                    {scanMode === "local" && (
                      <>
                        <label className="scan-field">
                          <span>Path to manifest.json</span>
                          <input
                            value={manifestPath}
                            onChange={(e) => setManifestPath(e.target.value)}
                            placeholder="target/manifest.json"
                          />
                        </label>
                        <label className="scan-field">
                          <span>dbt project directory <span className="scan-field-hint">(optional — needed if manifest was built with dbt Fusion/Cloud CLI)</span></span>
                          <input
                            value={projectDir}
                            onChange={(e) => setProjectDir(e.target.value)}
                            placeholder="e.g. demo-project"
                          />
                        </label>
                      </>
                    )}

                    <button
                      className="primary-button reuse-scan-btn"
                      onClick={runReuseScan}
                      disabled={isReuseScanning || !isDownloadReady || (scanMode === "cloud" && !cloudConfigured)}
                    >
                      {isReuseScanning ? (
                        <span className="scan-spinner">Scanning…</span>
                      ) : scanMode === "cloud" && cloudEnvFetch === "done" && selectedEnvIds.size > 0 ? (
                        `Scan ${selectedEnvIds.size} environment${selectedEnvIds.size !== 1 ? "s" : ""}${selectedProjectId ? ` in ${selectedProjectName}` : " across all projects"} →`
                      ) : (
                        "Scan for Redundancy →"
                      )}
                    </button>
                  </div>

                  {reuseError && (
                    <div className="scan-error">
                      <strong>Scan failed</strong>
                      <pre>{reuseError}</pre>
                    </div>
                  )}

                  {reuseResult && (
                    <div className="reuse-report">
                      {/* Header */}
                      <div className="reuse-report-header">
                        <div className="reuse-report-title">
                          <strong>Redundancy Report</strong>
                          <span className="reuse-report-meta">
                            {reuseResult.summary.models_scanned} models scanned ·{" "}
                            {new Date(reuseResult.timestamp).toLocaleTimeString()}
                          </span>
                        </div>
                        <div className="reuse-report-actions">
                          <button
                            className="ghost-button small"
                            onClick={() => downloadFile("REUSE_REPORT.md", reuseReportMarkdown(reuseResult))}
                          >
                            Download Report
                          </button>
                          <button
                            className="ghost-button small"
                            onClick={() => setReuseResult(null)}
                          >
                            Clear
                          </button>
                        </div>
                      </div>

                      {/* Summary cards */}
                      {(() => {
                        const report = reuseResult.reuse_report;
                        const total = report?.total_recommendations ?? 0;
                        const clusters = report?.cluster_count ?? 0;
                        const pairs = report?.remaining_pair_count ?? 0;
                        const highPriority = report?.prioritized_actions.filter(a => a.priority === "high").length ?? 0;
                        const riskLevel = highPriority >= 3 || clusters >= 2 ? "High" : highPriority >= 1 || total >= 3 ? "Moderate" : total === 0 ? "None" : "Low";
                        const riskClass = riskLevel === "High" ? "conf-high" : riskLevel === "Moderate" ? "conf-medium" : riskLevel === "Low" ? "conf-low" : "score-neutral";

                        return (
                          <>
                            <div className="reuse-summary-cards">
                              <div className="reuse-summary-card">
                                <span className={`score-chip ${riskClass}`}>{riskLevel} risk</span>
                                <span className="reuse-card-label">Redundancy level</span>
                              </div>
                              <div className="reuse-summary-card">
                                <strong className="reuse-card-num">{total}</strong>
                                <span className="reuse-card-label">Total opportunities</span>
                              </div>
                              <div className="reuse-summary-card">
                                <strong className="reuse-card-num">{clusters}</strong>
                                <span className="reuse-card-label">Model clusters</span>
                              </div>
                              <div className="reuse-summary-card">
                                <strong className="reuse-card-num">{pairs}</strong>
                                <span className="reuse-card-label">Duplicate pairs</span>
                              </div>
                            </div>

                            {total === 0 ? (
                              <div className="scan-clean" style={{ marginTop: 12 }}>
                                No material redundancy found at the current similarity threshold.
                              </div>
                            ) : (
                              <div className="reuse-queue-list" style={{ marginTop: 12 }}>
                                {report!.prioritized_actions.map((action, idx) => (
                                  <div key={`reuse-${idx}`} className="reuse-queue-card">
                                    <div className="reuse-queue-top">
                                      <span className={`score-chip ${priorityTone(action.priority)}`}>
                                        {action.priority} priority
                                      </span>
                                      <span className={`score-chip ${confidenceTone(action.confidence_band)}`}>
                                        {action.confidence_band} confidence
                                      </span>
                                      <span className="score-chip score-neutral">
                                        {action.recommendation_type === "cluster" ? "cluster" : "pair"}
                                      </span>
                                      {action.recommendation_type === "pair" && typeof action.similarity_score === "number" && (
                                        <span className="score-chip score-neutral">
                                          score {action.similarity_score.toFixed(2)}
                                        </span>
                                      )}
                                      {action.recommendation_type === "cluster" && typeof action.cluster_average_score === "number" && (
                                        <span className="score-chip score-neutral">
                                          avg {action.cluster_average_score.toFixed(2)}
                                        </span>
                                      )}
                                    </div>
                                    <p className="reuse-queue-summary">{action.summary}</p>
                                    {!!action.model_names.length && (
                                      <div className="cluster-model-list">
                                        {action.model_names.map(m => (
                                          <span key={m} className="score-chip score-neutral">{m}</span>
                                        ))}
                                      </div>
                                    )}
                                    <div className="similarity-grid">
                                      {!!action.shared_inputs?.length && (
                                        <div><span>Shared inputs</span><p>{action.shared_inputs.join(", ")}</p></div>
                                      )}
                                      {!!action.shared_selected_columns?.length && (
                                        <div><span>Shared columns</span><p>{action.shared_selected_columns.join(", ")}</p></div>
                                      )}
                                      {!!action.shared_aggregates?.length && (
                                        <div><span>Shared aggregates</span><p>{action.shared_aggregates.join(", ")}</p></div>
                                      )}
                                      {!!action.shared_filters?.length && (
                                        <div><span>Shared filters</span><p>{action.shared_filters.join(", ")}</p></div>
                                      )}
                                    </div>
                                    {action.suggested_shared_model && (
                                      <p className="similarity-suggested">
                                        Suggested shared model: <code>{action.suggested_shared_model}</code>
                                      </p>
                                    )}
                                  </div>
                                ))}
                              </div>
                            )}
                          </>
                        );
                      })()}
                    </div>
                  )}
                </div>
              )}

              <div className="panel-header">
                <div>
                  <div className="panel-kicker-row">
                    <span className="panel-kicker" style={{ color: activeCategory.accent }}>
                      {activeCategory.title}
                    </span>
                    {activeCategory.key === "naming" && (
                      <span
                        ref={namingIconRef}
                        className={`info-icon-wrap${namingInfoOpen ? " info-locked" : ""}`}
                        onClick={() => {
                          if (namingInfoOpen) {
                            setNamingInfoOpen(false);
                          } else {
                            const rect = namingIconRef.current?.getBoundingClientRect();
                            if (rect) setNamingInfoPos({ top: rect.bottom + 8, left: rect.left });
                            setNamingInfoOpen(true);
                          }
                        }}
                        title={namingInfoOpen ? undefined : "Click to learn how naming rules are enforced"}
                      >
                        <span className="info-icon">i</span>
                      </span>
                    )}
                    {activeCategory.key === "structure" && (
                      <span
                        ref={structureIconRef}
                        className={`info-icon-wrap${structureInfoOpen ? " info-locked" : ""}`}
                        onClick={() => {
                          if (structureInfoOpen) {
                            setStructureInfoOpen(false);
                          } else {
                            const rect = structureIconRef.current?.getBoundingClientRect();
                            if (rect) setStructureInfoPos({ top: rect.bottom + 8, left: rect.left });
                            setStructureInfoOpen(true);
                          }
                        }}
                        title={structureInfoOpen ? undefined : "Click to learn how structure rules are enforced"}
                      >
                        <span className="info-icon">i</span>
                      </span>
                    )}
                    {activeCategory.key === "testing" && (
                      <span
                        ref={testingIconRef}
                        className={`info-icon-wrap${testingInfoOpen ? " info-locked" : ""}`}
                        onClick={() => {
                          if (testingInfoOpen) {
                            setTestingInfoOpen(false);
                          } else {
                            const rect = testingIconRef.current?.getBoundingClientRect();
                            if (rect) setTestingInfoPos({ top: rect.bottom + 8, left: rect.left });
                            setTestingInfoOpen(true);
                          }
                        }}
                        title={testingInfoOpen ? undefined : "Click to learn how testing rules are enforced"}
                      >
                        <span className="info-icon">i</span>
                      </span>
                    )}
                    {activeCategory.key === "documentation" && (
                      <span
                        ref={documentationIconRef}
                        className={`info-icon-wrap${documentationInfoOpen ? " info-locked" : ""}`}
                        onClick={() => {
                          if (documentationInfoOpen) {
                            setDocumentationInfoOpen(false);
                          } else {
                            const rect = documentationIconRef.current?.getBoundingClientRect();
                            if (rect) setDocumentationInfoPos({ top: rect.bottom + 8, left: rect.left });
                            setDocumentationInfoOpen(true);
                          }
                        }}
                        title={documentationInfoOpen ? undefined : "Click to learn how documentation rules are enforced"}
                      >
                        <span className="info-icon">i</span>
                      </span>
                    )}
                    {activeCategory.key === "materialization" && (
                      <span
                        ref={materializationIconRef}
                        className={`info-icon-wrap${materializationInfoOpen ? " info-locked" : ""}`}
                        onClick={() => {
                          if (materializationInfoOpen) {
                            setMaterializationInfoOpen(false);
                          } else {
                            const rect = materializationIconRef.current?.getBoundingClientRect();
                            if (rect) setMaterializationInfoPos({ top: rect.bottom + 8, left: rect.left });
                            setMaterializationInfoOpen(true);
                          }
                        }}
                        title={materializationInfoOpen ? undefined : "Click to learn how materialization rules are enforced"}
                      >
                        <span className="info-icon">i</span>
                      </span>
                    )}
                    {activeCategory.key === "style" && (
                      <span
                        ref={styleIconRef}
                        className={`info-icon-wrap${styleInfoOpen ? " info-locked" : ""}`}
                        onClick={() => {
                          if (styleInfoOpen) {
                            setStyleInfoOpen(false);
                          } else {
                            const rect = styleIconRef.current?.getBoundingClientRect();
                            if (rect) setStyleInfoPos({ top: rect.bottom + 8, left: rect.left });
                            setStyleInfoOpen(true);
                          }
                        }}
                        title={styleInfoOpen ? undefined : "Click to learn how SQL style rules are enforced"}
                      >
                        <span className="info-icon">i</span>
                      </span>
                    )}
                  </div>
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
                  <div className="panel-kicker-row">
                    <span className="panel-kicker">Generated Artifacts</span>
                    <span
                      ref={artifactsIconRef}
                      className={`info-icon-wrap${artifactsInfoOpen ? " info-locked" : ""}`}
                      onClick={() => {
                        if (artifactsInfoOpen) {
                          setArtifactsInfoOpen(false);
                        } else {
                          const rect = artifactsIconRef.current?.getBoundingClientRect();
                          if (rect) setArtifactsInfoPos({ top: rect.bottom + 8, left: rect.left });
                          setArtifactsInfoOpen(true);
                        }
                      }}
                      title={artifactsInfoOpen ? undefined : "What is this section?"}
                    >
                      <span className="info-icon">i</span>
                    </span>
                  </div>
                  <h2>Live previews and downloads</h2>
                </div>
                <div className="chip-row">
                  {(["yaml", "review", "claude", "copilot"] as PreviewMode[]).map((mode) => (
                    <button
                      key={mode}
                      className={mode === previewMode ? "chip active" : "chip"}
                      onClick={() => setPreviewMode(mode)}
                    >
                      {mode === "yaml"
                        ? ".dbt-governance.yml"
                        : mode === "review"
                        ? "REVIEW.md"
                        : mode === "copilot"
                        ? "copilot-instructions.md"
                        : aiMdName}
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
                <button className="primary-button secondary" onClick={() => downloadFile(aiMdName, aiMdPreview)}>
                  Download {aiMdName}
                </button>
                <button className="primary-button secondary" onClick={() => downloadFile("copilot-instructions.md", copilotMdPreview)}>
                  Download copilot-instructions.md
                </button>
                {scanResult && (
                  <button
                    className="primary-button secondary"
                    onClick={() => downloadFile("REUSE_REPORT.md", reuseReportMarkdown(scanResult))}
                  >
                    Download REUSE_REPORT.md
                  </button>
                )}
                <button className="ghost-button" onClick={copyPreview}>
                  {copiedLabel || "Copy active preview"}
                </button>
              </div>

              {!scanResult && (
                <p className="artifact-note">
                  Run a scan to unlock <code className="inline-code">REUSE_REPORT.md</code>, a ranked handoff report for consolidation work.
                </p>
              )}

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

              <div className="scan-launcher">
                {/* Mode toggle */}
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

                {/* Cloud: project → environment selection */}
                {scanMode === "cloud" && (
                  <>
                    {!cloudConfigured ? (
                      <div className="scan-hint warn-card">
                        <strong>Account not configured.</strong>{" "}
                        <button className="inline-link" onClick={() => setShowSettings(true)}>
                          Open Settings
                        </button>{" "}
                        to enter your dbt Cloud account ID and API token.
                      </div>
                    ) : cloudEnvFetch === "loading" ? (
                      <p className="env-picker-hint">Loading environments…</p>
                    ) : cloudEnvFetch !== "done" ? (
                      <div className="env-picker-fetch-row">
                        <button className="ghost-button" onClick={fetchCloudEnvironments}>
                          Load environments from dbt Cloud
                        </button>
                        {cloudEnvFetch === "error" && (
                          <span className="env-picker-error">{cloudEnvError}</span>
                        )}
                      </div>
                    ) : (
                      <>
                        {/* Step 1: Choose a project */}
                        <div className="scan-step">
                          <div className="scan-step-header">
                            <span className="scan-step-num">1</span>
                            <span className="scan-step-title">Choose a project</span>
                          </div>
                          <div className="project-picker">
                            {uniqueProjects.map(p => (
                              <button
                                key={p.id}
                                className={`project-card${selectedProjectId === p.id ? " project-card-active" : ""}`}
                                onClick={() => {
                                  setSelectedProjectId(p.id);
                                  const projEnvs = cloudEnvs.filter(e => e.project_id === p.id);
                                  const prodIds = new Set(projEnvs.filter(e => isProdEnv(e.name)).map(e => e.id));
                                  setSelectedEnvIds(prodIds.size > 0 ? prodIds : new Set(projEnvs.map(e => e.id)));
                                }}
                              >
                                {p.name}
                                <span className="project-card-count">
                                  {cloudEnvs.filter(e => e.project_id === p.id).length} env{cloudEnvs.filter(e => e.project_id === p.id).length !== 1 ? "s" : ""}
                                </span>
                              </button>
                            ))}
                            {uniqueProjects.length > 1 && (
                              <button
                                className={`project-card project-card-all${!selectedProjectId ? " project-card-active" : ""}`}
                                onClick={() => {
                                  setSelectedProjectId(null);
                                  const allProdIds = new Set(cloudEnvs.filter(e => isProdEnv(e.name)).map(e => e.id));
                                  setSelectedEnvIds(allProdIds.size > 0 ? allProdIds : new Set(cloudEnvs.map(e => e.id)));
                                }}
                              >
                                All projects
                                <span className="project-card-count">{cloudEnvs.length} envs</span>
                              </button>
                            )}
                          </div>
                        </div>

                        {/* Step 2: Choose environments */}
                        <div className="scan-step">
                          <div className="scan-step-header">
                            <span className="scan-step-num">2</span>
                            <span className="scan-step-title">
                              {selectedProjectId
                                ? `Environments in ${selectedProjectName}`
                                : "Choose environments"}
                            </span>
                            <div className="env-filter-row">
                              <button className="env-filter-btn" onClick={selectProdEnvs}>★ Prod only</button>
                              <button className="env-filter-btn" onClick={selectAllEnvs}>All</button>
                              <button className="env-filter-btn" onClick={clearEnvs}>None</button>
                            </div>
                          </div>
                          <div className="env-checklist">
                            {filteredEnvs.map(env => {
                              const isProd = isProdEnv(env.name);
                              const isDev = env.type === "development";
                              return (
                                <label
                                  key={env.id}
                                  className={`env-check-row${isProd ? " env-is-prod" : ""}${selectedEnvIds.has(env.id) ? " env-checked" : ""}`}
                                >
                                  <input
                                    type="checkbox"
                                    checked={selectedEnvIds.has(env.id)}
                                    onChange={(e) => toggleEnv(env.id, e.target.checked)}
                                  />
                                  <span className="env-check-body">
                                    <span className="env-check-name">{env.name}</span>
                                    {!selectedProjectId && (
                                      <span className="env-check-project">{env.project_name}</span>
                                    )}
                                  </span>
                                  {isProd && <span className="env-badge-prod">prod</span>}
                                  <span className={`env-badge-type${isDev ? " env-badge-dev" : ""}`}>
                                    {env.type}
                                  </span>
                                  <span className="env-check-id">#{env.id}</span>
                                </label>
                              );
                            })}
                          </div>
                          <div className="env-multiselect-footer">
                            <span className="env-count">
                              {selectedEnvIds.size} of {filteredEnvs.length} environment{filteredEnvs.length !== 1 ? "s" : ""} selected
                            </span>
                            <button className="ghost-button small" onClick={fetchCloudEnvironments}>↻ Refresh</button>
                          </div>
                          {/* Warn if any selected env is a development environment */}
                          {Array.from(selectedEnvIds).some(id => {
                            const env = cloudEnvs.find(e => e.id === id);
                            return env?.type === "development";
                          }) && (
                            <div className="env-dev-warning">
                              <strong>⚠ Development environment selected</strong>
                              <p>
                                The dbt Cloud Discovery API only covers <strong>deployment</strong> environments
                                with at least one successful job run. Scanning a development environment will
                                fail with "No data available". Select a deployment environment instead.
                              </p>
                            </div>
                          )}
                        </div>
                      </>
                    )}
                  </>
                )}

                {/* Local mode: manifest path + project dir */}
                {scanMode === "local" && (
                  <>
                    <label className="scan-field">
                      <span>Path to manifest.json</span>
                      <input
                        value={manifestPath}
                        onChange={(e) => setManifestPath(e.target.value)}
                        placeholder="target/manifest.json"
                      />
                    </label>
                    <label className="scan-field">
                      <span>dbt project directory <span className="scan-field-hint">(optional — needed if manifest was built with dbt Fusion/Cloud CLI)</span></span>
                      <input
                        value={projectDir}
                        onChange={(e) => setProjectDir(e.target.value)}
                        placeholder="e.g. demo-project"
                      />
                    </label>
                  </>
                )}

                <label className="scan-ai-toggle">
                  <input
                    type="checkbox"
                    checked={withAiScan}
                    onChange={(e) => setWithAiScan(e.target.checked)}
                  />
                  <span>
                    Enable AI review{" "}
                    <span className="scan-hint-inline">(requires API key for selected provider)</span>
                  </span>
                </label>

                <button
                  className="primary-button scan-run-btn"
                  onClick={runScan}
                  disabled={isScanning || !isDownloadReady || (scanMode === "cloud" && !cloudConfigured)}
                >
                  {isScanning ? (
                    <span className="scan-spinner">Scanning…</span>
                  ) : scanMode === "cloud" && cloudEnvFetch === "done" && selectedEnvIds.size > 0 ? (
                    `Scan ${selectedEnvIds.size} environment${selectedEnvIds.size !== 1 ? "s" : ""}${selectedProjectId ? ` in ${selectedProjectName}` : " across all projects"} →`
                  ) : (
                    "Run Scan →"
                  )}
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

                  {scanResult.violations.some((v) => v.rule_id === "reuse.model_similarity_clusters") && (
                    <div className="cluster-summary-banner">
                      <strong>
                        {scanResult.violations.filter((v) => v.rule_id === "reuse.model_similarity_clusters").length}{" "}
                        reuse cluster
                        {scanResult.violations.filter((v) => v.rule_id === "reuse.model_similarity_clusters").length === 1 ? "" : "s"}{" "}
                        found
                      </strong>
                      <p>
                        Start with the cluster cards below. They tell you when several models should share one intermediate,
                        which is usually the fastest way to cut migration redundancy.
                      </p>
                    </div>
                  )}

                  {scanResult.reuse_report && scanResult.reuse_report.total_recommendations > 0 && (
                    <div className="reuse-queue">
                      <div className="reuse-queue-header">
                        <div>
                          <p className="panel-kicker">Reuse Action Queue</p>
                          <h3>Work the highest-value consolidation opportunities first</h3>
                        </div>
                        <div className="reuse-queue-metrics">
                          <span className="score-chip score-neutral">
                            {scanResult.reuse_report.cluster_count} cluster
                            {scanResult.reuse_report.cluster_count === 1 ? "" : "s"}
                          </span>
                          <span className="score-chip score-neutral">
                            {scanResult.reuse_report.remaining_pair_count} remaining pair
                            {scanResult.reuse_report.remaining_pair_count === 1 ? "" : "s"}
                          </span>
                        </div>
                      </div>

                      <div className="reuse-queue-list">
                        {scanResult.reuse_report.prioritized_actions.map((action, idx) => (
                          <div key={`${action.recommendation_type}-${idx}`} className="reuse-queue-card">
                            <div className="reuse-queue-top">
                              <span className={`score-chip ${priorityTone(action.priority)}`}>
                                {action.priority} priority
                              </span>
                              <span className={`score-chip ${confidenceTone(action.confidence_band)}`}>
                                {action.confidence_band} confidence
                              </span>
                              <span className="score-chip score-neutral">
                                {action.recommendation_type === "cluster" ? "cluster" : "pair"}
                              </span>
                              {action.recommendation_type === "cluster" &&
                                typeof action.cluster_average_score === "number" && (
                                  <span className="score-chip score-neutral">
                                    avg {action.cluster_average_score.toFixed(2)}
                                  </span>
                                )}
                              {action.recommendation_type === "pair" &&
                                typeof action.similarity_score === "number" && (
                                  <span className="score-chip score-neutral">
                                    score {action.similarity_score.toFixed(2)}
                                  </span>
                                )}
                            </div>
                            <p className="reuse-queue-summary">{action.summary}</p>
                            {!!action.model_names.length && (
                              <div className="cluster-model-list">
                                {action.model_names.map((model) => (
                                  <span key={model} className="score-chip score-neutral">{model}</span>
                                ))}
                              </div>
                            )}
                            <div className="similarity-grid">
                              {!!action.shared_inputs?.length && (
                                <div><span>Shared inputs</span><p>{action.shared_inputs.join(", ")}</p></div>
                              )}
                              {!!action.shared_selected_columns?.length && (
                                <div><span>Shared columns</span><p>{action.shared_selected_columns.join(", ")}</p></div>
                              )}
                              {!!action.shared_aggregates?.length && (
                                <div><span>Shared aggregates</span><p>{action.shared_aggregates.join(", ")}</p></div>
                              )}
                              {!!action.shared_filters?.length && (
                                <div><span>Shared filters</span><p>{action.shared_filters.join(", ")}</p></div>
                              )}
                            </div>
                            {!!action.example_pairs?.length && (
                              <div className="cluster-examples">
                                <span>Why this cluster ranks highly</span>
                                <p>
                                  {action.example_pairs
                                    .map((pair) => {
                                      const left = String(pair.left_model_name ?? "");
                                      const right = String(pair.right_model_name ?? "");
                                      const score = Number(pair.similarity_score ?? 0);
                                      return `${left} ↔ ${right} (${score.toFixed(2)})`;
                                    })
                                    .join(" · ")}
                                </p>
                              </div>
                            )}
                            {action.suggested_shared_model && (
                              <p className="similarity-suggested">
                                Suggested shared model: <code>{action.suggested_shared_model}</code>
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

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
                          {v.rule_id === "reuse.model_similarity_clusters" && v.details && (
                            <div className="similarity-card cluster-card">
                              <div className="similarity-header">
                                <span className={`score-chip ${confidenceTone(v.details.confidence_band)}`}>
                                  {v.details.confidence_band ?? "unknown"} confidence
                                </span>
                                {typeof v.details.cluster_average_score === "number" && (
                                  <span className="score-chip score-neutral">
                                    avg similarity {v.details.cluster_average_score.toFixed(2)}
                                  </span>
                                )}
                                {typeof v.details.cluster_peak_score === "number" && (
                                  <span className="score-chip score-neutral">
                                    peak {v.details.cluster_peak_score.toFixed(2)}
                                  </span>
                                )}
                              </div>
                              <p className="similarity-pair">
                                Cluster:{" "}
                                <strong>{v.details.cluster_models?.join(", ") ?? v.model_name}</strong>
                              </p>
                              {!!v.details.cluster_models?.length && (
                                <div className="cluster-model-list">
                                  {v.details.cluster_models.map((model) => (
                                    <span key={model} className="score-chip score-neutral">{model}</span>
                                  ))}
                                </div>
                              )}
                              <div className="similarity-grid">
                                {!!v.details.shared_inputs?.length && (
                                  <div><span>Shared inputs</span><p>{v.details.shared_inputs.join(", ")}</p></div>
                                )}
                                {!!v.details.shared_selected_columns?.length && (
                                  <div><span>Shared columns</span><p>{v.details.shared_selected_columns.join(", ")}</p></div>
                                )}
                                {!!v.details.shared_aggregates?.length && (
                                  <div><span>Shared aggregates</span><p>{v.details.shared_aggregates.join(", ")}</p></div>
                                )}
                                {!!v.details.shared_filters?.length && (
                                  <div><span>Shared filters</span><p>{v.details.shared_filters.join(", ")}</p></div>
                                )}
                              </div>
                              {!!v.details.cluster_example_pairs?.length && (
                                <div className="cluster-examples">
                                  <span>Strongest pair links</span>
                                  <p>
                                    {v.details.cluster_example_pairs
                                      .map(
                                        (pair) =>
                                          `${pair.left_model_name} ↔ ${pair.right_model_name} (${pair.similarity_score.toFixed(2)})`
                                      )
                                      .join(" · ")}
                                  </p>
                                </div>
                              )}
                              {v.details.suggested_shared_model && (
                                <p className="similarity-suggested">
                                  Suggested shared model: <code>{v.details.suggested_shared_model}</code>
                                </p>
                              )}
                            </div>
                          )}
                          {v.rule_id === "reuse.model_similarity_candidates" && v.details && (
                            <div className="similarity-card">
                              <div className="similarity-header">
                                <span className={`score-chip ${confidenceTone(v.details.confidence_band)}`}>
                                  {v.details.confidence_band ?? "unknown"} confidence
                                </span>
                                {typeof v.details.similarity_score === "number" && (
                                  <span className="score-chip score-neutral">
                                    similarity {v.details.similarity_score.toFixed(2)}
                                  </span>
                                )}
                              </div>
                              <p className="similarity-pair">
                                Pair: <strong>{v.model_name}</strong> and{" "}
                                <strong>{v.details.paired_model_name ?? "another model"}</strong>
                              </p>
                              <div className="similarity-grid">
                                {!!v.details.shared_inputs?.length && (
                                  <div><span>Shared inputs</span><p>{v.details.shared_inputs.join(", ")}</p></div>
                                )}
                                {!!v.details.shared_selected_columns?.length && (
                                  <div><span>Shared columns</span><p>{v.details.shared_selected_columns.join(", ")}</p></div>
                                )}
                                {!!v.details.shared_aggregates?.length && (
                                  <div><span>Shared aggregates</span><p>{v.details.shared_aggregates.join(", ")}</p></div>
                                )}
                                {!!v.details.shared_filters?.length && (
                                  <div><span>Shared filters</span><p>{v.details.shared_filters.join(", ")}</p></div>
                                )}
                              </div>
                              {v.details.suggested_shared_model && (
                                <p className="similarity-suggested">
                                  Suggested shared model: <code>{v.details.suggested_shared_model}</code>
                                </p>
                              )}
                            </div>
                          )}
                          {v.suggestion && <p className="violation-suggestion">→ {v.suggestion}</p>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

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
                      <span className="file-badge">{aiMdName}</span>
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
                    {scanMode === "cloud" && cloudEnvFetch === "done" && selectedEnvIds.size > 0 ? (
                      <>
                        <p>One command per selected environment:</p>
                        {Array.from(selectedEnvIds).map((id) => {
                          const env = cloudEnvs.find(e => e.id === id);
                          const cmd = `dbt-governance scan --cloud --environment-id ${id}`;
                          return (
                            <div key={id} className="cmd-block" style={{ marginBottom: 6 }}>
                              <span className="cmd-env-label">
                                {env?.name ?? `env ${id}`}{isProdEnv(env?.name ?? "") ? " ★" : ""}
                              </span>
                              <code>{cmd}</code>
                              <button className="cmd-copy" onClick={() => copyCommand(cmd, `env-${id}`)}>
                                {copiedCommand === `env-${id}` ? "Copied!" : "Copy"}
                              </button>
                            </div>
                          );
                        })}
                      </>
                    ) : (
                      <>
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
                      </>
                    )}
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
              {activeTab === "reuse" && (
                <>
                  <strong>Find the redundancy</strong>
                  <p>After a legacy migration, teams typically have 3-5x more staging models than they need. Start with the balanced preset, then review high-confidence similarity pairs first.</p>
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
                      ? `Your dbt Cloud connection is configured (account ${config.dbt_cloud.account_id}${config.dbt_cloud.environment_id > 0 ? `, env ${config.dbt_cloud.environment_id}` : " — all environments"}). Hit Run Scan to see live violations.`
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
                <span className="info-icon-wrap">
                  <span className="info-icon">i</span>
                  <div className="info-tooltip">
                    <strong>Four files are generated:</strong>
                    <ul>
                      <li>
                        <strong>.dbt-governance.yml</strong> — the machine-readable ruleset. Commit to your repo root; the scanner and CI job read this to enforce rules.
                      </li>
                      <li>
                        <strong>REVIEW.md</strong> — a plain-English checklist for human PR reviewers. Not read by AI tools.
                      </li>
                      <li>
                        <strong>{aiMdName}</strong> — instructions for Claude Code (CLAUDE.md) or Gemini CLI (GEMINI.md). Read automatically on every PR so generated code respects your conventions.
                      </li>
                      <li>
                        <strong>copilot-instructions.md</strong> — instructions for GitHub Copilot Code Review. Must be committed to <code>.github/copilot-instructions.md</code> on the base branch. Hard limit: 4,000 characters (Copilot silently truncates beyond that).
                      </li>
                    </ul>
                  </div>
                </span>
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
            <button className="primary-button secondary" disabled={!isDownloadReady} onClick={() => downloadFile(aiMdName, aiMdPreview)}>
              Download {aiMdName}
            </button>
            <button className="primary-button secondary" disabled={!isDownloadReady} onClick={() => downloadFile("copilot-instructions.md", copilotMdPreview)}>
              Download copilot-instructions.md
            </button>
            {scanResult && (
              <button
                className="primary-button secondary"
                onClick={() => downloadFile("REUSE_REPORT.md", reuseReportMarkdown(scanResult))}
              >
                Download REUSE_REPORT.md
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ─────────────────── Naming info popover (fixed, escapes overflow) ─────────────────── */}
      {namingInfoOpen && namingInfoPos && (
        <div
          ref={namingPopoverRef}
          className="naming-info-popover"
          style={{ top: namingInfoPos.top, left: namingInfoPos.left }}
          onWheel={(e) => e.stopPropagation()}
        >
          <div className="info-tooltip-header">
            <strong>How naming rules are enforced</strong>
            <button
              className="info-tooltip-close"
              onClick={() => setNamingInfoOpen(false)}
              aria-label="Close"
            >✕</button>
          </div>
          <div className="info-tooltip-body">
            <p style={{ marginBottom: 10 }}>
              <strong style={{ display: "inline" }}>Error vs Warning:</strong> when the scanner runs, every violation is printed to the output. Whether it <em>fails the CI check</em> (exits with code 1, blocking the PR) depends on the severity you set here and the <code>fail_on</code> setting in your config (default: <code>error</code>). With the default, <strong>errors block the PR</strong>; warnings are reported but the check still passes.
            </p>
            <p style={{ marginBottom: 10 }}>
              The scanner identifies a model&apos;s layer by its <strong>folder</strong> first (<code>models/staging/</code>, <code>models/intermediate/</code>, <code>models/marts/</code>), then falls back to its <strong>name prefix</strong>. Only models in the matching layer are checked by each rule.
            </p>
            <ul>
              <li>
                <strong>Staging prefix</strong><br />
                Pattern: <code>stg_&lt;source&gt;__&lt;entity&gt;</code> (note: <strong>double underscore</strong>)<br />
                ✓ <code>stg_stripe__payments.sql</code><br />
                ✓ <code>stg_salesforce__accounts.sql</code><br />
                ✗ <code>stripe_payments.sql</code> — no <code>stg_</code> prefix<br />
                ✗ <code>stg_payments.sql</code> — missing source name and double underscore
              </li>
              <li>
                <strong>Intermediate prefix</strong><br />
                Pattern: <code>int_&lt;entity&gt;_&lt;verb&gt;</code> — scanner enforces <code>int_</code> prefix only; the <code>&lt;entity&gt;_&lt;verb&gt;</code> part is a team convention, not a regex check.<br />
                ✓ <code>int_orders_pivoted.sql</code><br />
                ✓ <code>int_customers_ranked.sql</code><br />
                ✗ <code>orders_pivoted.sql</code> — no <code>int_</code> prefix
              </li>
              <li>
                <strong>Mart prefix</strong><br />
                Pattern: must start with <code>fct_</code> (fact table) or <code>dim_</code> (dimension).<br />
                ✓ <code>fct_orders.sql</code>, <code>dim_customers.sql</code><br />
                ✗ <code>orders.sql</code>, <code>customer_report.sql</code>
              </li>
              <li>
                <strong>Sources require explicit schema</strong><br />
                Every entry in <code>sources.yml</code> must have a <code>schema:</code> field. Without it, dbt falls back to the default schema, which silently breaks across environments.<br />
                ✓ <code>schema: raw_stripe</code><br />
                ✗ No <code>schema:</code> key at all
              </li>
              <li>
                <strong>SQL filename matches model name</strong><br />
                The filename (without <code>.sql</code>) must match the model name in <code>manifest.json</code>. A mismatch usually means the model was renamed in <code>dbt_project.yml</code> but the file was not.<br />
                ✓ File <code>stg_stripe__payments.sql</code>, model name <code>stg_stripe__payments</code><br />
                ✗ File <code>stg_payments.sql</code>, model name <code>stg_stripe__payments</code>
              </li>
            </ul>
          </div>
        </div>
      )}

      {/* ─────────────────── Structure info popover ─────────────────── */}
      {structureInfoOpen && structureInfoPos && (
        <div
          ref={structurePopoverRef}
          className="naming-info-popover"
          style={{ top: structureInfoPos.top, left: structureInfoPos.left }}
          onWheel={(e) => e.stopPropagation()}
        >
          <div className="info-tooltip-header">
            <strong>What structure rules check</strong>
            <button className="info-tooltip-close" onClick={() => setStructureInfoOpen(false)} aria-label="Close">✕</button>
          </div>
          <div className="info-tooltip-body">
            <p style={{ marginBottom: 10 }}>
              <strong style={{ display: "inline" }}>Background — the three layers:</strong> a well-run dbt project moves data through three stages. <strong>Staging</strong> models clean up raw source data (one model per source table, no business logic). <strong>Intermediate</strong> models join and transform staging data. <strong>Marts</strong> are the final outputs — the tables and views your dashboards and analysts actually query. Structure rules enforce that data always flows <em>in that order</em> and never skips steps or doubles back.
            </p>
            <p style={{ marginBottom: 10 }}>
              <strong style={{ display: "inline" }}>Error vs Warning:</strong> errors cause the CI scan to exit with a failure code and block the PR. Warnings are printed in the report but the check still passes (unless <code>fail_on</code> is set to <code>warning</code> in your config).
            </p>
            <ul>
              <li>
                <strong>Staging models only reference sources</strong> <em>(Error by default)</em><br />
                A staging model should pull data directly from a raw source table — nothing else. If it references another dbt model, business logic is leaking into the wrong layer.<br />
                ✓ <code>stg_stripe__payments</code> uses <code>source(&apos;stripe&apos;, &apos;payments&apos;)</code><br />
                ✗ <code>stg_stripe__payments</code> uses <code>ref(&apos;some_other_model&apos;)</code>
              </li>
              <li>
                <strong>Mart models never reference sources directly</strong> <em>(Error by default)</em><br />
                A mart should never reach back to raw source data — it should always go through staging and intermediate models. Raw sources are unvalidated; marts are supposed to be trustworthy outputs.<br />
                ✓ <code>fct_orders</code> references <code>ref(&apos;int_orders_enriched&apos;)</code><br />
                ✗ <code>fct_orders</code> references <code>source(&apos;stripe&apos;, &apos;charges&apos;)</code>
              </li>
              <li>
                <strong>Models should not skip layers</strong> <em>(Warning by default)</em><br />
                A mart model jumping straight to a staging model — skipping intermediate — means transformation logic ends up in the wrong place and is hard to reuse.<br />
                ✓ <code>fct_orders</code> → <code>int_orders_pivoted</code> → <code>stg_stripe__payments</code><br />
                ✗ <code>fct_orders</code> → <code>stg_stripe__payments</code> (skipped intermediate)
              </li>
              <li>
                <strong>Limit DAG depth</strong> <em>(Warning by default, configurable)</em><br />
                Counts how many upstream ancestors a model has. A very long chain (default limit: 8) makes it hard to trace where data came from and slows down full refreshes.<br />
                ✗ A model that is 11 hops away from its source tables
              </li>
              <li>
                <strong>Limit downstream fanout</strong> <em>(Warning by default, configurable)</em><br />
                Counts how many other models directly depend on a given model. If one model feeds 15 others (default limit: 10), a change to it is high-risk and hard to test.<br />
                ✗ <code>int_customers_core</code> is referenced directly by 14 downstream models
              </li>
              <li>
                <strong>Flag orphan models</strong> <em>(Info by default)</em><br />
                A model with no downstream consumers and no registered exposure is likely unused dead code — it still runs on every job, costing compute time.<br />
                ✗ <code>old_revenue_calc</code> — nothing references it and it has no exposure
              </li>
              <li>
                <strong>Detect diamond (rejoin) patterns</strong> <em>(Warning by default)</em><br />
                A diamond happens when two different models both trace back to the same common ancestor, then rejoin further downstream. This can cause row duplication that is very hard to spot.<br />
                ✗ <code>fct_revenue</code> joins <code>int_orders_by_region</code> and <code>int_orders_by_product</code>, which both come from <code>stg_stripe__orders</code>
              </li>
              <li>
                <strong>Model directories match layers</strong> <em>(Error by default)</em><br />
                The file&apos;s folder should match its name prefix. A file named <code>stg_*</code> should live under <code>models/staging/</code>. Mismatches confuse the layer detection used by all other rules.<br />
                ✓ <code>models/staging/stg_stripe__payments.sql</code><br />
                ✗ <code>models/marts/stg_stripe__payments.sql</code>
              </li>
            </ul>
          </div>
        </div>
      )}

      {/* ─────────────────── Testing info popover ─────────────────── */}
      {testingInfoOpen && testingInfoPos && (
        <div
          ref={testingPopoverRef}
          className="naming-info-popover"
          style={{ top: testingInfoPos.top, left: testingInfoPos.left }}
          onWheel={(e) => e.stopPropagation()}
        >
          <div className="info-tooltip-header">
            <strong>What testing rules check</strong>
            <button className="info-tooltip-close" onClick={() => setTestingInfoOpen(false)} aria-label="Close">✕</button>
          </div>
          <div className="info-tooltip-body">
            <p style={{ marginBottom: 10 }}>
              <strong style={{ display: "inline" }}>Background — what is a dbt test?</strong> A test is an automated data quality check defined in a YAML file alongside your models. After your models build, dbt runs these checks against the actual data — things like "this column has no duplicates" or "this column is never empty." If a test fails, the job fails. These rules ensure your team writes enough of them.
            </p>
            <p style={{ marginBottom: 10 }}>
              <strong style={{ display: "inline" }}>Error vs Warning:</strong> errors cause the CI scan to exit with a failure code and block the PR. Warnings are reported but do not block the PR by default.
            </p>
            <ul>
              <li>
                <strong>Primary keys require unique + not_null tests</strong> <em>(Error by default)</em><br />
                Every model should have one column that uniquely identifies each row (the primary key). This rule requires two tests on that column: <code>unique</code> (no duplicates) and <code>not_null</code> (no missing values). Without these, duplicate or missing rows can silently corrupt downstream reports.<br />
                ✓ Schema YAML has <code>- unique</code> and <code>- not_null</code> on the <code>order_id</code> column<br />
                ✗ Model has no tests at all, or only one of the two
              </li>
              <li>
                <strong>Minimum tests per model</strong> <em>(Warning by default, configurable)</em><br />
                Sets a floor on the total number of tests a model must have (default: 2). The primary key tests alone satisfy this for most models — the rule is a backstop to prevent models with zero tests from slipping through.<br />
                ✓ Model has 3 tests defined in its schema YAML<br />
                ✗ Model has 0 or 1 test (below the minimum you configure)
              </li>
              <li>
                <strong>Sources feeding staging require freshness checks</strong> <em>(Warning by default)</em><br />
                A freshness check tells dbt to verify that source data was loaded recently. Without it, your pipeline could be running on data that is hours or days old, and nobody would know. This rule flags any source table that feeds a staging model but has no freshness configuration.<br />
                ✓ Source definition includes <code>loaded_at_field: _ingested_at</code> and a freshness warning threshold<br />
                ✗ Source has no <code>loaded_at_field</code> and no freshness block
              </li>
              <li>
                <strong>Mart models should define contracts</strong> <em>(Info by default)</em><br />
                A dbt contract locks down the column names and data types a mart model is allowed to output. If a developer accidentally drops or renames a column, dbt refuses to build the model — protecting dashboards and downstream consumers from silent breaking changes.<br />
                ✓ Model config includes <code>contract: &#123;enforced: true&#125;</code> with all columns typed in the schema YAML<br />
                ✗ Mart model has no contract — column changes go undetected until a dashboard breaks
              </li>
              <li>
                <strong>Disabled tests are flagged</strong> <em>(Warning by default)</em><br />
                Tests can be silenced by setting <code>enabled: false</code> in the model config. This rule flags any model where that has happened, so disabled tests don&apos;t quietly accumulate as unaddressed technical debt.<br />
                ✗ A model has <code>config: &#123;enabled: false&#125;</code> — all its tests are being skipped
              </li>
            </ul>
          </div>
        </div>
      )}

      {/* ─────────────────── Documentation info popover ─────────────────── */}
      {documentationInfoOpen && documentationInfoPos && (
        <div
          ref={documentationPopoverRef}
          className="naming-info-popover"
          style={{ top: documentationInfoPos.top, left: documentationInfoPos.left }}
          onWheel={(e) => e.stopPropagation()}
        >
          <div className="info-tooltip-header">
            <strong>What documentation rules check</strong>
            <button className="info-tooltip-close" onClick={() => setDocumentationInfoOpen(false)} aria-label="Close">✕</button>
          </div>
          <div className="info-tooltip-body">
            <p style={{ marginBottom: 10 }}>
              <strong style={{ display: "inline" }}>Background:</strong> in dbt, documentation lives in YAML files alongside your SQL. A <code>schema.yml</code> file lets you describe what a model does, what each column means, and where source data comes from. Without these descriptions, the only way to understand the warehouse is to read raw SQL — which is not realistic for analysts, stakeholders, or new team members. These rules enforce a minimum documentation floor.
            </p>
            <p style={{ marginBottom: 10 }}>
              <strong style={{ display: "inline" }}>Error vs Warning:</strong> errors block the PR when the CI scan runs. Warnings are reported but do not block by default.
            </p>
            <ul>
              <li>
                <strong>Models require descriptions in key layers</strong> <em>(Error by default)</em><br />
                Intermediate and mart models (configurable) must have a written description in their schema YAML. Staging models are often excluded because they map 1-to-1 with source tables and the source description is sufficient.<br />
                ✓ <code>fct_orders</code> has <code>description: "One row per order, grain is order_id"</code> in its YAML<br />
                ✗ <code>fct_orders</code> has no <code>description:</code> field at all
              </li>
              <li>
                <strong>Mart columns require descriptions</strong> <em>(Warning by default)</em><br />
                Every column listed in a mart&apos;s schema YAML must have a description. Marts are the models analysts query directly — undocumented columns lead to misinterpretation and duplicate calculation logic across teams.<br />
                ✓ Column <code>gross_revenue</code> has <code>description: "Order total before discounts and refunds, in USD"</code><br />
                ✗ Column <code>gross_revenue</code> is listed in the YAML but has no description
              </li>
              <li>
                <strong>Sources require descriptions</strong> <em>(Warning by default)</em><br />
                Every source table defined in <code>sources.yml</code> should have a description explaining what system it comes from and what the data represents. Without this, developers have no way to evaluate whether a source is the right one to use.<br />
                ✓ Source <code>stripe.charges</code> has <code>description: "Raw payment events from the Stripe API, loaded hourly"</code><br />
                ✗ Source <code>stripe.charges</code> has no description
              </li>
              <li>
                <strong>Schema YAML exists per model directory</strong> <em>(Error by default)</em><br />
                Every folder containing SQL models must have at least one schema YAML file in it. A folder with no YAML means none of those models have tests, descriptions, or column definitions — they are completely invisible to governance.<br />
                ✓ <code>models/marts/finance/</code> contains <code>_finance__models.yml</code><br />
                ✗ <code>models/marts/finance/</code> has SQL files but no <code>.yml</code> file
              </li>
            </ul>
          </div>
        </div>
      )}

      {/* ─────────────────── Materialization info popover ─────────────────── */}
      {materializationInfoOpen && materializationInfoPos && (
        <div
          ref={materializationPopoverRef}
          className="naming-info-popover"
          style={{ top: materializationInfoPos.top, left: materializationInfoPos.left }}
          onWheel={(e) => e.stopPropagation()}
        >
          <div className="info-tooltip-header">
            <strong>What materialization rules check</strong>
            <button className="info-tooltip-close" onClick={() => setMaterializationInfoOpen(false)} aria-label="Close">✕</button>
          </div>
          <div className="info-tooltip-body">
            <p style={{ marginBottom: 10 }}>
              <strong style={{ display: "inline" }}>Background — what is a materialization?</strong> When dbt runs, it has to decide how to physically store each model in the database. A <strong>view</strong> stores only the query definition and recomputes on every read — fast to create, always fresh, no storage cost. A <strong>table</strong> physically writes all the rows to disk — slower to build but fast to query. An <strong>incremental</strong> model only processes new or changed rows on each run, which is essential for large datasets. These rules enforce sensible defaults for each layer so performance choices don&apos;t become governance problems.
            </p>
            <p style={{ marginBottom: 10 }}>
              <strong style={{ display: "inline" }}>Error vs Warning:</strong> errors block the PR. Warnings are reported but do not block by default.
            </p>
            <ul>
              <li>
                <strong>Staging models should be views</strong> <em>(Warning by default)</em><br />
                Staging models are just light cleanups of raw source tables. Materializing them as tables wastes storage and compute — you would be writing a full copy of raw data on every job run. Views are the right choice because they stay in sync automatically and cost nothing to store.<br />
                ✓ <code>stg_stripe__payments</code> is materialized as <code>view</code> (set in <code>dbt_project.yml</code> or model config)<br />
                ✗ <code>stg_stripe__payments</code> is materialized as <code>table</code> — full copy rebuilt on every run
              </li>
              <li>
                <strong>Incremental models require a unique_key</strong> <em>(Error by default)</em><br />
                An incremental model appends or merges new rows instead of rebuilding from scratch. Without a <code>unique_key</code>, dbt has no way to match incoming rows to existing ones — it will silently create duplicates every time the job runs.<br />
                ✓ <code>{`{{ config(materialized='incremental', unique_key='event_id') }}`}</code><br />
                ✗ <code>{`{{ config(materialized='incremental') }}`}</code> — no <code>unique_key</code>, duplicates on every run
              </li>
              <li>
                <strong>Incremental models should define on_schema_change</strong> <em>(Warning by default)</em><br />
                When a developer adds a new column to an incremental model, dbt needs to know what to do with the existing table that doesn&apos;t have that column yet. Without this setting, dbt&apos;s default behaviour silently ignores the new column — it simply doesn&apos;t appear in the table until a full refresh is forced.<br />
                ✓ <code>{`{{ config(on_schema_change='append_new_columns') }}`}</code> — new columns are added automatically<br />
                ✗ No <code>on_schema_change</code> — new columns silently dropped until someone notices the data is wrong
              </li>
            </ul>
          </div>
        </div>
      )}

      {/* ─────────────────── SQL Style info popover ─────────────────── */}
      {styleInfoOpen && styleInfoPos && (
        <div
          ref={stylePopoverRef}
          className="naming-info-popover"
          style={{ top: styleInfoPos.top, left: styleInfoPos.left }}
          onWheel={(e) => e.stopPropagation()}
        >
          <div className="info-tooltip-header">
            <strong>What SQL style rules check</strong>
            <button className="info-tooltip-close" onClick={() => setStyleInfoOpen(false)} aria-label="Close">✕</button>
          </div>
          <div className="info-tooltip-body">
            <p style={{ marginBottom: 10 }}>
              <strong style={{ display: "inline" }}>Background:</strong> dbt models are SQL files with a specific structure. These rules enforce patterns that make dbt SQL consistent, readable, and safe across environments — things a generic SQL linter would never catch because they are dbt-specific. The central idea is the <strong>import CTE pattern</strong>: all references to other models (<code>ref()</code>) or sources (<code>source()</code>) are declared at the top of the file as named CTEs, so the transformation logic below can read like plain English.
            </p>
            <p style={{ marginBottom: 10 }}>
              <strong style={{ display: "inline" }}>Error vs Warning:</strong> errors block the PR. Warnings are reported but do not block by default.
            </p>
            <ul>
              <li>
                <strong>Prefer import-then-logical CTE structure</strong> <em>(Warning by default)</em><br />
                All <code>ref()</code> and <code>source()</code> calls should be in CTEs at the top of the file ("import CTEs"), followed by CTEs containing transformation logic. Mixing them makes it hard to see at a glance what data a model depends on.<br />
                ✓ <code>with orders as (select * from {`{{ ref('stg_stripe__orders') }}`}),</code> then later <code>final as (select ... from orders ...)</code><br />
                ✗ A logical CTE appears first, then a <code>ref()</code> CTE appears after it
              </li>
              <li>
                <strong>No hardcoded schema or database references</strong> <em>(Error by default)</em><br />
                Writing <code>FROM prod.finance.orders</code> directly in SQL means the model only works in one environment. In dev or CI, that schema doesn&apos;t exist, so the model fails. All table references must go through <code>{`ref()`}</code> or <code>{`source()`}</code> so dbt can resolve the correct database and schema for each environment automatically.<br />
                ✓ <code>FROM {`{{ ref('stg_stripe__orders') }}`}</code><br />
                ✗ <code>FROM prod.raw_stripe.orders</code> — hardcoded, breaks in dev and CI
              </li>
              <li>
                <strong>No SELECT * in marts</strong> <em>(Warning by default)</em><br />
                Mart models are the final outputs consumed by dashboards and analysts. Using <code>SELECT *</code> means the column list is invisible in the SQL file and will silently change if an upstream model adds or removes columns — breaking dashboards without any warning.<br />
                ✓ <code>SELECT order_id, customer_id, gross_revenue, created_at</code><br />
                ✗ <code>SELECT *</code> in the final SELECT of a mart model
              </li>
              <li>
                <strong>Final SELECT should come from a named CTE</strong> <em>(Warning by default)</em><br />
                The last statement in the file — the one that actually writes data — should reference a CTE by name, not call <code>ref()</code> or <code>source()</code> directly. This keeps the "what does this model output" question separated from the "where does data come from" question.<br />
                ✓ Last line: <code>SELECT * FROM final</code> (where <code>final</code> is a CTE defined above)<br />
                ✗ Last line: <code>SELECT * FROM {`{{ ref('int_orders_enriched') }}`}</code> — no CTE wrapper
              </li>
              <li>
                <strong>Place ref() calls in import CTEs, not inline joins</strong> <em>(Warning by default)</em><br />
                Writing <code>JOIN {`{{ ref('dim_customers') }}`}</code> directly inside the SQL body buries the dependency in the middle of transformation logic, making it hard to see the full list of inputs at a glance and hard to diff in code review.<br />
                ✓ <code>customers as (select * from {`{{ ref('dim_customers') }}`})</code> at the top, then <code>JOIN customers</code> below<br />
                ✗ <code>JOIN {`{{ ref('dim_customers') }}`} ON ...</code> inline in the body
              </li>
            </ul>
          </div>
        </div>
      )}

      {/* ─────────────────── Artifacts info popover ─────────────────── */}
      {artifactsInfoOpen && artifactsInfoPos && (
        <div
          ref={artifactsPopoverRef}
          className="naming-info-popover"
          style={{ top: artifactsInfoPos.top, left: artifactsInfoPos.left }}
          onWheel={(e) => e.stopPropagation()}
        >
          <div className="info-tooltip-header">
            <strong>What is the Generated Artifacts section?</strong>
            <button className="info-tooltip-close" onClick={() => setArtifactsInfoOpen(false)} aria-label="Close">✕</button>
          </div>
          <div className="info-tooltip-body">
            <p style={{ marginBottom: 10 }}>
              This is where your rule configuration gets turned into real files. Everything you toggled — which rules are enabled, their severity levels, any custom thresholds — is reflected here as a live preview. <strong>Nothing is saved or applied until you download and commit these files to your dbt repository.</strong>
            </p>
            <p style={{ marginBottom: 6 }}>
              <strong>What to do in this section:</strong>
            </p>
            <ol style={{ margin: "0 0 12px 0", paddingLeft: 16 }}>
              <li style={{ marginBottom: 6 }}><strong>Preview each file</strong> using the tabs at the top (<code>.dbt-governance.yml</code>, <code>REVIEW.md</code>, <code>CLAUDE.md</code>, <code>copilot-instructions.md</code>).</li>
              <li style={{ marginBottom: 6 }}><strong>Download the files you need</strong> using the buttons above or the bar at the bottom of the page.</li>
              <li style={{ marginBottom: 6 }}><strong>Commit them to the correct location</strong> in your dbt repository — placement matters (see below).</li>
            </ol>
            <p style={{ marginBottom: 6 }}>
              <strong>What each file does and where it goes:</strong>
            </p>
            <ul style={{ margin: "0 0 12px 0", paddingLeft: 16 }}>
              <li style={{ marginBottom: 10 }}>
                <strong>.dbt-governance.yml</strong> — place in the <strong>root of your dbt repo</strong> (same folder as <code>dbt_project.yml</code>). The <code>dbt-governance scan</code> CLI reads this to know which rules to enforce, at what severity, and with what thresholds. Your CI pipeline runs this on every PR and fails the merge if errors are found.
              </li>
              <li style={{ marginBottom: 10 }}>
                <strong>REVIEW.md</strong> — place in the <strong>root of your dbt repo</strong>. A plain-English checklist for human code reviewers. Claude Code Review also reads this automatically on every PR when the action is installed.
              </li>
              <li style={{ marginBottom: 10 }}>
                <strong>CLAUDE.md / GEMINI.md</strong> — place in the <strong>root of your dbt repo</strong>. Read automatically by Claude Code or Google Gemini CLI when a developer opens the repo. Ensures any AI-assisted code already follows your conventions before a reviewer sees it.
              </li>
              <li style={{ marginBottom: 4 }}>
                <strong>copilot-instructions.md</strong> — place at <strong><code>.github/copilot-instructions.md</code></strong> in your dbt repo (the <code>.github/</code> folder in the root, not the repo root itself). GitHub Copilot Code Review reads this file automatically on every pull request and applies your governance rules as inline PR comments — no Actions workflow required. Two things to know:
                <ul style={{ marginTop: 6, paddingLeft: 16 }}>
                  <li style={{ marginBottom: 4 }}><strong>4,000-character limit</strong> — Copilot Code Review only reads the first 4,000 characters of this file. The generated file is kept well under that limit. If you add many custom rules and approach the limit, the file will include a truncation notice.</li>
                  <li><strong>Base branch only</strong> — Copilot reads the instructions from your base branch (e.g. <code>main</code>), not the feature branch. Merge any updates to <code>main</code> before expecting Copilot to apply them on new PRs.</li>
                </ul>
              </li>
            </ul>
            <p style={{ marginBottom: 0, opacity: 0.75, fontSize: "0.7rem" }}>
              Tip: if you change any rules, re-download the relevant files and commit the update. Everything is always regenerated fresh from your current settings.
            </p>
          </div>
        </div>
      )}

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

            {/* ── Configuration Checklist ── */}
            {(() => {
              const hasAccountId = config.dbt_cloud.account_id > 0;
              const hasToken = envVars.DBT_CLOUD_API_TOKEN === true;
              const aiProvider = config.ai_provider.provider;
              const aiEnvKey = aiProvider === "claude" ? "ANTHROPIC_API_KEY" : aiProvider === "openai" ? "OPENAI_API_KEY" : aiProvider === "gemini" ? "GEMINI_API_KEY" : null;
              const hasAiKey = aiEnvKey ? envVars[aiEnvKey] === true : true;
              const items = [
                { ok: config.dbt_cloud.enabled, label: "dbt Cloud mode enabled" },
                { ok: hasAccountId, label: "Account ID", hint: "Enter in dbt Cloud Connection below" },
                { ok: hasToken, label: "DBT_CLOUD_API_TOKEN", hint: "Set in .env file or shell environment" },
                ...(aiProvider !== "none" ? [{ ok: hasAiKey, label: aiEnvKey!, hint: "Set in .env file or shell environment" }] : []),
              ];
              const missingCount = items.filter((i) => !i.ok).length;
              return (
                <div className="drawer-section" style={{ paddingBottom: 10 }}>
                  <div className="config-checklist">
                    <p className="config-checklist-title">
                      {missingCount === 0 ? "✓ All configured — ready to scan" : `${missingCount} item${missingCount > 1 ? "s" : ""} need${missingCount === 1 ? "s" : ""} attention`}
                    </p>
                    {items.map((item) => (
                      <div key={item.label} className={`checklist-item ${item.ok ? "checklist-ok" : "checklist-missing"}`}>
                        <span className="checklist-icon">{item.ok ? "✓" : "!"}</span>
                        <span>
                          {item.label}
                          {!item.ok && item.hint && <> — <span className="checklist-hint">{item.hint}</span></>}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })()}

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

              {/* Env var: DBT_CLOUD_API_TOKEN */}
              <div className="env-row">
                <span className={`env-dot ${envVars.DBT_CLOUD_API_TOKEN ? "env-dot-ok" : "env-dot-missing"}`} />
                <span className="env-key">DBT_CLOUD_API_TOKEN</span>
                <span className={`env-status-text ${envVars.DBT_CLOUD_API_TOKEN ? "ok" : "missing"}`}>
                  {!envLoaded ? "Checking…" : envVars.DBT_CLOUD_API_TOKEN ? "Detected" : "Not found in environment"}
                </span>
              </div>

              <div className="drawer-form-grid">
                <label>
                  <span>
                    Account ID
                    {!config.dbt_cloud.account_id && <span className="field-tag field-tag-missing">Required</span>}
                  </span>
                  <input
                    type="number"
                    placeholder="e.g. 123456"
                    className={!config.dbt_cloud.account_id ? "field-empty" : ""}
                    value={config.dbt_cloud.account_id || ""}
                    onChange={(e) => updateConfig((next) => { next.dbt_cloud.account_id = Number(e.target.value); })}
                  />
                </label>

                {/* Environment picker — replaces raw ID input */}
                <div className="env-picker">
                  <span className="env-picker-label">
                    Environment
                    <span className="field-tag field-tag-optional">Optional</span>
                  </span>
                  {!config.dbt_cloud.account_id || !envVars.DBT_CLOUD_API_TOKEN ? (
                    <p className="env-picker-hint">Enter Account ID and set DBT_CLOUD_API_TOKEN to fetch environments</p>
                  ) : cloudEnvFetch === "done" ? (
                    <>
                      <div className="env-picker-select-row">
                        <select
                          value={config.dbt_cloud.environment_id || 0}
                          onChange={(e) => updateConfig((next) => { next.dbt_cloud.environment_id = Number(e.target.value); })}
                        >
                          <option value={0}>⚠ Scan all environments</option>
                          {cloudEnvs.map((env) => (
                            <option key={env.id} value={env.id}>
                              {env.project_name} · {env.name}{isProdEnv(env.name) ? " ★" : ""} ({env.type}, #{env.id})
                            </option>
                          ))}
                        </select>
                        <button className="ghost-button small" onClick={fetchCloudEnvironments}>↻</button>
                      </div>
                      {config.dbt_cloud.environment_id === 0 && (
                        <p className="env-all-warning">
                          ⚠ Scanning all environments queries every environment in your account. This may take several minutes and consume significant Discovery API quota. Select a specific environment for regular scans.
                        </p>
                      )}
                    </>
                  ) : cloudEnvFetch === "loading" ? (
                    <p className="env-picker-hint">Fetching environments…</p>
                  ) : (
                    <div className="env-picker-fetch-row">
                      <button className="ghost-button small" onClick={fetchCloudEnvironments}>
                        Fetch environments
                      </button>
                      {cloudEnvFetch === "error" && (
                        <span className="env-picker-error">{cloudEnvError}</span>
                      )}
                    </div>
                  )}
                </div>
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
                {!envVars.DBT_CLOUD_API_TOKEN && envLoaded && (
                  <strong style={{ color: "var(--accent-orange)", display: "block", marginBottom: 4 }}>
                    ⚠ Token not detected — the scanner will fail without it.
                  </strong>
                )}
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
                {config.ai_provider.provider !== "none" && envLoaded && (() => {
                  const key = config.ai_provider.provider === "claude" ? "ANTHROPIC_API_KEY" : config.ai_provider.provider === "openai" ? "OPENAI_API_KEY" : "GEMINI_API_KEY";
                  const found = envVars[key];
                  return (
                    <>
                      <span className={`conn-dot ${found ? "conn-ok" : "conn-off"}`} />
                      <span className="conn-label">{found ? "Key detected" : "Key missing"}</span>
                    </>
                  );
                })()}
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
                    {/* Env var status for AI key */}
                    {(() => {
                      const key = config.ai_provider.provider === "claude" ? "ANTHROPIC_API_KEY" : config.ai_provider.provider === "openai" ? "OPENAI_API_KEY" : "GEMINI_API_KEY";
                      return (
                        <div className="env-row" style={{ gridColumn: "1 / -1" }}>
                          <span className={`env-dot ${envVars[key] ? "env-dot-ok" : "env-dot-missing"}`} />
                          <span className="env-key">{key}</span>
                          <span className={`env-status-text ${envVars[key] ? "ok" : "missing"}`}>
                            {!envLoaded ? "Checking…" : envVars[key] ? "Detected" : "Not found in environment"}
                          </span>
                        </div>
                      );
                    })()}
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

              {config.ai_provider.provider !== "none" && envLoaded && (() => {
                const key = config.ai_provider.provider === "claude" ? "ANTHROPIC_API_KEY" : config.ai_provider.provider === "openai" ? "OPENAI_API_KEY" : "GEMINI_API_KEY";
                return !envVars[key] ? (
                  <div className="drawer-hint">
                    <strong style={{ color: "var(--accent-orange)", display: "block", marginBottom: 4 }}>
                      ⚠ {key} not detected — AI review will fail without it.
                    </strong>
                    Set <code className="inline-code">{key}</code> in your <code className="inline-code">.env</code> file or shell environment.
                    AI review runs only when <code className="inline-code">--with-ai</code> is passed to the scanner.
                  </div>
                ) : (
                  <div className="drawer-hint">
                    AI review runs only when <code className="inline-code">--with-ai</code> is passed or the AI toggle is enabled in Run Scan.
                  </div>
                );
              })()}
            </div>

            {/* ── AI Review Prompt ── */}
            {config.ai_provider.provider !== "none" && (
              <div className="drawer-section">
                <div className="drawer-section-header">
                  <span className="drawer-section-icon">✦</span>
                  <strong>AI Review Prompt</strong>
                </div>
                <p className="drawer-hint" style={{ marginBottom: 10 }}>
                  This is the system prompt sent to the AI on every model review. Add your own rules below — they are appended verbatim after the default instructions and exported in your <code className="inline-code">.dbt-governance.yml</code>.
                </p>

                {/* Default prompt — read-only, collapsible */}
                <details className="prompt-preview-details">
                  <summary className="prompt-preview-summary">View default system prompt</summary>
                  <pre className="prompt-preview-body">{`You are an expert dbt analytics engineer performing code review on dbt SQL models.
Your job is to identify governance violations — patterns that indicate poor practices,
maintenance risks, or architectural problems in dbt projects.

Respond ONLY with valid JSON in this exact format (no markdown, no prose):
{
  "violations": [
    {
      "rule_id": "<ai.rule_name>",
      "severity": "<error|warning|info>",
      "message": "<specific, actionable description of the problem>",
      "suggestion": "<concrete fix recommendation>"
    }
  ]
}

If no violations are found, return: {"violations": []}

Available rule IDs (use the best match, or ai.general for anything else):
- ai.business_logic_in_staging   — staging model applies business filters, joins, or
                                    aggregations that belong in an intermediate or mart model
- ai.complex_model_should_split  — model is doing too many things and should be broken
                                    into smaller intermediate steps
- ai.misleading_description      — the model or column description does not accurately
                                    reflect what the SQL actually computes
- ai.hardcoded_values            — magic numbers, hardcoded dates, status strings, or
                                    environment-specific schema names embedded in SQL
- ai.poor_cte_structure          — CTEs are poorly named, redundant, or structured in a
                                    way that hides logic
- ai.missing_column_context      — a column performs a complex calculation but has no
                                    description to explain its business meaning
- ai.general                     — any other significant quality or maintainability concern

Severity guide:
- error: blocks understanding or correctness
- warning: significant smell that should be fixed
- info: low-priority improvement

Be specific: quote the actual SQL or column name in your message when relevant.
Only flag real issues — do not invent violations for well-written code.`}</pre>
                </details>

                <label className="drawer-label-block" style={{ marginTop: 12 }}>
                  <span>Custom instructions <span className="field-tag-optional">optional</span></span>
                  <textarea
                    className="prompt-custom-textarea"
                    rows={6}
                    placeholder={`Add your team's specific rules here. For example:\n- Flag any model that uses DISTINCT without a comment explaining why\n- Warn when a mart model has more than 20 columns without a description\n- Error on any use of SELECT * in production models`}
                    value={config.ai_provider.additional_instructions}
                    onChange={(e) =>
                      updateConfig((next) => { next.ai_provider.additional_instructions = e.target.value; })
                    }
                  />
                  <span className="drawer-field-hint">
                    Plain text. Each line is a rule or instruction. Appended after the default prompt above.
                  </span>
                </label>
              </div>
            )}

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
                      <polygon points="0 0, 8 3, 0 6" fill="#94A3B8" />
                    </marker>
                  </defs>

                  {/* Central Governance */}
                  <rect x="280" y="18" width="200" height="44" rx="10" fill="rgba(245,158,11,0.08)" stroke="#F59E0B" strokeWidth="1.5" />
                  <text x="380" y="36" textAnchor="middle" fontFamily="system-ui,-apple-system,sans-serif" fontSize="12" fontWeight="600" fill="#1A1A2E">Central Governance</text>
                  <text x="380" y="53" textAnchor="middle" fontFamily="system-ui,-apple-system,sans-serif" fontSize="10" fill="#64748B">this app — configure your standards</text>

                  {/* Arrow: Central Governance → config files */}
                  <line x1="380" y1="62" x2="380" y2="80" stroke="#94A3B8" strokeWidth="1.5" markerEnd="url(#ah)" />
                  <text x="392" y="75" fontFamily="system-ui,-apple-system,sans-serif" fontSize="9" fill="#94A3B8">Download 3 files</text>

                  {/* Config files box */}
                  <rect x="160" y="82" width="440" height="58" rx="10" fill="rgba(255,255,255,0.72)" stroke="rgba(15,23,42,0.14)" strokeWidth="1.5" />
                  <text x="380" y="104" textAnchor="middle" fontFamily="system-ui,-apple-system,sans-serif" fontSize="11.5" fontWeight="600" fill="#1A1A2E">.dbt-governance.yml  ·  REVIEW.md  ·  CLAUDE.md</text>
                  <text x="380" y="121" textAnchor="middle" fontFamily="system-ui,-apple-system,sans-serif" fontSize="10" fill="#64748B">Commit all three to the root of your dbt repo</text>
                  <text x="380" y="134" textAnchor="middle" fontFamily="system-ui,-apple-system,sans-serif" fontSize="9.5" fill="#D97706">One-time manual step — everything else is automated</text>

                  {/* Arrow: config → repo */}
                  <line x1="380" y1="140" x2="380" y2="160" stroke="#94A3B8" strokeWidth="1.5" markerEnd="url(#ah)" />

                  {/* dbt repo */}
                  <rect x="280" y="162" width="200" height="40" rx="10" fill="rgba(13,148,136,0.08)" stroke="#0D9488" strokeWidth="1.5" />
                  <text x="380" y="179" textAnchor="middle" fontFamily="system-ui,-apple-system,sans-serif" fontSize="12" fontWeight="600" fill="#1A1A2E">Your dbt repo</text>
                  <text x="380" y="195" textAnchor="middle" fontFamily="system-ui,-apple-system,sans-serif" fontSize="9.5" fill="#64748B">GitHub / GitLab / Bitbucket</text>

                  {/* Branch lines from repo */}
                  <line x1="380" y1="202" x2="380" y2="216" stroke="#94A3B8" strokeWidth="1.5" />
                  <line x1="175" y1="216" x2="585" y2="216" stroke="#94A3B8" strokeWidth="1" strokeDasharray="4,3" />
                  <line x1="175" y1="216" x2="175" y2="246" stroke="#94A3B8" strokeWidth="1.5" markerEnd="url(#ah)" />
                  <line x1="585" y1="216" x2="585" y2="246" stroke="#94A3B8" strokeWidth="1.5" markerEnd="url(#ah)" />
                  <text x="175" y="234" textAnchor="middle" fontFamily="system-ui,-apple-system,sans-serif" fontSize="9" fill="#94A3B8">On every PR</text>
                  <text x="585" y="234" textAnchor="middle" fontFamily="system-ui,-apple-system,sans-serif" fontSize="9" fill="#94A3B8">On every PR</text>

                  {/* Left: GitHub Actions / scan */}
                  <rect x="28" y="248" width="294" height="98" rx="10" fill="rgba(255,105,74,0.06)" stroke="#FF694A" strokeWidth="1.5" />
                  <text x="42" y="270" fontFamily="system-ui,-apple-system,sans-serif" fontSize="11" fontWeight="700" fill="#FF694A">GitHub Actions  (setup required)</text>
                  <text x="42" y="288" fontFamily="system-ui,-apple-system,sans-serif" fontSize="10.5" fontWeight="600" fill="#1A1A2E">dbt-governance scan</text>
                  <text x="42" y="305" fontFamily="system-ui,-apple-system,sans-serif" fontSize="10" fill="#64748B">· 30+ deterministic rules, runs in ~60s</text>
                  <text x="42" y="320" fontFamily="system-ui,-apple-system,sans-serif" fontSize="10" fill="#64748B">· SARIF output → inline PR annotations</text>
                  <text x="42" y="335" fontFamily="system-ui,-apple-system,sans-serif" fontSize="10" fill="#64748B">· Fails CI on error-severity violations</text>

                  {/* Right: Claude Code Review */}
                  <rect x="438" y="248" width="294" height="98" rx="10" fill="rgba(245,158,11,0.06)" stroke="#F59E0B" strokeWidth="1.5" />
                  <text x="452" y="270" fontFamily="system-ui,-apple-system,sans-serif" fontSize="11" fontWeight="700" fill="#D97706">Claude Code Review  (optional)</text>
                  <text x="452" y="288" fontFamily="system-ui,-apple-system,sans-serif" fontSize="10.5" fontWeight="600" fill="#1A1A2E">Reads REVIEW.md + CLAUDE.md</text>
                  <text x="452" y="305" fontFamily="system-ui,-apple-system,sans-serif" fontSize="10" fill="#64748B">· Semantic judgment on every PR</text>
                  <text x="452" y="320" fontFamily="system-ui,-apple-system,sans-serif" fontSize="10" fill="#64748B">· Catches what static rules miss</text>
                  <text x="452" y="335" fontFamily="system-ui,-apple-system,sans-serif" fontSize="10" fill="#64748B">· Inline comments with context and fixes</text>

                  {/* Data source arrow */}
                  <line x1="130" y1="356" x2="130" y2="348" stroke="#94A3B8" strokeWidth="1" markerEnd="url(#ah)" strokeDasharray="3,2" />

                  {/* Data sources */}
                  <rect x="28" y="358" width="152" height="26" rx="6" fill="rgba(255,255,255,0.65)" stroke="rgba(15,23,42,0.1)" strokeWidth="1" />
                  <text x="104" y="375" textAnchor="middle" fontFamily="system-ui,-apple-system,sans-serif" fontSize="9.5" fill="#1A1A2E" fontWeight="500">dbt Cloud API</text>
                  <text x="194" y="375" textAnchor="middle" fontFamily="system-ui,-apple-system,sans-serif" fontSize="9" fill="#94A3B8">or</text>
                  <rect x="208" y="358" width="126" height="26" rx="6" fill="rgba(255,255,255,0.65)" stroke="rgba(15,23,42,0.1)" strokeWidth="1" strokeDasharray="4,2" />
                  <text x="271" y="375" textAnchor="middle" fontFamily="system-ui,-apple-system,sans-serif" fontSize="9.5" fill="#64748B">manifest.json (local)</text>

                  {/* Claude requires ANTHROPIC_API_KEY */}
                  <rect x="438" y="358" width="294" height="26" rx="6" fill="rgba(245,158,11,0.05)" stroke="rgba(245,158,11,0.18)" strokeWidth="1" />
                  <text x="585" y="375" textAnchor="middle" fontFamily="system-ui,-apple-system,sans-serif" fontSize="9.5" fill="#94A3B8">Requires: ANTHROPIC_API_KEY in repo secrets</text>
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
