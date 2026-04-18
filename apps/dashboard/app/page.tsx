export const dynamic = "force-dynamic";

type IncidentStatus = "open" | "reviewed";

type IncidentRecord = {
  incident: {
    incidentId: string;
    issueId: string;
    title: string;
    projectSlug: string | null;
    environment: string | null;
    exceptionType: string;
    exceptionMessage: string;
    repoRelativePath: string | null;
    lineNumber: number | null;
    functionName: string | null;
    codeContext: string | null;
    eventWebUrl: string;
    receivedAt: string;
  };
  status: IncidentStatus;
  createdAt: string;
  reviewedAt: string | null;
};

type IncidentFeedResponse = {
  summary: {
    openCount: number;
    reviewedCount: number;
    totalCount: number;
  };
  incidents: IncidentRecord[];
};

type AgentHealthResponse = {
  status: string;
  allowDebugEndpoints: boolean;
  openIncidentCount: number;
  reviewedIncidentCount: number;
  totalIncidentCount: number;
};

type DashboardData = {
  health: AgentHealthResponse | null;
  feed: IncidentFeedResponse | null;
  error: string | null;
  agentBaseUrl: string;
};

const agentBaseUrl =
  process.env.SECURE_LOOP_AGENT_URL?.trim() || "http://127.0.0.1:8001";

async function fetchDashboardData(): Promise<DashboardData> {
  try {
    const [healthResponse, feedResponse] = await Promise.all([
      fetch(`${agentBaseUrl}/health`, {
        cache: "no-store",
        headers: { Accept: "application/json" },
      }),
      fetch(`${agentBaseUrl}/incidents?status=all&limit=40`, {
        cache: "no-store",
        headers: { Accept: "application/json" },
      }),
    ]);

    if (!healthResponse.ok || !feedResponse.ok) {
      return {
        health: null,
        feed: null,
        error: `SecureLoop agent responded with HTTP ${healthResponse.status}/${feedResponse.status}.`,
        agentBaseUrl,
      };
    }

    return {
      health: (await healthResponse.json()) as AgentHealthResponse,
      feed: (await feedResponse.json()) as IncidentFeedResponse,
      error: null,
      agentBaseUrl,
    };
  } catch {
    return {
      health: null,
      feed: null,
      error:
        "The dashboard could not reach the local SecureLoop agent. Start `pnpm dev` first.",
      agentBaseUrl,
    };
  }
}

