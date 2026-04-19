"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Code2,
  ExternalLink,
  Eye,
  FileCode2,
  FunctionSquare,
  MapPin,
  Radio,
  ShieldAlert,
  ShieldCheck,
  ShieldOff,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type {
  IncidentFeedResponse,
  IncidentRecord,
  IncidentsClearedEvent,
  NavigateResponse,
  SentryResolutionStatus,
} from "./types";

/* ── Props ─────────────────────────────────────────────── */
type Props = {
  initialFeed: IncidentFeedResponse | null;
  agentBaseUrl: string;
  onRecordsChange?: (records: IncidentRecord[]) => void;
};

/* ── Helpers ───────────────────────────────────────────── */
function formatTimestamp(value: string | null): string {
  if (!value) return "Not yet reviewed";
  const date = new Date(value);
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function relativeTime(value: string): string {
  const diff = Date.now() - new Date(value).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

type StatusStyle = {
  bg: string;
  border: string;
  text: string;
  icon: typeof AlertTriangle;
};

function getStatusStyle(status: IncidentRecord["status"]): StatusStyle {
  return status === "open"
    ? {
        bg: "bg-red-500/8",
        border: "border-red-500/25",
        text: "text-red-400",
        icon: AlertTriangle,
      }
    : {
        bg: "bg-emerald-500/8",
        border: "border-emerald-500/25",
        text: "text-emerald-400",
        icon: CheckCircle2,
      };
}

function getSentryStyle(
  value: SentryResolutionStatus | null,
): StatusStyle {
  switch (value) {
    case "resolved":
      return {
        bg: "bg-emerald-500/8",
        border: "border-emerald-500/25",
        text: "text-emerald-400",
        icon: ShieldCheck,
      };
    case "ignored":
      return {
        bg: "bg-slate-500/8",
        border: "border-slate-500/25",
        text: "text-slate-400",
        icon: ShieldOff,
      };
    default:
      return {
        bg: "bg-amber-500/8",
        border: "border-amber-500/25",
        text: "text-amber-400",
        icon: ShieldAlert,
      };
  }
}

function upsertById(
  prev: IncidentRecord[],
  incoming: IncidentRecord,
): IncidentRecord[] {
  const id = incoming.incident.incidentId;
  const next = prev.filter((r) => r.incident.incidentId !== id);
  next.unshift(incoming);
  next.sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));
  return next;
}

/* ── Animation variants ────────────────────────────────── */
const listStagger = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.08, delayChildren: 0.2 },
  },
};

const cardVariant = {
  hidden: { opacity: 0, y: 20, scale: 0.97, filter: "blur(4px)" },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    filter: "blur(0px)",
    transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] },
  },
  exit: {
    opacity: 0,
    scale: 0.95,
    y: -10,
    transition: { duration: 0.3 },
  },
};

const fadeIn = {
  hidden: { opacity: 0, y: 12 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] },
  },
};

/* ── Main component ────────────────────────────────────── */
type ToastKind = "success" | "info" | "error";
type ToastState = { message: string; kind: ToastKind } | null;

