"use client";

import { AnimatePresence, motion, type Variants } from "framer-motion";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Clock,
  Code2,
  Download,
  ExternalLink,
  Eye,
  FileCode2,
  FlaskConical,
  GitPullRequest,
  Loader2,
  MapPin,
  Search,
  ShieldAlert,
  ShieldCheck,
  ShieldOff,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type {
  AutopilotCompletedEvent,
  AutopilotFailedEvent,
  AutopilotStatus,
  AutopilotStepEvent,
  AutopilotStepId,
  IncidentFeedResponse,
  IncidentRecord,
  IncidentsClearedEvent,
  NavigateResponse,
  PipelineStep,
  PipelineStepEvent,
  SentryResolutionStatus,
} from "./types";
import {
  CompactPipelineBar,
  derivePipelineSteps,
} from "./pipeline-progress";

type Props = {
  initialFeed: IncidentFeedResponse | null;
  agentBaseUrl: string;
  autopilotEnabled?: boolean;
  onRecordsChange?: (records: IncidentRecord[]) => void;
};

/* ── Helpers ───────────────────────────────────────────── */
function formatTimestamp(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function relativeTime(value: string): string {
  const diff = Date.now() - new Date(value).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function sentryToneClasses(value: SentryResolutionStatus | null) {
  switch (value) {
    case "resolved":
      return "border-emerald-200 bg-emerald-50 text-emerald-700";
    case "ignored":
      return "border-slate-200 bg-slate-50 text-slate-500";
    default:
      return "border-amber-200 bg-amber-50 text-amber-700";
  }
}

function sentryIcon(value: SentryResolutionStatus | null) {
  switch (value) {
    case "resolved":
      return ShieldCheck;
    case "ignored":
      return ShieldOff;
    default:
      return ShieldAlert;
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

function useMounted(): boolean {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  return mounted;
}

/* ── Animation variants ────────────────────────────────── */
const listStagger: Variants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.05, delayChildren: 0.05 } },
};

const rowVariant: Variants = {
  hidden: { opacity: 0, y: 8 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.35, ease: [0.22, 1, 0.36, 1] as const },
  },
  exit: { opacity: 0, y: -4, transition: { duration: 0.2 } },
};

type ToastKind = "success" | "info" | "error";
type ToastState = { message: string; kind: ToastKind } | null;
type AgentPipelinePayload = {
  incidentId?: string;
  step?: string;
  reason?: string;
  detail?: string;
  error?: string;
  prUrl?: string | null;
};

const PRE_PR_FAILURE_REASONS = new Set([
  "incident_not_found",
  "missing_source_metadata",
  "source_file_not_found",
  "patch_mismatch",
  "sandbox_test_generation_failed",
  "sandbox_did_not_reproduce",
  "sandbox_fix_failed",
  "sandbox_timeout",
  "sandbox_runner_error",
  "internal_error",
]);

function translateAgentEvent(
  eventName: "pipeline.step" | "pipeline.completed" | "pipeline.failed",
  payload: AgentPipelinePayload,
): PipelineStepEvent[] {
  const incidentId = payload.incidentId;
  if (!incidentId) return [];

  if (eventName === "pipeline.step") {
    switch (payload.step) {
      case "fetch_source":
      case "analyze":
        return [{ incidentId, step: "analyzing", status: "running" }];
      case "sandbox":
        return [
          { incidentId, step: "analyzing", status: "completed" },
          { incidentId, step: "sandbox", status: "running" },
        ];
      case "open_pr":
        return [
          { incidentId, step: "analyzing", status: "completed" },
          { incidentId, step: "sandbox", status: "completed" },
          { incidentId, step: "pr_opening", status: "running" },
        ];
      default:
        return [];
    }
  }

  if (eventName === "pipeline.completed") {
    return [
      {
        incidentId,
        step: "pr_opening",
        status: "completed",
        prUrl: payload.prUrl ?? null,
      },
    ];
  }

  const reason = payload.reason ?? payload.error ?? "unknown";
  const failedStep = reason.startsWith("sandbox_")
    ? "sandbox"
    : PRE_PR_FAILURE_REASONS.has(reason)
      ? "analyzing"
      : "pr_opening";
  return [
    {
      incidentId,
      step: failedStep,
      status: "failed",
      error: payload.detail ?? payload.error ?? reason,
    },
  ];
}

