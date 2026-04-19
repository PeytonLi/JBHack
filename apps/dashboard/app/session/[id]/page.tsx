import Link from "next/link";
import { SessionPipelineLive } from "./session-pipeline-live";
import type { IncidentRecord } from "../../types";

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
      <main className="mx-auto max-w-4xl p-8 space-y-6">
        <Link
          href="/"
          className="text-xs font-semibold uppercase tracking-[0.22em] text-cyan-400 hover:text-cyan-300"
        >
          ← Back to queue
        </Link>
        <div className="glass-card p-6 text-sm text-slate-400">
          Incident <span className="font-mono text-slate-300">{id}</span> not
          found or agent unreachable at {agentBaseUrl}.
        </div>
      </main>
    );
  }

  const record = (await res.json()) as IncidentRecord;

  return (
    <main className="mx-auto max-w-4xl p-8 space-y-6">
      <Link
        href="/"
        className="inline-flex items-center text-xs font-semibold uppercase tracking-[0.22em] text-cyan-400 hover:text-cyan-300"
      >
        ← Back to queue
      </Link>
      <header className="glass-card p-6">
        <p className="text-[0.6rem] font-bold uppercase tracking-[0.28em] text-slate-500">
          Incident · {record.incident.incidentId}
        </p>
        <h1 className="mt-2 text-2xl font-bold text-white leading-snug tracking-tight">
          <span className="text-slate-400 font-semibold">
            {record.incident.exceptionType}
          </span>
          <span className="text-white/20 mx-2">·</span>
          {record.incident.title}
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-slate-400">
          {record.incident.exceptionMessage}
        </p>
      </header>
      <SessionPipelineLive
        incidentId={id}
        initialRecord={record}
        agentBaseUrl={agentBaseUrl}
      />
    </main>
  );
}