export function IncidentStream({ initialFeed, agentBaseUrl, onRecordsChange }: Props) {
  const [records, setRecords] = useState<IncidentRecord[]>(
    initialFeed?.incidents ?? [],
  );
  const [connected, setConnected] = useState(false);
  const [toast, setToast] = useState<ToastState>(null);

  // Notify parent of record changes for live stat updates
  useEffect(() => {
    onRecordsChange?.(records);
  }, [records, onRecordsChange]);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(timer);
  }, [toast]);

  const openInIde = async (incidentId: string) => {
    try {
      const res = await fetch(`${agentBaseUrl}/ide/navigate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ incidentId }),
      });
      if (!res.ok) {
        setToast({ message: "Failed to reach agent", kind: "error" });
        return;
      }
      const body = (await res.json()) as NavigateResponse;
      setToast(
        body.delivered
          ? { message: "Sent to IDE", kind: "success" }
          : { message: "IDE plugin not connected", kind: "info" },
      );
    } catch {
      setToast({ message: "Failed to reach agent", kind: "error" });
    }
  };

  useEffect(() => {
    const url = `${agentBaseUrl}/dashboard/events/stream`;
    const source = new EventSource(url);
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    const handleEvent = (evt: MessageEvent) => {
      try {
        const incoming = JSON.parse(evt.data) as IncidentRecord;
        setRecords((prev) => upsertById(prev, incoming));
      } catch {
        // Ignore malformed frames; the next snapshot on reconnect will resync.
      }
    };
    source.addEventListener("incident.created", handleEvent);
    source.addEventListener("incident.updated", handleEvent);
    const handleCleared = (evt: MessageEvent) => {
      try {
        const cleared = JSON.parse(evt.data) as IncidentsClearedEvent;
        const removed = new Set(cleared.incidentIds);
        setRecords((prev) =>
          prev.filter((r) => !removed.has(r.incident.incidentId)),
        );
      } catch {
        // Ignore malformed frames; a refresh will resync.
      }
    };
    source.addEventListener("incidents.cleared", handleCleared);
    return () => source.close();
  }, [agentBaseUrl]);

  const openIncidents = useMemo(
    () => records.filter((r) => r.status === "open"),
    [records],
  );
  const reviewedIncidents = useMemo(
    () => records.filter((r) => r.status === "reviewed"),
    [records],
  );

  return (
    <>
    <motion.section
      variants={listStagger}
      initial="hidden"
      animate="visible"
      className="grid gap-8 xl:grid-cols-2"
    >
      {/* ── Open incidents column ─────────────────────── */}
      <div className="space-y-5">
        <motion.div
          variants={fadeIn}
          className="flex items-center justify-between"
        >
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-red-500/10 border border-red-500/15">
              <AlertTriangle className="w-4 h-4 text-red-400" />
            </div>
            <h2 className="text-xl font-bold text-white tracking-tight">
              Open Incidents
            </h2>
          </div>
          <div className="flex items-center gap-3">
            <LiveIndicator connected={connected} />
            <span className="rounded-full border border-red-500/20 bg-red-500/8 px-3 py-1 text-[0.65rem] font-bold uppercase tracking-[0.22em] text-red-400 tabular-nums">
              {openIncidents.length} active
            </span>
          </div>
        </motion.div>

        <AnimatePresence mode="popLayout">
          {openIncidents.length > 0 ? (
            openIncidents.map((record) => (
              <IncidentCard
                key={record.incident.incidentId}
                record={record}
                onOpenInIde={openInIde}
              />
            ))
          ) : (
            <motion.div
              variants={cardVariant}
              initial="hidden"
              animate="visible"
              className="glass-card border-dashed p-8 text-center"
            >
              <div className="flex flex-col items-center gap-3">
                <div className="flex items-center justify-center w-12 h-12 rounded-2xl bg-white/5 border border-white/10">
                  <ShieldCheck className="w-5 h-5 text-slate-500" />
                </div>
                <p className="text-sm leading-7 text-slate-500 max-w-xs">
                  No open incidents in the queue. Trigger{" "}
                  <code className="font-mono text-xs text-cyan-400/60 bg-cyan-500/5 px-1.5 py-0.5 rounded">
                    Run Demo
                  </code>{" "}
                  in the plugin to generate one.
                </p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ── Reviewed column ────────────────────────────── */}
      <div className="space-y-5">
        <motion.div
          variants={fadeIn}
          className="flex items-center justify-between"
        >
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/15">
              <Eye className="w-4 h-4 text-emerald-400" />
            </div>
            <h2 className="text-xl font-bold text-white tracking-tight">
              Reviewed History
            </h2>
          </div>
          <span className="rounded-full border border-emerald-500/20 bg-emerald-500/8 px-3 py-1 text-[0.65rem] font-bold uppercase tracking-[0.22em] text-emerald-400 tabular-nums">
            {reviewedIncidents.length} reviewed
          </span>
        </motion.div>

        <AnimatePresence mode="popLayout">
          {reviewedIncidents.length > 0 ? (
            reviewedIncidents.map((record) => (
              <IncidentCard
                key={record.incident.incidentId}
                record={record}
                onOpenInIde={openInIde}
              />
            ))
          ) : (
            <motion.div
              variants={cardVariant}
              initial="hidden"
              animate="visible"
              className="glass-card border-dashed p-8 text-center"
            >
              <div className="flex flex-col items-center gap-3">
                <div className="flex items-center justify-center w-12 h-12 rounded-2xl bg-white/5 border border-white/10">
                  <Clock className="w-5 h-5 text-slate-500" />
                </div>
                <p className="text-sm leading-7 text-slate-500 max-w-xs">
                  Reviewed incidents appear here after a developer clicks{" "}
                  <code className="font-mono text-xs text-cyan-400/60 bg-cyan-500/5 px-1.5 py-0.5 rounded">
                    Mark Reviewed
                  </code>{" "}
                  in the IDE.
                </p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.section>
    <Toast state={toast} />
    </>
  );
}

/* ── Toast ─────────────────────────────────────────────── */
function Toast({ state }: { state: ToastState }) {
  if (!state) return null;
  const tone =
    state.kind === "success"
      ? "border-emerald-400/40 bg-emerald-500/20 text-emerald-50"
      : state.kind === "error"
        ? "border-red-400/40 bg-red-500/20 text-red-50"
        : "border-slate-400/40 bg-slate-500/20 text-slate-50";
  return (
    <div
      role="status"
      aria-live="polite"
      className={`pointer-events-none fixed bottom-6 right-6 z-50 rounded-2xl border px-4 py-3 text-sm font-medium shadow-[0_12px_40px_rgba(15,23,42,0.5)] backdrop-blur ${tone}`}
    >
      {state.message}
    </div>
  );
}

/* ── Live indicator ────────────────────────────────────── */
function LiveIndicator({ connected }: { connected: boolean }) {
  return (
    <span className="flex items-center gap-2 rounded-full border border-white/8 bg-white/[0.03] px-3 py-1 text-[0.65rem] font-semibold uppercase tracking-[0.22em] text-slate-400">
      <span
        className={`h-1.5 w-1.5 rounded-full transition-colors ${
          connected
            ? "bg-emerald-400 pulse-live"
            : "bg-amber-400"
        }`}
      />
      {connected ? "Live" : "Reconnecting"}
    </span>
  );
}

/* ── Incident card ─────────────────────────────────────── */
function IncidentCard({
  record,
  onOpenInIde,
}: {
  record: IncidentRecord;
  onOpenInIde?: (incidentId: string) => void;
}) {
  const location = [
    record.incident.repoRelativePath,
    record.incident.lineNumber,
  ]
    .filter(Boolean)
    .join(":");
  const sentryStatus = record.incident.sentryStatus ?? "unresolved";
  const statusStyle = getStatusStyle(record.status);
  const sentryStyle = getSentryStyle(record.incident.sentryStatus);
  const StatusIcon = statusStyle.icon;
  const SentryIcon = sentryStyle.icon;
  const canOpenInIde = Boolean(record.incident.repoRelativePath);

  return (
    <motion.article
      layout
      variants={cardVariant}
      initial="hidden"
      animate="visible"
      exit="exit"
      className="glass-card group p-5 lg:p-6 transition-all duration-300"
    >
      {/* ── Top row: badges + Sentry link ──────────────  */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-3 flex-1 min-w-0">
          {/* Badges */}
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[0.65rem] font-bold uppercase tracking-[0.24em] ${statusStyle.bg} ${statusStyle.border} ${statusStyle.text}`}
            >
              <StatusIcon className="w-3 h-3" />
              {record.status}
            </span>
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[0.65rem] font-bold uppercase tracking-[0.24em] ${sentryStyle.bg} ${sentryStyle.border} ${sentryStyle.text}`}
            >
              <SentryIcon className="w-3 h-3" />
              {sentryStatus}
            </span>
            <span className="rounded-full border border-white/8 bg-white/[0.03] px-3 py-1 text-[0.6rem] font-semibold uppercase tracking-[0.22em] text-slate-500">
              {record.incident.environment ?? "unknown env"}
            </span>
          </div>

          {/* Title */}
          <h3 className="text-lg font-bold text-white leading-snug tracking-tight">
            <span className="text-slate-400 font-semibold">
              {record.incident.exceptionType}
            </span>
            <span className="text-white/20 mx-2">·</span>
            {record.incident.title}
          </h3>

          {/* Exception message */}
          <p className="max-w-2xl text-sm leading-relaxed text-slate-400">
            {record.incident.exceptionMessage}
          </p>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2 shrink-0">
          <motion.button
            type="button"
            whileHover={canOpenInIde ? { scale: 1.04 } : undefined}
            whileTap={canOpenInIde ? { scale: 0.97 } : undefined}
            disabled={!canOpenInIde || !onOpenInIde}
            onClick={() =>
              canOpenInIde && onOpenInIde?.(record.incident.incidentId)
            }
            title={
              canOpenInIde
                ? "Open this file in your running JetBrains IDE"
                : "No repo-relative path available for this incident"
            }
            className="flex items-center gap-2 rounded-full border border-amber-400/20 bg-amber-400/8 px-4 py-2 text-xs font-semibold text-amber-300 transition-all hover:border-amber-300/40 hover:bg-amber-400/15 hover:shadow-[0_4px_20px_rgba(251,191,36,0.12)] cursor-pointer disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-amber-400/20 disabled:hover:bg-amber-400/8 disabled:hover:shadow-none"
          >
            <FileCode2 className="w-3.5 h-3.5" />
            Open in IDE
          </motion.button>
          <motion.a
            whileHover={{ scale: 1.04 }}
            whileTap={{ scale: 0.97 }}
            className="flex items-center gap-2 rounded-full border border-cyan-400/20 bg-cyan-400/8 px-4 py-2 text-xs font-semibold text-cyan-300 transition-all hover:border-cyan-300/40 hover:bg-cyan-400/15 hover:shadow-[0_4px_20px_rgba(34,211,238,0.12)] cursor-pointer"
            href={record.incident.eventWebUrl}
            target="_blank"
            rel="noreferrer"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            Open Sentry
          </motion.a>
        </div>
      </div>

      {/* ── Detail grid ────────────────────────────────── */}
      <dl className="mt-5 grid gap-3 text-sm text-slate-400 md:grid-cols-2">
        <DetailCell
          icon={MapPin}
          label="Location"
          value={location || "Location unavailable"}
          mono
        />
        <DetailCell
          icon={FunctionSquare}
          label="Function"
          value={record.incident.functionName ?? "Unknown function"}
          mono
        />
        <DetailCell
          icon={Clock}
          label="Received"
          value={formatTimestamp(record.createdAt)}
          secondary={relativeTime(record.createdAt)}
        />
        <DetailCell
          icon={Eye}
          label="Review State"
          value={
            record.status === "reviewed"
              ? `Reviewed ${formatTimestamp(record.reviewedAt)}`
              : "Waiting for human review in the IDE"
          }
        />
      </dl>

      {/* ── Code context ───────────────────────────────── */}
      {record.incident.codeContext ? (
        <div className="mt-5 code-block overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-amber-300/8">
            <Code2 className="w-3.5 h-3.5 text-amber-400/60" />
            <span className="text-[0.65rem] font-semibold uppercase tracking-[0.2em] text-amber-400/50">
              Code Context
            </span>
          </div>
          <pre className="overflow-x-auto p-4 text-sm leading-6 text-amber-100/80 font-mono">
            <code>{record.incident.codeContext}</code>
          </pre>
        </div>
      ) : null}
    </motion.article>
  );
}

/* ── Detail cell sub-component ─────────────────────────── */
function DetailCell({
  icon: Icon,
  label,
  value,
  mono,
  secondary,
}: {
  icon: typeof MapPin;
  label: string;
  value: string;
  mono?: boolean;
  secondary?: string;
}) {
  return (
    <div className="stat-card p-4 backdrop-blur-sm">
      <dt className="flex items-center gap-1.5 text-[0.6rem] font-semibold uppercase tracking-[0.22em] text-slate-600">
        <Icon className="w-3 h-3" />
        {label}
      </dt>
      <dd
        className={`mt-2 text-slate-200 ${
          mono ? "font-mono text-xs" : "text-sm"
        }`}
      >
        {value}
      </dd>
      {secondary && (
        <dd className="mt-0.5 text-[0.65rem] text-slate-500">{secondary}</dd>
      )}
    </div>
  );
}