/* ── Main stream ───────────────────────────────────────── */
export function IncidentStream({
  initialFeed,
  agentBaseUrl,
  autopilotEnabled = false,
  onRecordsChange,
}: Props) {
  const [records, setRecords] = useState<IncidentRecord[]>(
    initialFeed?.incidents ?? [],
  );
  const [connected, setConnected] = useState(false);
  const [toast, setToast] = useState<ToastState>(null);
  const [pipelines, setPipelines] = useState<Record<string, AutopilotStatus>>(
    {},
  );
  const [pipelineEvents, setPipelineEvents] = useState<
    Record<string, PipelineStepEvent[]>
  >({});
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    onRecordsChange?.(records);
  }, [records, onRecordsChange]);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(timer);
  }, [toast]);

  const toggleExpanded = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

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
      if (body.delivered) {
        setToast({ message: "Sent to IDE", kind: "success" });
      } else if (body.launched) {
        setToast({
          message: "Launching sandbox IDE… the file will open in ~20s",
          kind: "info",
        });
      } else {
        switch (body.launchReason) {
          case "already-running":
            setToast({ message: "Launching sandbox IDE…", kind: "info" });
            break;
          case "debounced":
            setToast({
              message: "Sandbox IDE starting — please wait",
              kind: "info",
            });
            break;
          case "gradlew-not-found":
            setToast({
              message:
                "Could not find gradlew in apps/jetbrains-plugin — start the IDE manually",
              kind: "error",
            });
            break;
          case "spawn-error":
            setToast({
              message: "Failed to launch sandbox IDE",
              kind: "error",
            });
            break;
          case "disabled":
          default:
            setToast({ message: "IDE plugin not connected", kind: "info" });
        }
      }
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
        // ignore
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
        setPipelines((prev) => {
          const next = { ...prev };
          for (const id of removed) delete next[id];
          return next;
        });
      } catch {
        // ignore
      }
    };
    source.addEventListener("incidents.cleared", handleCleared);

    const handlePipelineStep = (evt: MessageEvent) => {
      try {
        const data = JSON.parse(evt.data) as AutopilotStepEvent &
          AgentPipelinePayload;
        if (!isAutopilotStepId(data.step)) return;
        setPipelines((prev) => ({
          ...prev,
          [data.incidentId]: { phase: "running", step: data.step },
        }));
        const translated = translateAgentEvent("pipeline.step", data);
        if (translated.length > 0) {
          setPipelineEvents((prev) => ({
            ...prev,
            [data.incidentId]: [...(prev[data.incidentId] ?? []), ...translated],
          }));
        }
      } catch {
        // ignore
      }
    };
    const handlePipelineCompleted = (evt: MessageEvent) => {
      try {
        const data = JSON.parse(evt.data) as AutopilotCompletedEvent &
          AgentPipelinePayload;
        setPipelines((prev) => ({
          ...prev,
          [data.incidentId]: {
            phase: "completed",
            prUrl: data.prUrl,
            prNumber: data.prNumber,
            branch: data.branch,
          },
        }));
        const translated = translateAgentEvent("pipeline.completed", data);
        if (translated.length > 0) {
          setPipelineEvents((prev) => ({
            ...prev,
            [data.incidentId]: [...(prev[data.incidentId] ?? []), ...translated],
          }));
        }
      } catch {
        // ignore
      }
    };
    const handlePipelineFailed = (evt: MessageEvent) => {
      try {
        const data = JSON.parse(evt.data) as AutopilotFailedEvent &
          AgentPipelinePayload;
        setPipelines((prev) => ({
          ...prev,
          [data.incidentId]: {
            phase: "failed",
            reason: data.reason,
            path: data.path,
          },
        }));
        const translated = translateAgentEvent("pipeline.failed", data);
        if (translated.length > 0) {
          setPipelineEvents((prev) => ({
            ...prev,
            [data.incidentId]: [...(prev[data.incidentId] ?? []), ...translated],
          }));
        }
      } catch {
        // ignore
      }
    };
    source.addEventListener("pipeline.step", handlePipelineStep);
    source.addEventListener("pipeline.completed", handlePipelineCompleted);
    source.addEventListener("pipeline.failed", handlePipelineFailed);

    const handlePipelineProgress = (evt: MessageEvent) => {
      try {
        const ev = JSON.parse(evt.data) as PipelineStepEvent;
        if (!ev || typeof ev.step !== "string" || typeof ev.status !== "string") {
          return;
        }
        setPipelineEvents((prev) => ({
          ...prev,
          [ev.incidentId]: [...(prev[ev.incidentId] ?? []), ev],
        }));
      } catch {
        // ignore
      }
    };
    source.addEventListener("pipeline.step", handlePipelineProgress);
    source.addEventListener("pipeline.completed", handlePipelineProgress);
    source.addEventListener("pipeline.failed", handlePipelineProgress);

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
        className="grid gap-6 xl:grid-cols-[1.12fr_0.88fr]"
      >
        {/* ── Open incidents panel ─────────────────────── */}
        <LogPanel
          title="Open Incidents"
          count={openIncidents.length}
          countLabel="active"
          tone="danger"
          Icon={AlertTriangle}
          live
          connected={connected}
          emptyMessage={
            <>
              No active incidents. Trigger a Sentry alert and SecureLoop will
              start the autopilot remediation loop.
            </>
          }
        >
          <AnimatePresence initial={false}>
            {openIncidents.map((record) => (
              <LogRow
                key={record.incident.incidentId}
                record={record}
                expanded={expanded.has(record.incident.incidentId)}
                onToggle={() => toggleExpanded(record.incident.incidentId)}
                pipeline={pipelines[record.incident.incidentId]}
                steps={derivePipelineSteps(
                  record,
                  pipelineEvents[record.incident.incidentId] ?? [],
                )}
                autopilotEnabled={autopilotEnabled}
                onOpenInIde={openInIde}
              />
            ))}
          </AnimatePresence>
        </LogPanel>

        {/* ── Reviewed history panel ───────────────────── */}
        <LogPanel
          title="Reviewed History"
          count={reviewedIncidents.length}
          countLabel="reviewed"
          tone="success"
          Icon={Eye}
          emptyMessage={
            <>
              Reviewed incidents appear here after the developer approves or
              rejects the generated fix in JetBrains.
            </>
          }
        >
          <AnimatePresence initial={false}>
            {reviewedIncidents.map((record) => (
              <LogRow
                key={record.incident.incidentId}
                record={record}
                expanded={expanded.has(record.incident.incidentId)}
                onToggle={() => toggleExpanded(record.incident.incidentId)}
                pipeline={pipelines[record.incident.incidentId]}
                steps={derivePipelineSteps(
                  record,
                  pipelineEvents[record.incident.incidentId] ?? [],
                )}
                autopilotEnabled={autopilotEnabled}
                onOpenInIde={openInIde}
              />
            ))}
          </AnimatePresence>
        </LogPanel>
      </motion.section>
      <Toast state={toast} />
    </>
  );
}

