"use client";

import { useEffect, useMemo, useState } from "react";
import type { IncidentFeedResponse, IncidentRecord, SentryResolutionStatus } from "./types";

type Props = {
  initialFeed: IncidentFeedResponse | null;
  agentBaseUrl: string;
};

function formatTimestamp(value: string | null): string {
  if (!value) return "Not yet reviewed";
  const date = new Date(value);
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function statusClasses(status: IncidentRecord["status"]): string {
  return status === "open"
    ? "border-red-500/40 bg-red-500/10 text-red-100"
    : "border-emerald-500/40 bg-emerald-500/10 text-emerald-100";
}

function sentryStatusClasses(value: SentryResolutionStatus | null): string {
  switch (value) {
    case "resolved":
      return "border-emerald-500/40 bg-emerald-500/10 text-emerald-100";
    case "ignored":
      return "border-slate-500/40 bg-slate-500/10 text-slate-200";
    default:
      return "border-amber-500/40 bg-amber-500/10 text-amber-100";
  }
}

function upsertById(prev: IncidentRecord[], incoming: IncidentRecord): IncidentRecord[] {
  const id = incoming.incident.incidentId;
  const next = prev.filter((record) => record.incident.incidentId !== id);
  next.unshift(incoming);
  next.sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));
  return next;
}

export function IncidentStream({ initialFeed, agentBaseUrl }: Props) {
  const [records, setRecords] = useState<IncidentRecord[]>(
    initialFeed?.incidents ?? [],
  );
  const [connected, setConnected] = useState(false);

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
    return () => source.close();
  }, [agentBaseUrl]);

  const openIncidents = useMemo(
    () => records.filter((record) => record.status === "open"),
    [records],
  );
  const reviewedIncidents = useMemo(
    () => records.filter((record) => record.status === "reviewed"),
    [records],
  );

  return (
    <section className="grid gap-6 xl:grid-cols-2">
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-2xl font-semibold text-white">Open Incidents</h2>
          <div className="flex items-center gap-3">
            <LiveIndicator connected={connected} />
            <span className="rounded-full border border-red-500/30 bg-red-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-red-100">
              {openIncidents.length} active
            </span>
          </div>
        </div>
        {openIncidents.length > 0 ? (
          openIncidents.map((record) => (
            <IncidentCard key={record.incident.incidentId} record={record} />
          ))
        ) : (
          <div className="rounded-[2rem] border border-dashed border-white/15 bg-white/5 p-8 text-sm leading-7 text-slate-300">
            No open incidents are waiting in the queue. Trigger `Run Demo` in
            the plugin or hit the broken checkout path to generate one.
          </div>
        )}
      </div>

      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-2xl font-semibold text-white">Reviewed History</h2>
          <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-emerald-100">
            {reviewedIncidents.length} reviewed
          </span>
        </div>
        {reviewedIncidents.length > 0 ? (
          reviewedIncidents.map((record) => (
            <IncidentCard key={record.incident.incidentId} record={record} />
          ))
        ) : (
          <div className="rounded-[2rem] border border-dashed border-white/15 bg-white/5 p-8 text-sm leading-7 text-slate-300">
            Reviewed incidents appear here after a developer clicks
            `Mark Reviewed` inside the SecureLoop tool window.
          </div>
        )}
      </div>
    </section>
  );
}

function LiveIndicator({ connected }: { connected: boolean }) {
  const dotClass = connected
    ? "bg-emerald-400 shadow-[0_0_0_4px_rgba(16,185,129,0.15)]"
    : "bg-amber-400 shadow-[0_0_0_4px_rgba(251,191,36,0.15)]";
  return (
    <span className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs uppercase tracking-[0.2em] text-slate-200">
      <span className={`h-2 w-2 rounded-full ${dotClass}`} />
      {connected ? "Live" : "Reconnecting"}
    </span>
  );
}

function IncidentCard({ record }: { record: IncidentRecord }) {
  const location = [record.incident.repoRelativePath, record.incident.lineNumber]
    .filter(Boolean)
    .join(":");
  const sentryStatus = record.incident.sentryStatus ?? "unresolved";

  return (
    <article className="rounded-3xl border border-white/10 bg-slate-950/70 p-5 shadow-[0_20px_60px_rgba(15,23,42,0.35)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] ${statusClasses(record.status)}`}
            >
              {record.status}
            </span>
            <span
              className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] ${sentryStatusClasses(record.incident.sentryStatus)}`}
            >
              {sentryStatus}
            </span>
            <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs uppercase tracking-[0.22em] text-slate-300">
              {record.incident.environment ?? "unknown env"}
            </span>
          </div>
          <h2 className="text-xl font-semibold text-white">
            {record.incident.exceptionType}: {record.incident.title}
          </h2>
          <p className="max-w-2xl text-sm leading-6 text-slate-300">
            {record.incident.exceptionMessage}
          </p>
        </div>

        <a
          className="rounded-full border border-cyan-400/30 bg-cyan-400/10 px-4 py-2 text-sm font-medium text-cyan-100 transition hover:border-cyan-300/60 hover:bg-cyan-400/20"
          href={record.incident.eventWebUrl}
          target="_blank"
          rel="noreferrer"
        >
          Open Sentry
        </a>
      </div>

      <dl className="mt-5 grid gap-3 text-sm text-slate-300 md:grid-cols-2">
        <div className="rounded-2xl border border-white/8 bg-white/5 p-4">
          <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Location</dt>
          <dd className="mt-2 font-mono text-sm text-slate-100">
            {location || "Location unavailable"}
          </dd>
        </div>
        <div className="rounded-2xl border border-white/8 bg-white/5 p-4">
          <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Function</dt>
          <dd className="mt-2 font-mono text-sm text-slate-100">
            {record.incident.functionName ?? "Unknown function"}
          </dd>
        </div>
        <div className="rounded-2xl border border-white/8 bg-white/5 p-4">
          <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Received</dt>
          <dd className="mt-2 text-slate-100">{formatTimestamp(record.createdAt)}</dd>
        </div>
        <div className="rounded-2xl border border-white/8 bg-white/5 p-4">
          <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Review State</dt>
          <dd className="mt-2 text-slate-100">
            {record.status === "reviewed"
              ? `Reviewed ${formatTimestamp(record.reviewedAt)}`
              : "Waiting for a human review in the IDE"}
          </dd>
        </div>
      </dl>

      {record.incident.codeContext ? (
        <pre className="mt-5 overflow-x-auto rounded-2xl border border-amber-300/20 bg-amber-50/5 p-4 text-sm leading-6 text-amber-50">
          <code>{record.incident.codeContext}</code>
        </pre>
      ) : null}
    </article>
  );
}
