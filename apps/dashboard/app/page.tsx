"use client";

import { motion, type Variants } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
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

  return (
    <main className="min-h-screen bg-white text-slate-900">
      {/* ── Top navigation ─────────────────────────────── */}
      <nav className="nav-shell sticky top-0 z-40">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3 lg:px-10">
          <div className="flex items-center gap-3">
            <Image
              src="/secureloop-logo.png"
              alt="SecureLoop"
              width={1024}
              height={559}
              priority
              className="h-9 w-auto"
            />
            <span className="hidden md:inline text-[10px] font-semibold uppercase tracking-[0.28em] text-slate-400 border-l border-slate-200 pl-3 ml-1">
              Dashboard
            </span>
          </div>
          <div className="flex items-center gap-3">
            <span
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] font-semibold ${
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

      <div className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-6 py-10 lg:px-10">
        {/* ── Incident Command Center (full-width single box) ── */}
        <motion.section
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          className="hero-shell p-8 lg:p-10"
        >
          <div className="hero-grid" aria-hidden />
          <div className="relative flex flex-col gap-8 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-2xl">
              <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">
                <span className="inline-flex h-1.5 w-1.5 rounded-full bg-slate-900" />
                SecureLoop · Control Plane
              </div>
              <h1 className="mt-4 text-4xl font-bold tracking-tight text-slate-900 sm:text-[44px] leading-[1.05]">
                Incident Command Center
              </h1>
              <p className="mt-4 text-[15px] leading-7 text-slate-600">
                A single pane of glass for every Sentry incident routed through
                SecureLoop. Raw incidents stream in, the JetBrains plugin
                handles human review, and Codex analysis plus approved fixes
                flow through this dashboard in real time.
              </p>

              <div className="mt-7 flex flex-wrap items-center gap-2">
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
                  Launch IDE
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

            {/* Meta panel (base url + last sync) */}
            <div className="shrink-0 rounded-xl border border-slate-200 bg-white/60 px-5 py-4 lg:min-w-[260px]">
              <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.24em] text-slate-400">
                <Terminal className="h-3 w-3" />
                Agent Endpoint
              </div>
              <code className="mt-2 block font-mono text-[12px] text-slate-700 break-all">
                {agentBaseUrl}
              </code>
              <div className="mt-4 flex items-center justify-between text-[11px] text-slate-500">
                <span className="uppercase tracking-[0.22em] text-slate-400">
                  Last sync
                </span>
                <span className="font-mono tabular-nums text-slate-700">
                  {lastSyncLabel ?? "—"}
                </span>
              </div>
            </div>
          </div>

          {error ? (
            <div className="relative mt-6 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-[13px] text-red-700">
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
          className="grid gap-4 lg:grid-cols-[minmax(260px,320px)_1fr]"
        >
          {/* Compact Agent Status strip */}
          <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50/60 px-4 py-3">
            <div
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
                agentOk
                  ? "bg-emerald-100 text-emerald-600"
                  : "bg-slate-200 text-slate-500"
              }`}
            >
              <Activity className="h-4 w-4" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-[0.24em] text-slate-400">
                  Agent Status
                </span>
                <span
                  className={`inline-flex h-1.5 w-1.5 rounded-full ${
                    agentOk ? "bg-emerald-500 pulse-live" : "bg-slate-400"
                  }`}
                  style={{ color: agentOk ? "#059669" : "#94a3b8" }}
                />
              </div>
              <div className="mt-0.5 truncate text-sm font-semibold text-slate-900">
                {agentOk ? "Connected" : "Unavailable"}
              </div>
            </div>
            <div className="flex shrink-0 flex-col items-end gap-1">
              <span className="text-[9px] font-semibold uppercase tracking-[0.2em] text-slate-400">
                Debug
              </span>
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                  health?.allowDebugEndpoints
                    ? "bg-emerald-50 text-emerald-600 border border-emerald-200"
                    : "bg-slate-100 text-slate-500 border border-slate-200"
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
          className="flex items-center gap-4"
        >
          <div className="flex items-center gap-2.5 rounded-full border border-slate-200 bg-white px-3.5 py-1.5">
            <span className="rec-dot inline-flex h-2 w-2 rounded-full bg-red-500" />
            <span className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-700">
              Incident Feed
            </span>
            <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-red-500">
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
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 lg:px-10">
          <p className="text-[11px] font-medium text-slate-500">
            SecureLoop · Built for JBHack
          </p>
          <p className="text-[11px] text-slate-400">
            Auto-Scribe AI SRE Agent
          </p>
        </div>
      </footer>
    </main>
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