/* ── Log panel wrapper ─────────────────────────────────── */
function LogPanel({
  title,
  count,
  countLabel,
  tone,
  Icon,
  live,
  connected,
  emptyMessage,
  children,
}: {
  title: string;
  count: number;
  countLabel: string;
  tone: "danger" | "success";
  Icon: typeof AlertTriangle;
  live?: boolean;
  connected?: boolean;
  emptyMessage: React.ReactNode;
  children: React.ReactNode;
}) {
  const iconClass =
    tone === "danger" ? "text-red-600 bg-red-50" : "text-emerald-600 bg-emerald-50";
  const countClass =
    tone === "danger"
      ? "text-red-600 border-red-200 bg-red-50"
      : "text-emerald-600 border-emerald-200 bg-emerald-50";

  return (
    <div className="log-panel">
      <div className="log-panel-header">
        <div className="flex items-center gap-3">
          <span
            className={`flex h-10 w-10 items-center justify-center rounded-lg ${iconClass}`}
          >
            <Icon className="h-5 w-5" strokeWidth={2.25} />
          </span>
          <div>
            <h2 className="text-[19px] font-black text-slate-950">
              {title}
            </h2>
            <p className="mt-0.5 text-[12px] font-medium text-slate-500">
              {count} {countLabel} · log-style feed
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {live ? (
            <span className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-bold uppercase text-slate-500">
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  connected ? "bg-emerald-500 pulse-live" : "bg-amber-400"
                }`}
              />
              {connected ? "Live" : "Reconnecting"}
            </span>
          ) : null}
          <span
            className={`inline-flex items-center rounded-lg border px-3 py-1 text-[12px] font-black tabular-nums ${countClass}`}
          >
            {count}
          </span>
        </div>
      </div>

      {count === 0 ? (
        <div className="flex min-h-[190px] items-center justify-center px-8 py-14">
          <p className="max-w-md text-center text-[15px] font-medium leading-7 text-slate-500">
            {emptyMessage}
          </p>
        </div>
      ) : (
        <div>{children}</div>
      )}
    </div>
  );
}

/* ── Log row ───────────────────────────────────────────── */
function LogRow({
  record,
  expanded,
  onToggle,
  pipeline,
  steps,
  autopilotEnabled = false,
  onOpenInIde,
}: {
  record: IncidentRecord;
  expanded: boolean;
  onToggle: () => void;
  pipeline?: AutopilotStatus;
  steps: PipelineStep[];
  autopilotEnabled?: boolean;
  onOpenInIde?: (incidentId: string) => void;
}) {
  const location = [
    record.incident.repoRelativePath,
    record.incident.lineNumber,
  ]
    .filter(Boolean)
    .join(":");
  const mounted = useMounted();
  const receivedLabel = mounted ? relativeTime(record.createdAt) : "";
  const receivedFull = mounted ? formatTimestamp(record.createdAt) : "";

  const isOpen = record.status === "open";
  const accentColor = isOpen ? "#dc2626" : "#059669";
  const canOpenInIde = Boolean(record.incident.repoRelativePath);
  const SentryIcon = sentryIcon(record.incident.sentryStatus);
  const sentryTone = sentryToneClasses(record.incident.sentryStatus);
  const sentryStatus = record.incident.sentryStatus ?? "unresolved";

  return (
    <motion.article
      layout
      variants={rowVariant}
      initial="hidden"
      animate="visible"
      exit="exit"
      className="log-row group"
    >
      <div
        className="log-row-accent"
        style={{ background: accentColor }}
      />

      {/* Row header (clickable) */}
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-start gap-3 text-left"
      >
        {/* Status dot */}
        <span
          className="mt-1.5 flex h-2 w-2 shrink-0 rounded-full"
          style={{
            background: accentColor,
            boxShadow: isOpen ? "0 0 0 3px rgba(220,38,38,0.12)" : undefined,
          }}
        />

        <div className="min-w-0 flex-1">
          {/* Line 1 — chips + type + title */}
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span
              className={`chip chip-mono ${sentryTone}`}
              style={{ borderWidth: 1 }}
            >
              <SentryIcon className="h-3 w-3" />
              {sentryStatus}
            </span>
            {record.incident.environment ? (
              <span className="chip chip-mono">
                {record.incident.environment}
              </span>
            ) : null}
            <span className="font-mono text-[13px] font-black text-slate-950">
              {record.incident.exceptionType}
            </span>
            <span className="text-slate-300">·</span>
            <span className="truncate text-[15px] font-bold text-slate-800">
              {record.incident.title}
            </span>
          </div>

          {/* Line 2 — location + function + time */}
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-slate-500">
            <span className="inline-flex items-center gap-1.5 font-mono">
              <MapPin className="h-3 w-3 text-slate-400" />
              {location || "location unavailable"}
            </span>
            {record.incident.functionName ? (
              <span className="inline-flex items-center gap-1.5 font-mono">
                <Code2 className="h-3 w-3 text-slate-400" />
                {record.incident.functionName}
              </span>
            ) : null}
            <span
              className="inline-flex items-center gap-1.5"
              title={receivedFull}
            >
              <Clock className="h-3 w-3 text-slate-400" />
              {receivedLabel}
            </span>
            <span className="inline-flex items-center gap-1.5 text-slate-400">
              <span className="font-mono text-[10px] uppercase tracking-[0.18em]">
                pipeline
              </span>
              <CompactPipelineBar steps={steps} />
            </span>
          </div>
        </div>

        {/* Expand chevron */}
        <ChevronRight
          className={`h-4 w-4 shrink-0 text-slate-400 transition-transform ${expanded ? "rotate-90" : ""}`}
        />
      </button>

      {/* Right-rail quick actions (always visible) */}
      <div className="mt-3 flex flex-wrap items-center gap-2 pl-5">
        <button
          type="button"
          disabled={!canOpenInIde || !onOpenInIde}
          onClick={(e) => {
            e.stopPropagation();
            if (canOpenInIde) onOpenInIde?.(record.incident.incidentId);
          }}
          className="btn"
          title={
            canOpenInIde
              ? "Open this file in your running JetBrains IDE"
              : "No repo-relative path available"
          }
        >
          <FileCode2 className="h-3.5 w-3.5" />
          Open in IDE
        </button>
        <a
          className="btn"
          href={record.incident.eventWebUrl}
          target="_blank"
          rel="noreferrer"
          onClick={(e) => e.stopPropagation()}
        >
          <ExternalLink className="h-3.5 w-3.5" />
          Sentry
        </a>
        <Link
          href={`/session/${record.incident.incidentId}`}
          className="btn btn-primary"
          onClick={(e) => e.stopPropagation()}
        >
          View session
        </Link>
      </div>

      {/* Expanded body */}
      <AnimatePresence initial={false}>
        {expanded ? (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="mt-4 grid gap-3 rounded-lg border border-slate-200 bg-slate-50/60 p-4 text-[12px] sm:grid-cols-2">
              <ExpandedField
                label="Exception message"
                value={record.incident.exceptionMessage}
              />
              <ExpandedField
                label="Received"
                value={receivedFull}
                secondary={receivedLabel}
              />
              <ExpandedField
                label="Review state"
                value={
                  record.status === "reviewed"
                    ? `Reviewed ${formatTimestamp(record.reviewedAt)}`
                    : "Waiting for human review in IDE"
                }
              />
              <ExpandedField
                label="Incident ID"
                value={record.incident.incidentId}
                mono
              />
            </div>

            {autopilotEnabled && pipeline ? (
              <PipelineStrip pipeline={pipeline} />
            ) : null}

            {record.incident.codeContext ? (
              <div className="mt-4 code-block overflow-hidden">
                <div className="flex items-center gap-2 border-b border-white/10 px-4 py-2">
                  <Code2 className="h-3 w-3 text-slate-400" />
                  <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-400">
                    Code Context
                  </span>
                </div>
                <pre className="overflow-x-auto p-4 font-mono text-[12px] leading-6 text-slate-100">
                  <code>{record.incident.codeContext}</code>
                </pre>
              </div>
            ) : null}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </motion.article>
  );
}

/* ── Expanded detail field ─────────────────────────────── */
function ExpandedField({
  label,
  value,
  secondary,
  mono,
}: {
  label: string;
  value: string;
  secondary?: string;
  mono?: boolean;
}) {
  return (
    <div>
      <p className="text-[9px] font-semibold uppercase tracking-[0.22em] text-slate-400">
        {label}
      </p>
      <p
        className={`mt-1 text-slate-900 ${mono ? "font-mono text-[11.5px]" : "text-[13px] leading-5"}`}
      >
        {value}
      </p>
      {secondary ? (
        <p className="mt-0.5 text-[11px] text-slate-500">{secondary}</p>
      ) : null}
    </div>
  );
}

/* ── Toast ─────────────────────────────────────────────── */
function Toast({ state }: { state: ToastState }) {
  if (!state) return null;
  const tone =
    state.kind === "success"
      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
      : state.kind === "error"
        ? "border-red-200 bg-red-50 text-red-800"
        : "border-slate-200 bg-white text-slate-800";
  return (
    <div
      role="status"
      aria-live="polite"
      className={`pointer-events-none fixed bottom-6 right-6 z-50 rounded-xl border px-4 py-3 text-sm font-medium shadow-lg ${tone}`}
    >
      {state.message}
    </div>
  );
}

/* ── Autopilot pipeline strip (expanded row) ───────────── */
const PIPELINE_STEPS: {
  id: AutopilotStepId;
  label: string;
  icon: typeof Search;
}[] = [
  { id: "fetch_source", label: "Fetch", icon: Download },
  { id: "analyze", label: "Analyze", icon: Search },
  { id: "sandbox", label: "Sandbox", icon: FlaskConical },
  { id: "open_pr", label: "Open PR", icon: GitPullRequest },
];

const FAILURE_REASON_LABELS: Record<string, string> = {
  incident_not_found: "Incident not found",
  missing_source_metadata: "Missing source metadata",
  source_file_not_found: "Source file not found",
  patch_mismatch: "Patch did not apply",
  sandbox_test_generation_failed: "Test generation failed",
  sandbox_did_not_reproduce: "Did not reproduce bug",
  sandbox_fix_failed: "Fix did not pass sandbox",
  sandbox_timeout: "Sandbox timed out",
  sandbox_runner_error: "Sandbox runner error",
  internal_error: "Internal error",
};

function failureReasonLabel(reason: string): string {
  return FAILURE_REASON_LABELS[reason] ?? reason;
}

function isAutopilotStepId(value: unknown): value is AutopilotStepId {
  return (
    value === "fetch_source" ||
    value === "analyze" ||
    value === "sandbox" ||
    value === "open_pr"
  );
}

function stepIndex(step: AutopilotStepId): number {
  return PIPELINE_STEPS.findIndex((s) => s.id === step);
}

function PipelineStrip({ pipeline }: { pipeline: AutopilotStatus }) {
  const failed = pipeline.phase === "failed";
  const completed = pipeline.phase === "completed";
  const currentIdx =
    pipeline.phase === "running"
      ? stepIndex(pipeline.step)
      : completed
        ? PIPELINE_STEPS.length
        : -1;

  return (
    <div className="mt-4 rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
          Autopilot Pipeline
        </span>
        {completed && "prUrl" in pipeline ? (
          <a
            href={pipeline.prUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[11px] font-semibold text-emerald-700 hover:bg-emerald-100"
          >
            <GitPullRequest className="h-3 w-3" />
            PR #{pipeline.prNumber}
          </a>
        ) : null}
        {failed && "reason" in pipeline ? (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-red-200 bg-red-50 px-3 py-1 text-[11px] font-semibold text-red-700">
            <XCircle className="h-3 w-3" />
            {failureReasonLabel(pipeline.reason)}
          </span>
        ) : null}
      </div>
      <div className="flex items-center gap-2">
        {PIPELINE_STEPS.map((step, idx) => {
          const done = idx < currentIdx;
          const active = idx === currentIdx && pipeline.phase === "running";
          const isFailedHere = failed && idx === Math.max(currentIdx, 0);
          const StepIcon = step.icon;
          const dotTone = isFailedHere
            ? "border-red-200 bg-red-50 text-red-700"
            : done
              ? "border-emerald-200 bg-emerald-50 text-emerald-700"
              : active
                ? "border-slate-300 bg-slate-100 text-slate-900"
                : "border-slate-200 bg-white text-slate-400";
          const barTone = done
            ? "bg-emerald-300"
            : active
              ? "bg-slate-400"
              : "bg-slate-200";
          return (
            <div key={step.id} className="flex flex-1 items-center gap-2">
              <div
                className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold ${dotTone}`}
              >
                {active ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : isFailedHere ? (
                  <XCircle className="h-3 w-3" />
                ) : done ? (
                  <CheckCircle2 className="h-3 w-3" />
                ) : (
                  <StepIcon className="h-3 w-3" />
                )}
                {step.label}
              </div>
              {idx < PIPELINE_STEPS.length - 1 ? (
                <div className={`h-px flex-1 ${barTone}`} />
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
