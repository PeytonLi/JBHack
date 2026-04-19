"use client";

import { useEffect, useMemo, useState } from "react";
import {
  FullPipelineView,
  derivePipelineSteps,
} from "../../pipeline-progress";
import type { IncidentRecord, PipelineStepEvent } from "../../types";

type Props = {
  incidentId: string;
  initialRecord: IncidentRecord;
  agentBaseUrl: string;
};

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
  incidentId: string,
): PipelineStepEvent[] {
  if (!payload || payload.incidentId !== incidentId) return [];

  if (eventName === "pipeline.step") {
    switch (payload.step) {
      case "fetch_source":
      case "analyze":
      case "sandbox":
        return [{ incidentId, step: "analyzing", status: "running" }];
      case "open_pr":
        return [
          { incidentId, step: "analyzing", status: "completed" },
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

  const reason = payload.reason ?? "unknown";
  const failedStep = PRE_PR_FAILURE_REASONS.has(reason) ? "analyzing" : "pr_opening";
  return [
    {
      incidentId,
      step: failedStep,
      status: "failed",
      error: payload.detail ?? reason,
    },
  ];
}

export function SessionPipelineLive({
  incidentId,
  initialRecord,
  agentBaseUrl,
}: Props) {
  const [record, setRecord] = useState<IncidentRecord>(initialRecord);
  const [events, setEvents] = useState<PipelineStepEvent[]>([]);

  useEffect(() => {
    const source = new EventSource(`${agentBaseUrl}/dashboard/events/stream`);

    const handlePipelineEvent = (
      eventName: "pipeline.step" | "pipeline.completed" | "pipeline.failed",
    ) =>
      (evt: MessageEvent) => {
        try {
          const payload = JSON.parse(evt.data) as AgentPipelinePayload;
          const translated = translateAgentEvent(eventName, payload, incidentId);
          if (translated.length === 0) return;
          setEvents((prev) => [...prev, ...translated]);
        } catch {
          // ignore malformed frames
        }
      };

    const handleIncidentUpdated = (evt: MessageEvent) => {
      try {
        const payload = JSON.parse(evt.data) as IncidentRecord;
        if (!payload?.incident) return;
        if (payload.incident.incidentId !== incidentId) return;
        setRecord(payload);
      } catch {
        // ignore
      }
    };

    source.addEventListener("pipeline.step", handlePipelineEvent("pipeline.step"));
    source.addEventListener(
      "pipeline.completed",
      handlePipelineEvent("pipeline.completed"),
    );
    source.addEventListener(
      "pipeline.failed",
      handlePipelineEvent("pipeline.failed"),
    );
    source.addEventListener("incident.updated", handleIncidentUpdated);

    return () => source.close();
  }, [agentBaseUrl, incidentId]);

  const steps = useMemo(
    () => derivePipelineSteps(record, events),
    [record, events],
  );

  const location = [
    record.incident.repoRelativePath,
    record.incident.lineNumber,
  ]
    .filter(Boolean)
    .join(":");

  return (
    <div className="space-y-6">
      <FullPipelineView steps={steps} />

      <div className="glass-card p-6">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500 mb-4">
          Incident Detail
        </h2>
        <dl className="grid gap-4 text-sm text-slate-600 md:grid-cols-2">
          <SessionCell
            label="Location"
            value={location || "Location unavailable"}
            mono
          />
          <SessionCell
            label="Function"
            value={record.incident.functionName ?? "Unknown function"}
            mono
          />
          <SessionCell
            label="Environment"
            value={record.incident.environment ?? "unknown"}
          />
          <SessionCell
            label="Sentry Status"
            value={record.incident.sentryStatus ?? "unresolved"}
          />
        </dl>
      </div>

      {record.incident.codeContext ? (
        <div className="code-block overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-white/10">
            <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-400">
              Code Context
            </span>
          </div>
          <pre className="overflow-x-auto p-4 text-sm leading-6 text-slate-100 font-mono">
            <code>{record.incident.codeContext}</code>
          </pre>
        </div>
      ) : null}
    </div>
  );
}

function SessionCell({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex flex-col gap-1">
      <dt className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-400">
        {label}
      </dt>
      <dd
        className={`text-sm text-slate-900 ${mono ? "font-mono text-[12px]" : ""}`}
      >
        {value}
      </dd>
    </div>
  );
}
