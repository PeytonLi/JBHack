"use client";

import { motion, type Variants } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Moon,
  RefreshCw,
  Sun,
  Terminal,
  Trash2,
  Zap,
} from "lucide-react";
import Image from "next/image";
import { useCallback, useEffect, useMemo, useState } from "react";
import { IncidentStream } from "./incident-stream";
import type {
  AgentHealthResponse,
  AgentStatusResponse,
  DeleteIncidentsResponse,
  IncidentFeedResponse,
  IncidentRecord,
} from "./types";

const agentBaseUrl =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_SECURE_LOOP_AGENT_URL?.trim() ||
      "http://127.0.0.1:8001")
    : "http://127.0.0.1:8001";

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 16 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] as const },
  },
};

type DashboardData = {
  health: AgentHealthResponse | null;
  feed: IncidentFeedResponse | null;
  status: AgentStatusResponse | null;
  error: string | null;
};

type ThemeMode = "dark" | "light";

export default function Home() {
  const [data, setData] = useState<DashboardData>({
    health: null,
    feed: null,
    status: null,
    error: null,
  });
  const [loading, setLoading] = useState(true);
  const [clearing, setClearing] = useState<"open" | "reviewed" | null>(null);
  const [liveRecords, setLiveRecords] = useState<IncidentRecord[]>([]);
  const [lastSyncAt, setLastSyncAt] = useState<number | null>(null);
  const [themeMode, setThemeMode] = useState<ThemeMode>("dark");

  const fetchData = useCallback(async () => {
    try {
      const [healthRes, feedRes, statusRes] = await Promise.all([
        fetch(`${agentBaseUrl}/health`, {
          cache: "no-store",
          headers: { Accept: "application/json" },
        }),
        fetch(`${agentBaseUrl}/incidents?status=all&limit=40`, {
          cache: "no-store",
          headers: { Accept: "application/json" },
        }),
        fetch(`${agentBaseUrl}/status`, {
          cache: "no-store",
          headers: { Accept: "application/json" },
        }),
      ]);

      if (!healthRes.ok || !feedRes.ok) {
        setData({
          health: null,
          feed: null,
          status: null,
          error: `Agent responded with HTTP ${healthRes.status}/${feedRes.status}`,
        });
      } else {
        setData({
          health: (await healthRes.json()) as AgentHealthResponse,
          feed: (await feedRes.json()) as IncidentFeedResponse,
          status: statusRes.ok
            ? ((await statusRes.json()) as AgentStatusResponse)
            : null,
          error: null,
        });
        setLastSyncAt(Date.now());
      }
    } catch {
      setData({
        health: null,
        feed: null,
        status: null,
        error: "Cannot reach SecureLoop agent — start `pnpm dev` first.",
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    const stored = window.localStorage.getItem("secureloop-theme");
    if (stored === "dark" || stored === "light") {
      setThemeMode(stored);
    }
  }, []);

  useEffect(() => {
    document.documentElement.dataset.secureloopTheme = themeMode;
    document.body.dataset.secureloopTheme = themeMode;
    document.body.style.backgroundColor =
      themeMode === "dark" ? "#080a09" : "#fbfcfe";
    document.body.style.color = themeMode === "dark" ? "#f7f7f4" : "#0f172a";
  }, [themeMode]);

  const toggleTheme = useCallback(() => {
    setThemeMode((current) => {
      const next = current === "dark" ? "light" : "dark";
      window.localStorage.setItem("secureloop-theme", next);
      return next;
    });
  }, []);

  const clearIncidents = useCallback(
    async (status: "open" | "reviewed") => {
      const label = status === "open" ? "open" : "reviewed";
      if (
        typeof window !== "undefined" &&
        !window.confirm(`Remove all ${label} incidents from the queue?`)
      ) {
        return;
      }
      setClearing(status);
      try {
        const res = await fetch(
          `${agentBaseUrl}/incidents?status=${status}`,
          { method: "DELETE", headers: { Accept: "application/json" } },
        );
        if (!res.ok) {
          throw new Error(`Agent responded with HTTP ${res.status}`);
        }
        (await res.json()) as DeleteIncidentsResponse;
        await fetchData();
      } catch {
        setData((prev) => ({
          ...prev,
          error: `Failed to clear ${label} incidents.`,
        }));
      } finally {
        setClearing(null);
      }
    },
    [fetchData],
  );

  const { health, feed, status, error } = data;
  const autopilotEnabled = Boolean(status?.autopilotEnabled);

  const openCount = liveRecords.filter((r) => r.status === "open").length;
  const reviewedCount = liveRecords.filter(
    (r) => r.status === "reviewed",
  ).length;
  const totalCount = liveRecords.length;

  const displayOpen = totalCount > 0 ? openCount : (feed?.summary.openCount ?? 0);
  const displayReviewed =
    totalCount > 0 ? reviewedCount : (feed?.summary.reviewedCount ?? 0);
  const displayTotal = totalCount > 0 ? totalCount : (feed?.summary.totalCount ?? 0);

  const total = Math.max(displayTotal, 1);
  const openPct = Math.round((displayOpen / total) * 100);
  const reviewedPct = Math.round((displayReviewed / total) * 100);

  const lastSyncLabel = useMemo(() => {
    if (!lastSyncAt) return null;
    const date = new Date(lastSyncAt);
    return date.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }, [lastSyncAt]);

  const agentOk = health?.status === "ok";
  const isDarkTheme = themeMode === "dark";

  return (
    <main
      data-theme={themeMode}
      className={`${isDarkTheme ? "secureloop-stage" : "bg-[#fbfcfe]"} min-h-screen text-slate-900`}
      style={{
        background: isDarkTheme ? "#080a09" : "#fbfcfe",
        color: isDarkTheme ? "#f7f7f4" : "#0f172a",
      }}
    >
      {/* ── Top navigation ─────────────────────────────── */}
      <nav className="nav-shell sticky top-0 z-40">
        <div className="mx-auto flex max-w-[1540px] items-center justify-between px-6 py-4 lg:px-10">
          <div className="flex items-center gap-3">
            <div className="logo-tile">
              <Image
                src="/secureloop-logo.png"
                alt="SecureLoop"
                width={1024}
                height={559}
                priority
                className="h-8 w-auto"
              />
            </div>
            <span className="hidden border-l border-slate-200 pl-4 text-[12px] font-semibold uppercase text-slate-500 md:inline">
              Autopilot
            </span>
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={toggleTheme}
              className="btn"
              aria-label={`Switch to ${isDarkTheme ? "light" : "dark"} theme`}
            >
              {isDarkTheme ? (
                <Sun className="h-3.5 w-3.5" />
              ) : (
                <Moon className="h-3.5 w-3.5" />
              )}
              {isDarkTheme ? "Light" : "Dark"}
            </button>
            <span
              className={`inline-flex items-center gap-2 rounded-lg border px-3.5 py-2 text-[12px] font-semibold ${
                agentOk
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                  : "border-slate-200 bg-slate-50 text-slate-500"
              }`}
            >
              <span
                style={{ color: agentOk ? "#059669" : "#94a3b8" }}
                className={`h-1.5 w-1.5 rounded-full ${
                  agentOk ? "pulse-live bg-emerald-500" : "bg-slate-400"
                }`}
              />
              {agentOk ? "Agent Online" : "Agent Offline"}
            </span>
          </div>
        </div>
      </nav>

      <div className="mx-auto flex w-full max-w-[1540px] flex-col gap-7 px-6 py-8 lg:px-10">
        {/* ── Autopilot Control Plane ─────────────────── */}
        <motion.section
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          className="hero-shell p-9 lg:p-12"
        >
          <div className="hero-grid" aria-hidden />
          <div className="relative grid gap-10 lg:grid-cols-[1.05fr_0.95fr] lg:items-start">
            <div>
              <div className="flex items-center gap-2 text-[12px] font-bold uppercase text-slate-500">
                <span className="inline-flex h-2 w-2 rounded-full bg-red-500" />
                SecureLoop · Autopilot
              </div>
              <h1 className="mt-5 max-w-4xl text-[48px] font-black leading-[0.98] text-slate-950 sm:text-[64px]">
                Production alerts, patched before the handoff.
              </h1>
              <p className="mt-5 max-w-3xl text-[18px] leading-8 text-slate-600">
                Sentry fires, SecureLoop pulls the source, Codex writes the
                smallest policy-aware fix, sandbox tests verify it, and
                JetBrains keeps the human approval gate in the IDE.
              </p>

              <div className="mt-8 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={() => {
                    setLoading(true);
                    fetchData();
                  }}
                  className="btn btn-primary"
                >
                  <RefreshCw
                    className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`}
                  />
                  Refresh
                </button>
                <a
                  className="btn"
                  href="https://www.jetbrains.com/help/idea/run-debug-configuration-gradle.html"
                  target="_blank"
                  rel="noreferrer"
                >
                  <Zap className="h-3.5 w-3.5" />
                  IDE Setup
                </a>
                <button
                  type="button"
                  onClick={() => clearIncidents("open")}
                  disabled={clearing !== null || displayOpen === 0}
                  className="btn btn-danger"
                >
                  <Trash2
                    className={`h-3.5 w-3.5 ${clearing === "open" ? "animate-pulse" : ""}`}
                  />
                  Clear Open
                </button>
                <button
                  type="button"
                  onClick={() => clearIncidents("reviewed")}
                  disabled={clearing !== null || displayReviewed === 0}
                  className="btn btn-success"
                >
                  <Trash2
                    className={`h-3.5 w-3.5 ${clearing === "reviewed" ? "animate-pulse" : ""}`}
                  />
                  Clear Reviewed
                </button>
              </div>
            </div>

            <DemoLoop
              agentBaseUrl={agentBaseUrl}
              autopilotEnabled={autopilotEnabled}
              codexAvailable={Boolean(status?.codexAvailable)}
              lastSyncLabel={lastSyncLabel}
            />
          </div>

          {error ? (
            <div className="relative mt-8 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-[14px] font-semibold text-red-700">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              {error}
            </div>
          ) : null}
        </motion.section>

        {/* ── Agent Status + Stat tiles row ─────────────── */}
        <motion.section
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          className="grid gap-4 lg:grid-cols-[minmax(320px,430px)_1fr]"
        >
          {/* Compact Agent Status strip */}
          <div className="flex items-center gap-4 rounded-lg border border-slate-200 bg-white px-5 py-5 shadow-sm shadow-slate-200/40">
            <div
              className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-lg ${
                agentOk
                  ? "bg-emerald-100 text-emerald-600"
                  : "bg-slate-200 text-slate-500"
              }`}
            >
              <Activity className="h-5 w-5" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-bold uppercase text-slate-400">
                  Agent Status
                </span>
                <span
                  className={`inline-flex h-1.5 w-1.5 rounded-full ${
                    agentOk ? "bg-emerald-500 pulse-live" : "bg-slate-400"
                  }`}
                  style={{ color: agentOk ? "#059669" : "#94a3b8" }}
                />
              </div>
              <div className="mt-1 truncate text-[18px] font-black text-slate-950">
                {agentOk ? "Connected" : "Unavailable"}
              </div>
            </div>
            <div className="flex shrink-0 flex-col items-end gap-1">
              <span className="text-[10px] font-bold uppercase text-slate-400">
                Debug
              </span>
              <span
                className={`rounded-lg border px-2.5 py-1 text-[11px] font-semibold ${
                  health?.allowDebugEndpoints
                    ? "border-emerald-200 bg-emerald-50 text-emerald-600"
                    : "border-slate-200 bg-slate-100 text-slate-500"
                }`}
              >
                {health?.allowDebugEndpoints ? "On" : "Off"}
              </span>
            </div>
          </div>

          {/* Unique stat tiles */}
          <div className="grid gap-3 sm:grid-cols-3">
            <StatTile
              label="Open"
              value={displayOpen}
              tone="danger"
              meterPct={openPct}
              Icon={AlertTriangle}
              caption={`${openPct}% of total`}
            />
            <StatTile
              label="Reviewed"
              value={displayReviewed}
              tone="success"
              meterPct={reviewedPct}
              Icon={CheckCircle2}
              caption={`${reviewedPct}% of total`}
            />
            <StatTile
              label="Total"
              value={displayTotal}
              tone="neutral"
              Icon={Activity}
              caption="All time"
              split={{ open: displayOpen, reviewed: displayReviewed }}
            />
          </div>
        </motion.section>

        {/* ── Incident Feed header (recording indicator) ── */}
        <motion.section
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          className="flex items-center gap-4 pt-2"
        >
          <div className="flex items-center gap-2.5 rounded-lg border border-slate-200 bg-white px-4 py-2 shadow-sm shadow-slate-200/40">
            <span className="rec-dot inline-flex h-2 w-2 rounded-full bg-red-500" />
            <span className="text-[12px] font-black uppercase text-slate-700">
              Incident Feed
            </span>
            <span className="text-[11px] font-bold uppercase text-red-500">
              Recording
            </span>
          </div>
          <div className="h-px flex-1 bg-slate-200" />
          <span className="font-mono text-[11px] text-slate-500 tabular-nums">
            {displayTotal.toString().padStart(3, "0")} logs
          </span>
        </motion.section>

        {/* ── Incident stream ───────────────────────────── */}
        <IncidentStream
          initialFeed={feed}
          agentBaseUrl={agentBaseUrl}
          autopilotEnabled={autopilotEnabled}
          onRecordsChange={setLiveRecords}
        />
      </div>

      {/* ── Footer ────────────────────────────────────── */}
      <footer className="border-t border-slate-200 bg-slate-50/50 py-6">
        <div className="mx-auto flex max-w-[1540px] items-center justify-between px-6 lg:px-10">
          <p className="text-[11px] font-medium text-slate-500">
            SecureLoop · Built for JBHack
          </p>
          <p className="text-[11px] text-slate-400">
            Codex-in-IDE remediation loop
          </p>
        </div>
      </footer>
    </main>
  );
}

