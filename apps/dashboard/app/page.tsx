import { IncidentStream } from "./incident-stream";
import type {
  AgentHealthResponse,
  IncidentFeedResponse,
} from "./types";

export const dynamic = "force-dynamic";

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

export default async function Home() {
  const { health, feed, error, agentBaseUrl } = await fetchDashboardData();

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

        <IncidentStream initialFeed={feed} agentBaseUrl={agentBaseUrl} />
      </div>
    </main>
  );
}
