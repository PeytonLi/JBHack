"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  CheckCircle2,
  ExternalLink,
  Loader2,
  Zap,
} from "lucide-react";
import type {
  IncidentRecord,
  PipelineStep,
  PipelineStepEvent,
  PipelineStepId,
  PipelineStepStatus,
} from "./types";

const STEP_LABELS: Record<PipelineStepId, string> = {
  ingested: "Ingested",
  analyzing: "Analyzing",
  analyzed: "Analyzed",
  pr_opening: "Opening PR",
  pr_ready: "PR Ready",
};

const STEP_ORDER: PipelineStepId[] = [
  "ingested",
  "analyzing",
  "analyzed",
  "pr_opening",
  "pr_ready",
];

function relativeTime(value: string | null): string {
  if (!value) return "";
  const diff = Date.now() - new Date(value).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function makeStep(
  id: PipelineStepId,
  status: PipelineStepStatus,
  updatedAt: string | null,
  detail: string | null = null,
): PipelineStep {
  return { id, label: STEP_LABELS[id], status, updatedAt, detail };
}

export function derivePipelineSteps(
  record: IncidentRecord,
  liveEvents: PipelineStepEvent[],
): PipelineStep[] {
  const steps: Record<PipelineStepId, PipelineStep> = {
    ingested: makeStep("ingested", "completed", record.createdAt),
    analyzing: makeStep("analyzing", "pending", null),
    analyzed: makeStep("analyzed", "pending", null),
    pr_opening: makeStep("pr_opening", "pending", null),
    pr_ready: makeStep("pr_ready", "pending", null),
  };

  for (const ev of liveEvents) {
    if (ev.incidentId !== record.incident.incidentId) continue;
    const stamp = new Date().toISOString();
    if (ev.step === "analyzing") {
      if (ev.status === "running") {
        steps.analyzing = makeStep("analyzing", "running", stamp);
      } else if (ev.status === "completed") {
        steps.analyzing = makeStep("analyzing", "completed", stamp);
        steps.analyzed = makeStep("analyzed", "completed", stamp);
      } else if (ev.status === "failed") {
        steps.analyzing = makeStep("analyzing", "failed", stamp, ev.error ?? null);
      }
    } else if (ev.step === "pr_opening") {
      if (ev.status === "running") {
        steps.pr_opening = makeStep("pr_opening", "running", stamp);
      } else if (ev.status === "completed") {
        steps.pr_opening = makeStep(
          "pr_opening",
          "completed",
          stamp,
          ev.prUrl ?? null,
        );
        steps.pr_ready = makeStep("pr_ready", "completed", stamp, ev.prUrl ?? null);
      } else if (ev.status === "failed") {
        steps.pr_opening = makeStep("pr_opening", "failed", stamp, ev.error ?? null);
      }
    }
  }

  return STEP_ORDER.map((id) => steps[id]);
}

type PipStyle = { bg: string; icon: typeof CheckCircle2 | null };

function pipStyle(status: PipelineStepStatus): PipStyle {
  switch (status) {
    case "running":
      return { bg: "bg-cyan-400", icon: Loader2 };
    case "completed":
      return { bg: "bg-emerald-400", icon: CheckCircle2 };
    case "failed":
      return { bg: "bg-red-500", icon: AlertCircle };
    default:
      return { bg: "bg-slate-600/40", icon: null };
  }
}


export function CompactPipelineBar({ steps }: { steps: PipelineStep[] }) {
  const onlyIngestedDone = steps.every(
    (s) => s.id === "ingested" || s.status === "pending",
  );
  return (
    <div className="flex items-center gap-1">
      {steps.map((step, idx) => {
        const { bg, icon: Icon } = pipStyle(step.status);
        const prevCompleted =
          idx > 0 && steps[idx - 1].status === "completed";
        const showZap = onlyIngestedDone && step.id === "ingested";
        return (
          <div key={step.id} className="flex items-center gap-1">
            <motion.div
              layout
              transition={{ duration: 0.25 }}
              className={`relative flex h-3 w-3 items-center justify-center rounded-full ${bg}`}
              title={`${step.label}: ${step.status}`}
            >
              {showZap ? (
                <Zap className="w-2 h-2 text-slate-900" />
              ) : Icon ? (
                <Icon
                  className={`w-2 h-2 text-slate-900 ${step.status === "running" ? "animate-spin" : ""}`}
                />
              ) : null}
            </motion.div>
            {idx < steps.length - 1 ? (
              <div
                className={`h-px w-4 ${prevCompleted ? "bg-emerald-400/60" : "bg-white/10"}`}
              />
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function statusBadge(status: PipelineStepStatus): string {
  switch (status) {
    case "running":
      return "border-cyan-400/30 bg-cyan-500/10 text-cyan-300";
    case "completed":
      return "border-emerald-400/30 bg-emerald-500/10 text-emerald-300";
    case "failed":
      return "border-red-400/30 bg-red-500/10 text-red-300";
    default:
      return "border-white/10 bg-white/[0.02] text-slate-500";
  }
}

export function FullPipelineView({ steps }: { steps: PipelineStep[] }) {
  return (
    <div className="glass-card p-6">
      <div className="flex items-center justify-between mb-5">
        <h2 className="text-sm font-bold uppercase tracking-[0.22em] text-slate-400">
          Pipeline Progress
        </h2>
      </div>
      <ol className="space-y-3">
        <AnimatePresence initial={false}>
          {steps.map((step) => {
            const { bg, icon: Icon } = pipStyle(step.status);
            const isPrUrl =
              step.id === "pr_opening" &&
              step.status === "completed" &&
              !!step.detail &&
              /^https?:\/\//.test(step.detail);
            return (
              <motion.li
                key={step.id}
                layout
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="flex items-center gap-4"
              >
                <div
                  className={`flex h-2.5 w-2.5 items-center justify-center rounded-full ${bg}`}
                >
                  {Icon ? (
                    <Icon
                      className={`w-2 h-2 text-slate-900 ${step.status === "running" ? "animate-spin" : ""}`}
                    />
                  ) : null}
                </div>
                <span className="text-sm font-semibold text-white flex-1">
                  {step.label}
                </span>
                <span
                  className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-[0.2em] ${statusBadge(step.status)}`}
                >
                  {step.status}
                </span>
                <time className="text-[0.65rem] text-slate-500 w-16 text-right tabular-nums">
                  {relativeTime(step.updatedAt)}
                </time>
                {step.detail ? (
                  <div className="basis-full pl-6 text-xs font-mono text-slate-400">
                    {isPrUrl ? (
                      <a
                        href={step.detail}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1.5 text-cyan-300 hover:text-cyan-200"
                      >
                        <ExternalLink className="w-3 h-3" />
                        {step.detail}
                      </a>
                    ) : (
                      step.detail
                    )}
                  </div>
                ) : null}
              </motion.li>
            );
          })}
        </AnimatePresence>
      </ol>
    </div>
  );
}