function DemoLoop({
  agentBaseUrl,
  autopilotEnabled,
  codexAvailable,
  lastSyncLabel,
}: {
  agentBaseUrl: string;
  autopilotEnabled: boolean;
  codexAvailable: boolean;
  lastSyncLabel: string | null;
}) {
  const steps: Array<{
    label: string;
    body: string;
    Icon: typeof Activity;
    tone: string;
  }> = [
    {
      label: "Sentry",
      body: "Production alert lands with stack trace and file path.",
      Icon: AlertTriangle,
      tone: "text-red-600 bg-red-50 border-red-200",
    },
    {
      label: "Codex",
      body: "Policy-aware diagnosis and minimal patch are generated.",
      Icon: Zap,
      tone: "text-sky-700 bg-sky-50 border-sky-200",
    },
    {
      label: "Sandbox",
      body: "Generated pytest proves the failure, then proves the fix.",
      Icon: Activity,
      tone: "text-amber-700 bg-amber-50 border-amber-200",
    },
    {
      label: "JetBrains",
      body: "Developer approves the diff in the IDE before shipping.",
      Icon: CheckCircle2,
      tone: "text-emerald-700 bg-emerald-50 border-emerald-200",
    },
  ];

  return (
    <div className="lg:border-l lg:border-slate-200 lg:pl-9">
      <div className="flex items-center justify-between gap-4">
        <div>
          <div className="text-[12px] font-black uppercase text-slate-400">
            Live Remediation Loop
          </div>
          <div className="mt-1 text-[24px] font-black text-slate-950">
            Alert to PR, with proof.
          </div>
        </div>
        <span
          className={`inline-flex items-center rounded-lg border px-3 py-2 text-[12px] font-black ${
            autopilotEnabled
              ? "border-emerald-200 bg-emerald-50 text-emerald-700"
              : "border-amber-200 bg-amber-50 text-amber-700"
          }`}
        >
          {autopilotEnabled ? "Autopilot Active" : "Autopilot Standby"}
        </span>
      </div>

      <div className="mt-6 grid gap-3">
        {steps.map((step, index) => (
          <div
            key={step.label}
            className="grid grid-cols-[42px_1fr] items-start gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm shadow-slate-200/40"
          >
            <div
              className={`flex h-9 w-9 items-center justify-center rounded-lg border ${step.tone}`}
            >
              <step.Icon className="h-4 w-4" />
            </div>
            <div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-[13px] font-black text-slate-950">
                  {index + 1}. {step.label}
                </span>
                <span className="font-mono text-[11px] text-slate-400">
                  {index === 0 ? "trigger" : "auto"}
                </span>
              </div>
              <p className="mt-1 text-[13px] leading-5 text-slate-600">
                {step.body}
              </p>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <StatusPill
          label="Codex"
          value={codexAvailable ? "Ready" : "Offline"}
          active={codexAvailable}
        />
        <StatusPill
          label="Last Sync"
          value={lastSyncLabel ?? "Pending"}
          active={Boolean(lastSyncLabel)}
        />
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-slate-500">
          <div className="flex items-center gap-1.5 text-[9px] font-bold uppercase text-slate-400">
            <Terminal className="h-3 w-3" />
            Agent
          </div>
          <code className="mt-1 block truncate font-mono text-[11px] font-semibold text-slate-700">
            {agentBaseUrl.replace("http://", "")}
          </code>
        </div>
      </div>
    </div>
  );
}

function StatusPill({
  label,
  value,
  active,
}: {
  label: string;
  value: string;
  active: boolean;
}) {
  return (
    <div
      className={`rounded-lg border px-3 py-2 ${
        active
          ? "border-emerald-200 bg-emerald-50 text-emerald-700"
          : "border-slate-200 bg-slate-50 text-slate-500"
      }`}
    >
      <div className="text-[9px] font-bold uppercase text-slate-400">
        {label}
      </div>
      <div className="mt-0.5 font-mono text-[12px] font-black">{value}</div>
    </div>
  );
}

/* ── Stat tile ─────────────────────────────────────────── */
type StatTileProps = {
  label: string;
  value: number;
  tone: "danger" | "success" | "neutral";
  meterPct?: number;
  Icon: typeof Activity;
  caption?: string;
  split?: { open: number; reviewed: number };
};

function StatTile({
  label,
  value,
  tone,
  meterPct,
  Icon,
  caption,
  split,
}: StatTileProps) {
  const toneColor =
    tone === "danger"
      ? "#dc2626"
      : tone === "success"
        ? "#059669"
        : "#0f172a";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      className="stat-tile"
      style={{ color: toneColor }}
    >
      <div className="flex items-center gap-2">
        <Icon className="h-3.5 w-3.5" strokeWidth={2.25} />
        <span className="text-[10px] font-semibold uppercase tracking-[0.24em] text-slate-500">
          {label}
        </span>
      </div>
      <motion.div
        key={value}
        initial={{ scale: 0.92, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 320, damping: 22 }}
        className="mt-3 text-[40px] font-bold tabular-nums leading-none"
        style={{ color: toneColor }}
      >
        {value}
      </motion.div>

      {split ? (
        <div className="mt-4 space-y-2">
          <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full bg-red-500 transition-all"
              style={{
                width: `${split.open + split.reviewed > 0 ? (split.open / (split.open + split.reviewed)) * 100 : 0}%`,
              }}
            />
            <div
              className="h-full bg-emerald-500 transition-all"
              style={{
                width: `${split.open + split.reviewed > 0 ? (split.reviewed / (split.open + split.reviewed)) * 100 : 0}%`,
              }}
            />
          </div>
          <div className="flex items-center justify-between text-[10px] text-slate-500">
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-red-500" />
              {split.open} open
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              {split.reviewed} reviewed
            </span>
          </div>
        </div>
      ) : (
        <div className="mt-5 space-y-2">
          <div className="meter">
            <div
              className="meter-fill"
              style={{ width: `${meterPct ?? 0}%`, background: toneColor }}
            />
          </div>
          {caption ? (
            <p className="text-[10px] font-medium text-slate-500">{caption}</p>
          ) : null}
        </div>
      )}
    </motion.div>
  );
}
