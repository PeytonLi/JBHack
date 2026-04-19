import Link from "next/link";
import { SessionPipelineLive } from "./session-pipeline-live";
import type { IncidentRecord, PipelineStateRow } from "../../types";

const agentBaseUrl =
  process.env.NEXT_PUBLIC_SECURE_LOOP_AGENT_URL?.trim() ||
  "http://127.0.0.1:8001";

export default async function SessionPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const res = await fetch(`${agentBaseUrl}/incidents/${id}`, {
    cache: "no-store",
    headers: { Accept: "application/json" },
  }).catch(() => null);

  if (!res || !res.ok) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-10 space-y-6">
        <Link
          href="/"
          className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500 hover:text-slate-900"
        >
          ← Back to queue
        </Link>
        <div className="glass-card p-6 text-sm text-slate-600">
          Incident <span className="font-mono text-slate-900">{id}</span> not
          found or agent unreachable at{" "}
          <span className="font-mono">{agentBaseUrl}</span>.
        </div>
      </main>
    );
  }

  const record = (await res.json()) as IncidentRecord;

  let initialPipelineState: PipelineStateRow | null = null;
  try {
    const pipelineStateRes = await fetch(
      `${agentBaseUrl}/incidents/${id}/pipeline-state`,
      { cache: "no-store", headers: { Accept: "application/json" } },
    );
    if (pipelineStateRes.ok) {
      initialPipelineState = (await pipelineStateRes.json()) as
        | PipelineStateRow
        | null;
    }
  } catch {
    initialPipelineState = null;
  }

  return (
    <main className="mx-auto max-w-4xl px-6 py-10 space-y-6">
      <Link
        href="/"
        className="inline-flex items-center text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500 hover:text-slate-900"
      >
        ← Back to queue
      </Link>
      <header className="glass-card p-6">
        <p className="text-[10px] font-semibold uppercase tracking-[0.28em] text-slate-400">
          Incident · {record.incident.incidentId}
        </p>
        <h1 className="mt-2 text-2xl font-bold text-slate-900 leading-snug tracking-tight">
          <span className="text-slate-500 font-semibold">
            {record.incident.exceptionType}
          </span>
          <span className="text-slate-300 mx-2">·</span>
          {record.incident.title}
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-slate-600">
          {record.incident.exceptionMessage}
        </p>
      </header>
      <SessionPipelineLive
        incidentId={id}
        initialRecord={record}
        initialPipelineState={initialPipelineState}
        agentBaseUrl={agentBaseUrl}
      />
    </main>
  );
}