function formatTimestamp(value: string | null): string {
  if (!value) {
    return "Not yet reviewed";
  }

  const date = new Date(value);
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function statusClasses(status: IncidentStatus): string {
  return status === "open"
    ? "border-red-500/40 bg-red-500/10 text-red-100"
    : "border-emerald-500/40 bg-emerald-500/10 text-emerald-100";
}

function IncidentCard({ record }: { record: IncidentRecord }) {
  const location = [record.incident.repoRelativePath, record.incident.lineNumber]
    .filter(Boolean)
    .join(":");

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
          <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">
            Location
          </dt>
          <dd className="mt-2 font-mono text-sm text-slate-100">
            {location || "Location unavailable"}
          </dd>
        </div>
        <div className="rounded-2xl border border-white/8 bg-white/5 p-4">
          <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">
            Function
          </dt>
          <dd className="mt-2 font-mono text-sm text-slate-100">
            {record.incident.functionName ?? "Unknown function"}
          </dd>
        </div>
        <div className="rounded-2xl border border-white/8 bg-white/5 p-4">
          <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">
            Received
          </dt>
          <dd className="mt-2 text-slate-100">
            {formatTimestamp(record.createdAt)}
          </dd>
        </div>
        <div className="rounded-2xl border border-white/8 bg-white/5 p-4">
          <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">
            Review State
          </dt>
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

export default async function Home() {
  const { health, feed, error, agentBaseUrl } = await fetchDashboardData();
  const incidents = feed?.incidents ?? [];
  const openIncidents = incidents.filter((record) => record.status === "open");
  const reviewedIncidents = incidents.filter(
    (record) => record.status === "reviewed",
  );

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,rgba(34,211,238,0.18),transparent_32%),linear-gradient(180deg,#020617_0%,#0f172a_52%,#111827_100%)] text-slate-100">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-10 px-6 py-12 lg:px-10">
        <section className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
          <div className="rounded-[2rem] border border-white/10 bg-slate-950/55 p-8 shadow-[0_30px_100px_rgba(15,23,42,0.45)] backdrop-blur">
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-cyan-300">
              SecureLoop Dashboard
            </p>
            <h1 className="mt-4 max-w-3xl text-4xl font-semibold tracking-tight text-white sm:text-5xl">
              Local incident queue and review state for the current SecureLoop
              MVP.
            </h1>
            <p className="mt-4 max-w-2xl text-base leading-7 text-slate-300">
              This dashboard reflects the real companion service contract: raw
              incidents in, human review in the IDE, reviewed history retained
              in the local queue. It does not pretend the AI analysis pipeline
              exists yet.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <a
                className="rounded-full border border-cyan-300/30 bg-cyan-300/10 px-5 py-3 text-sm font-semibold text-cyan-100 transition hover:border-cyan-200/60 hover:bg-cyan-300/20"
                href="/"
              >
                Refresh Dashboard
              </a>
              <a
                className="rounded-full border border-white/10 bg-white/5 px-5 py-3 text-sm font-semibold text-white transition hover:border-white/20 hover:bg-white/10"
                href="https://www.jetbrains.com/help/idea/run-debug-configuration-gradle.html"
                target="_blank"
                rel="noreferrer"
              >
                Run `runIde`
              </a>
            </div>
          </div>

          <div className="grid gap-4">
            <div className="rounded-[2rem] border border-white/10 bg-white/5 p-6 backdrop-blur">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-400">
                Agent
              </p>
              <h2 className="mt-3 text-2xl font-semibold text-white">
                {health?.status === "ok" ? "Connected" : "Unavailable"}
              </h2>
              <p className="mt-2 text-sm leading-6 text-slate-300">
                {error ?? `Polling ${agentBaseUrl} for health and incident data.`}
              </p>
              <p className="mt-4 text-xs uppercase tracking-[0.24em] text-slate-500">
                Demo mode
              </p>
              <p className="mt-2 text-sm text-slate-200">
                {health?.allowDebugEndpoints
                  ? "Enabled for Run Demo and debug incident injection."
                  : "Disabled until SECURE_LOOP_ALLOW_DEBUG_ENDPOINTS=1 is set."}
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              {[
                {
                  label: "Open incidents",
                  value: feed?.summary.openCount ?? 0,
                  accent: "text-red-200",
                },
                {
                  label: "Reviewed incidents",
                  value: feed?.summary.reviewedCount ?? 0,
                  accent: "text-emerald-200",
                },
                {
                  label: "Total incidents",
                  value: feed?.summary.totalCount ?? 0,
                  accent: "text-cyan-100",
                },
              ].map((stat) => (
                <div
                  key={stat.label}
                  className="rounded-[1.75rem] border border-white/10 bg-slate-950/55 p-5"
                >
                  <p className="text-xs uppercase tracking-[0.22em] text-slate-500">
                    {stat.label}
                  </p>
                  <p className={`mt-3 text-3xl font-semibold ${stat.accent}`}>
                    {stat.value}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-2">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-2xl font-semibold text-white">
                Open Incidents
              </h2>
              <span className="rounded-full border border-red-500/30 bg-red-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-red-100">
                {openIncidents.length} active
              </span>
            </div>
            {openIncidents.length > 0 ? (
              openIncidents.map((record) => (
                <IncidentCard
                  key={record.incident.incidentId}
                  record={record}
                />
              ))
            ) : (
              <div className="rounded-[2rem] border border-dashed border-white/15 bg-white/5 p-8 text-sm leading-7 text-slate-300">
                No open incidents are waiting in the queue. Trigger `Run Demo`
                in the plugin or hit the broken checkout path to generate one.
              </div>
            )}
          </div>

          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-2xl font-semibold text-white">
                Reviewed History
              </h2>
              <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-emerald-100">
                {reviewedIncidents.length} reviewed
              </span>
            </div>
            {reviewedIncidents.length > 0 ? (
              reviewedIncidents.map((record) => (
                <IncidentCard
                  key={record.incident.incidentId}
                  record={record}
                />
              ))
            ) : (
              <div className="rounded-[2rem] border border-dashed border-white/15 bg-white/5 p-8 text-sm leading-7 text-slate-300">
                Reviewed incidents appear here after a developer clicks
                `Mark Reviewed` inside the SecureLoop tool window.
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
