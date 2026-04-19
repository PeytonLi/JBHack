"use client";

import { motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  RefreshCw,
  Shield,
  Trash2,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
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

/* ── animation orchestration ──────────────────────────── */
const stagger = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.1, delayChildren: 0.15 } },
};

const fadeUp = {
  hidden: { opacity: 0, y: 24, filter: "blur(6px)" },
  visible: {
    opacity: 1,
    y: 0,
    filter: "blur(0px)",
    transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1] },
  },
};

const scaleIn = {
  hidden: { opacity: 0, scale: 0.92 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] },
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

  // Compute live stats from the records (SSE-updated)
  const openCount = liveRecords.filter((r) => r.status === "open").length;
  const reviewedCount = liveRecords.filter((r) => r.status === "reviewed").length;
  const totalCount = liveRecords.length;

  // Use live counts if available, fall back to feed summary
  const displayOpen = totalCount > 0 ? openCount : (feed?.summary.openCount ?? 0);
  const displayReviewed = totalCount > 0 ? reviewedCount : (feed?.summary.reviewedCount ?? 0);
  const displayTotal = totalCount > 0 ? totalCount : (feed?.summary.totalCount ?? 0);

  const stats = [
    {
      label: "Open",
      value: displayOpen,
      icon: AlertTriangle,
      color: "text-red-400",
      glow: "rgba(239, 68, 68, 0.15)",
      gradient: "from-red-500/20 to-red-900/10",
    },
    {
      label: "Reviewed",
      value: displayReviewed,
      icon: CheckCircle2,
      color: "text-emerald-400",
      glow: "rgba(16, 185, 129, 0.15)",
      gradient: "from-emerald-500/20 to-emerald-900/10",
    },
    {
      label: "Total",
      value: displayTotal,
      icon: Activity,
      color: "text-cyan-400",
      glow: "rgba(34, 211, 238, 0.15)",
      gradient: "from-cyan-500/20 to-cyan-900/10",
    },
  ];

  return (
    <main className="relative min-h-screen bg-[#050a18] text-slate-100">
      {/* ── Background gradient orbs ──────────────────── */}
      <div className="gradient-orb gradient-orb-cyan w-[600px] h-[600px] -top-[200px] -left-[100px] fixed" />
      <div
        className="gradient-orb gradient-orb-violet w-[500px] h-[500px] top-[40%] -right-[150px] fixed"
        style={{ animationDelay: "-7s" }}
      />
      <div
        className="gradient-orb gradient-orb-rose w-[400px] h-[400px] bottom-[10%] left-[30%] fixed"
        style={{ animationDelay: "-14s" }}
      />

      {/* ── Subtle grid pattern ───────────────────────── */}
      <div
        className="fixed inset-0 pointer-events-none z-0"
        style={{
          backgroundImage:
            "linear-gradient(rgba(255,255,255,0.015) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.015) 1px, transparent 1px)",
          backgroundSize: "64px 64px",
        }}
      />

      {/* ── Top nav bar ───────────────────────────────── */}
      <motion.nav
        initial={{ opacity: 0, y: -16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        className="fixed top-0 left-0 right-0 z-50 border-b border-white/[0.06]"
      >
        <div className="nav-glass mx-auto flex items-center justify-between max-w-7xl px-6 py-3 lg:px-10">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500/20 to-violet-500/20 border border-cyan-500/20">
              <Shield className="w-4 h-4 text-cyan-400" />
            </div>
            <span className="text-sm font-bold tracking-tight text-white">
              SecureLoop
            </span>
            <span className="hidden sm:inline text-[0.6rem] font-semibold uppercase tracking-[0.2em] text-slate-600 ml-1">
              Dashboard
            </span>
          </div>
          <div className="flex items-center gap-4">
            <span
              className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-[0.65rem] font-semibold ${
                health?.status === "ok"
                  ? "border border-emerald-500/20 bg-emerald-500/8 text-emerald-400"
                  : "border border-slate-700 bg-slate-800/50 text-slate-500"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  health?.status === "ok"
                    ? "bg-emerald-400 pulse-live"
                    : "bg-slate-500"
                }`}
              />
              {health?.status === "ok" ? "Agent Online" : "Agent Offline"}
            </span>
          </div>
        </div>
      </motion.nav>

      {/* ── Top gradient line ─────────────────────────── */}
      <div className="fixed top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-cyan-500/40 to-transparent z-[60]" />

      <div className="relative z-10 mx-auto flex w-full max-w-7xl flex-col gap-10 px-6 pt-20 pb-14 lg:px-10">
        {/* ── Header ──────────────────────────────────── */}
        <motion.header
          variants={stagger}
          initial="hidden"
          animate="visible"
          className="grid gap-8 lg:grid-cols-[1.6fr_1fr]"
        >
          {/* Hero card */}
          <motion.div variants={fadeUp} className="hero-card p-8 lg:p-10">
            <div className="flex items-center gap-3 mb-6">
              <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-500/15 to-violet-500/15 border border-cyan-500/20 shadow-[0_0_20px_rgba(34,211,238,0.1)]">
                <Shield className="w-5 h-5 text-cyan-400" />
              </div>
              <span className="text-xs font-semibold uppercase tracking-[0.3em] text-cyan-400/80">
                SecureLoop
              </span>
            </div>
            <h1 className="max-w-2xl text-4xl font-bold tracking-tight text-white sm:text-5xl leading-[1.1]">
              <span className="text-gradient">Incident Command</span>{" "}
              <br className="hidden sm:block" />
              Center
            </h1>
            <p className="mt-5 max-w-xl text-base leading-7 text-slate-400">
              This dashboard reflects the real companion service contract: raw
              incidents in, human review in the IDE, reviewed history retained
              in the local queue, with Codex analysis and approved fixes
              handled inside the JetBrains plugin.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <motion.button
                onClick={() => {
                  setLoading(true);
                  fetchData();
                }}
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                className="btn-glow flex items-center gap-2 rounded-full bg-gradient-to-r from-cyan-500/20 to-violet-500/20 border border-cyan-400/25 px-6 py-3 text-sm font-semibold text-cyan-100 transition-all hover:border-cyan-300/50 cursor-pointer"
              >
                <RefreshCw
                  className={`w-4 h-4 ${loading ? "animate-spin" : ""}`}
                />
                Refresh Dashboard
              </motion.button>
              <motion.a
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                className="flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-6 py-3 text-sm font-semibold text-slate-300 transition hover:border-white/20 hover:bg-white/[0.06] cursor-pointer"
                href="https://www.jetbrains.com/help/idea/run-debug-configuration-gradle.html"
                target="_blank"
                rel="noreferrer"
              >
                <Zap className="w-4 h-4" />
                Run <code className="font-mono text-xs text-white/70">runIde</code>
              </motion.a>
              <button
                type="button"
                onClick={() => clearIncidents("open")}
                disabled={clearing !== null || displayOpen === 0}
                className="flex items-center gap-2 rounded-full border border-red-400/25 bg-red-500/10 px-6 py-3 text-sm font-semibold text-red-200 transition hover:border-red-300/50 hover:bg-red-500/15 hover:scale-[1.03] active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:scale-100 cursor-pointer"
              >
                <Trash2
                  className={`w-4 h-4 ${clearing === "open" ? "animate-pulse" : ""}`}
                />
                Clear Open
              </button>
              <button
                type="button"
                onClick={() => clearIncidents("reviewed")}
                disabled={clearing !== null || displayReviewed === 0}
                className="flex items-center gap-2 rounded-full border border-emerald-400/25 bg-emerald-500/10 px-6 py-3 text-sm font-semibold text-emerald-200 transition hover:border-emerald-300/50 hover:bg-emerald-500/15 hover:scale-[1.03] active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:scale-100 cursor-pointer"
              >
                <Trash2
                  className={`w-4 h-4 ${clearing === "reviewed" ? "animate-pulse" : ""}`}
                />
                Clear Reviewed
              </button>
            </div>
          </motion.div>

          {/* Status panel */}
          <motion.div variants={fadeUp} className="flex flex-col gap-4">
            {/* Connection status */}
            <div className="glass-card p-6 flex-1">
              <div className="flex items-center justify-between">
                <p className="text-[0.65rem] font-semibold uppercase tracking-[0.28em] text-slate-500">
                  Agent Status
                </p>
                <span
                  className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold ${
                    health?.status === "ok"
                      ? "border border-emerald-500/25 bg-emerald-500/10 text-emerald-400"
                      : "border border-red-500/25 bg-red-500/10 text-red-400"
                  }`}
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      health?.status === "ok"
                        ? "bg-emerald-400 pulse-live"
                        : "bg-red-400"
                    }`}
                  />
                  {health?.status === "ok" ? "Connected" : "Unavailable"}
                </span>
              </div>
              <p className="mt-4 text-sm leading-6 text-slate-400">
                {error ??
                  `Polling ${agentBaseUrl} for health and incident data.`}
              </p>
              <div className="mt-4 flex items-center gap-2">
                <span className="text-[0.6rem] font-semibold uppercase tracking-[0.28em] text-slate-600">
                  Demo mode
                </span>
                <span
                  className={`rounded-full px-2.5 py-0.5 text-[0.65rem] font-semibold ${
                    health?.allowDebugEndpoints
                      ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                      : "bg-slate-800/80 text-slate-500 border border-slate-700/50"
                  }`}
                >
                  {health?.allowDebugEndpoints ? "Enabled" : "Disabled"}
                </span>
              </div>
            </div>

            {/* Stat cards */}
            <div className="grid gap-3 grid-cols-3">
              {stats.map((stat, i) => (
                <motion.div
                  key={stat.label}
                  variants={scaleIn}
                  custom={i}
                  whileHover={{
                    scale: 1.04,
                    transition: { duration: 0.2 },
                  }}
                  className="stat-card p-4 backdrop-blur-xl cursor-default group"
                  style={{
                    boxShadow: `0 16px 48px -8px ${stat.glow}`,
                  }}
                >
                  <div className="flex items-center gap-1.5 mb-3">
                    <stat.icon
                      className={`w-3.5 h-3.5 ${stat.color} transition-transform group-hover:scale-110`}
                      strokeWidth={2.5}
                    />
                    <p className="text-[0.6rem] font-semibold uppercase tracking-[0.24em] text-slate-500">
                      {stat.label}
                    </p>
                  </div>
                  <motion.p
                    key={stat.value}
                    initial={{ scale: 1.2, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    transition={{ type: "spring", stiffness: 300, damping: 20 }}
                    className={`text-3xl font-bold tabular-nums ${stat.color}`}
                  >
                    {stat.value}
                  </motion.p>
                </motion.div>
              ))}
            </div>
          </motion.div>
        </motion.header>

        {/* ── Divider ─────────────────────────────────── */}
        <div className="flex items-center gap-4">
          <div className="flex-1 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent" />
          <span className="text-[0.6rem] font-semibold uppercase tracking-[0.3em] text-slate-600">
            Incident Feed
          </span>
          <div className="flex-1 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent" />
        </div>

        {/* ── Incident stream ─────────────────────────── */}
        <IncidentStream
          initialFeed={feed}
          agentBaseUrl={agentBaseUrl}
          autopilotEnabled={autopilotEnabled}
          onRecordsChange={setLiveRecords}
        />
      </div>

      {/* ── Footer ────────────────────────────────────── */}
      <footer className="relative z-10 border-t border-white/[0.04] py-6">
        <div className="mx-auto max-w-7xl px-6 lg:px-10 flex items-center justify-between">
          <p className="text-[0.65rem] text-slate-600">
            SecureLoop · Built for JBHack
          </p>
          <p className="text-[0.65rem] text-slate-700">
            Auto-Scribe AI SRE Agent
          </p>
        </div>
      </footer>
    </main>
  );
}
