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

export function SessionPipelineLive({
  incidentId,
  initialRecord,
  agentBaseUrl,
}: Props) {
  const [record, setRecord] = useState<IncidentRecord>(initialRecord);
  const [events, setEvents] = useState<PipelineStepEvent[]>([]);

  useEffect(() => {
    const source = new EventSource(`${agentBaseUrl}/dashboard/events/stream`);

    const handlePipelineEvent = (evt: MessageEvent) => {
      try {
        const ev = JSON.parse(evt.data) as PipelineStepEvent;
        if (!ev || ev.incidentId !== incidentId) return;
        if (typeof ev.step !== "string" || typeof ev.status !== "string") {
          return;
        }
        setEvents((prev) => [...prev, ev]);
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

    source.addEventListener("pipeline.step", handlePipelineEvent);
    source.addEventListener("pipeline.completed", handlePipelineEvent);
    source.addEventListener("pipeline.failed", handlePipelineEvent);
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
        <h2 className="text-sm font-bold uppercase tracking-[0.22em] text-slate-400 mb-4">
          Incident Detail
        </h2>
        <dl className="grid gap-4 text-sm text-slate-400 md:grid-cols-2">
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
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-amber-300/8">
            <span className="text-[0.65rem] font-semibold uppercase tracking-[0.2em] text-amber-400/50">
              Code Context
            </span>
          </div>
          <pre className="overflow-x-auto p-4 text-sm leading-6 text-amber-100/80 font-mono">
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
      <dt className="text-[0.6rem] font-bold uppercase tracking-[0.24em] text-slate-500">
        {label}
      </dt>
      <dd
        className={`text-sm text-slate-200 ${mono ? "font-mono" : ""}`}
      >
        {value}
      </dd>
    </div>
  );
}
