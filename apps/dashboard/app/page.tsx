import React from "react";

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
  if (!value) return "Pending Review";
  const date = new Date(value);
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "numeric",
  }).format(date);
}

// Icons
const SentryIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
);
const AgentIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>
);
const IDEIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="9" y1="3" x2="9" y2="21"/></svg>
);
const PRIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M13 6h3a2 2 0 0 1 2 2v7"/><line x1="6" y1="9" x2="6" y2="21"/></svg>
);
const ArrowRight = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-slate-300"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
);

function FlowDiagram() {
  return (
    <div className="w-full rounded-3xl bg-white border border-slate-200/60 p-8 shadow-sm animate-slide-up mb-10 overflow-hidden relative">
      <div className="absolute top-0 right-0 p-8 opacity-5">
        <svg width="150" height="150" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
      </div>
      <h3 className="text-lg font-semibold text-slate-800 mb-6">SecureLoop Execution Pipeline</h3>
      <div className="flex flex-col md:flex-row items-center justify-between gap-4 md:gap-2">
        <div className="flex flex-col items-center">
          <div className="w-16 h-16 rounded-full bg-red-50 text-red-500 border border-red-100 flex items-center justify-center mb-3 shadow-sm">
            <SentryIcon />
          </div>
          <span className="text-sm font-semibold text-slate-700">1. Detection</span>
          <span className="text-xs text-slate-500 text-center max-w-[120px] mt-1">Sentry captures runtime exception</span>
        </div>
        <div className="hidden md:block"><ArrowRight /></div>
        
        <div className="flex flex-col items-center">
          <div className="w-16 h-16 rounded-full bg-blue-50 text-blue-500 border border-blue-100 flex items-center justify-center mb-3 shadow-sm animate-pulse-soft">
            <AgentIcon />
          </div>
          <span className="text-sm font-semibold text-slate-700">2. Synchronization</span>
          <span className="text-xs text-slate-500 text-center max-w-[120px] mt-1">Agent parses context & maps locally</span>
        </div>
        <div className="hidden md:block"><ArrowRight /></div>
        
        <div className="flex flex-col items-center opacity-90 transition hover:opacity-100">
          <div className="w-16 h-16 rounded-2xl bg-amber-50 text-amber-500 border border-amber-100 flex items-center justify-center mb-3 shadow-sm">
            <IDEIcon />
          </div>
          <span className="text-sm font-semibold text-slate-700">3. Resolution</span>
          <span className="text-xs text-slate-500 text-center max-w-[120px] mt-1">Developer approves AI patch in IDE</span>
        </div>
        <div className="hidden md:block"><ArrowRight /></div>
        
        <div className="flex flex-col items-center opacity-90 transition hover:opacity-100">
          <div className="w-16 h-16 rounded-xl bg-emerald-50 text-emerald-500 border border-emerald-100 flex items-center justify-center mb-3 shadow-sm">
            <PRIcon />
          </div>
          <span className="text-sm font-semibold text-slate-700">4. Deployment</span>
          <span className="text-xs text-slate-500 text-center max-w-[120px] mt-1">Secure GitHub PR merged directly</span>
        </div>
      </div>
    </div>
  );
}

function CodeSnippet({ code, startLine }: { code: string; startLine: number | null }) {
  if (!code) return null;
  const lines = code.trim().split("\\n");
  const base = startLine || 1;
  return (
    <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 overflow-hidden text-sm font-mono shadow-inner">
      {lines.map((line, i) => (
        <div key={i} className="flex">
          <div className="w-12 shrink-0 border-r border-slate-200 bg-slate-100 py-1 pr-3 text-right text-slate-400 select-none">
            {base + i}
          </div>
          <div className="py-1 px-4 text-slate-700 whitespace-pre overflow-x-auto">
            {line}
          </div>
        </div>
      ))}
    </div>
  );
}

function IncidentCard({ record }: { record: IncidentRecord }) {
  const isOpen = record.status === "open";
  const location = [record.incident.repoRelativePath, record.incident.lineNumber]
    .filter(Boolean)
    .join(":");

  return (
    <article className="group relative rounded-2xl border border-slate-200/60 bg-white p-6 shadow-sm transition-all hover:shadow-md hover:-translate-y-0.5">
      <div className="absolute top-0 right-0 p-6">
        <a
          href={record.incident.eventWebUrl}
          target="_blank"
          rel="noreferrer"
          className="rounded-full bg-slate-50 border border-slate-200 px-4 py-1.5 text-xs font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
        >
          View in Sentry &rarr;
        </a>
      </div>

      <div className="flex items-center gap-3 mb-4">
        <span
          className={`flex h-2.5 w-2.5 rounded-full ${isOpen ? "bg-amber-400 animate-pulse-soft" : "bg-emerald-400"}`}
        />
        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
          {isOpen ? "Action Required in IDE" : "Resolved & Patched"}
        </h2>
      </div>

      <h3 className="text-xl font-bold text-slate-900 mb-1">
        {record.incident.exceptionType}
      </h3>
      <p className="text-sm font-medium text-slate-600 max-w-[80%]">
        {record.incident.exceptionMessage}
      </p>

      <div className="mt-6 grid grid-cols-2 lg:grid-cols-4 gap-4 border-t border-slate-100 pt-5">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-1">Location</p>
          <p className="font-mono text-xs text-slate-700 truncate" title={location || "N/A"}>
            {location || "N/A"}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-1">Function</p>
          <p className="font-mono text-xs text-slate-700 truncate">
            {record.incident.functionName || "root"}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-1">Env</p>
          <span className="inline-flex rounded-md bg-slate-100 border border-slate-200 px-2 py-0.5 text-xs text-slate-600 capitalize">
            {record.incident.environment || "production"}
          </span>
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-1">Status</p>
          <p className="text-xs font-medium text-slate-700">
            {isOpen ? formatTimestamp(record.createdAt) : formatTimestamp(record.reviewedAt)}
          </p>
        </div>
      </div>

      <CodeSnippet code={record.incident.codeContext || ""} startLine={record.incident.lineNumber} />

      {!isOpen && (
        <div className="mt-4 rounded-xl bg-emerald-50/50 border border-emerald-100 p-4">
          <p className="text-xs font-semibold text-emerald-800 mb-1 flex items-center gap-2">
            <PRIcon /> Fix Approved & Deployed via AI
          </p>
          <p className="text-xs text-emerald-600">The developer successfully analyzed the root cause via SecureLoop within JetBrains and approved the generated patch.</p>
        </div>
      )}
    </article>
  );
}

export default async function Home() {
  const { health, feed, error, agentBaseUrl } = await fetchDashboardData();
  const incidents = feed?.incidents ?? [];
  const openIncidents = incidents.filter((record) => record.status === "open");
  const reviewedIncidents = incidents.filter((record) => record.status === "reviewed");

  const isConnected = health?.status === "ok";

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900 pb-20">
      {/* Premium Header */}
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-md border-b border-slate-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold text-lg shadow-sm">
              S
            </div>
            <span className="font-bold text-lg tracking-tight text-slate-800">SecureLoop</span>
          </div>
          <div className="flex items-center gap-4">
            <a href="/" className="text-sm font-medium text-slate-500 hover:text-blue-600 transition">Refresh</a>
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-bold uppercase tracking-wider ${isConnected ? 'bg-emerald-50 text-emerald-600 border border-emerald-200' : 'bg-red-50 text-red-600 border border-red-200'}`}>
              <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-500 animate-pulse-soft' : 'bg-red-500'}`} />
              {isConnected ? "Agent Connected" : "Agent Offline"}
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 mt-10">
        <FlowDiagram />

        {!isConnected && (
          <div className="rounded-2xl border border-red-200 bg-red-50 p-6 mb-8 shadow-sm">
            <h3 className="text-sm font-bold text-red-800 mb-1">Connection Error</h3>
            <p className="text-sm text-red-600 mb-3">{error || `Failed to poll ${agentBaseUrl}`}</p>
            <p className="text-sm text-red-800">Please ensure the SecureLoop python agent is running via <code>uv run main.py</code> and that <code>pnpm dev</code> was started properly.</p>
          </div>
        )}

        {/* Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12 animate-slide-up delay-100">
          <div className="rounded-2xl bg-white border border-slate-200 p-6 shadow-sm flex items-center justify-between">
            <div>
              <p className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-2">Total Queue</p>
              <p className="text-4xl font-light tracking-tight text-slate-800">{feed?.summary.totalCount ?? 0}</p>
            </div>
            <div className="w-12 h-12 rounded-full bg-slate-50 border border-slate-100 flex items-center justify-center text-slate-400">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
            </div>
          </div>
          <div className="rounded-2xl bg-white border border-slate-200 p-6 shadow-sm flex items-center justify-between">
            <div>
              <p className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-2">Needs Repair</p>
              <p className="text-4xl font-light tracking-tight text-amber-500">{feed?.summary.openCount ?? 0}</p>
            </div>
            <div className="w-12 h-12 rounded-full bg-amber-50 border border-amber-100 flex items-center justify-center text-amber-500">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            </div>
          </div>
          <div className="rounded-2xl bg-white border border-slate-200 p-6 shadow-sm flex items-center justify-between">
            <div>
              <p className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-2">Secured</p>
              <p className="text-4xl font-light tracking-tight text-emerald-500">{feed?.summary.reviewedCount ?? 0}</p>
            </div>
            <div className="w-12 h-12 rounded-full bg-emerald-50 border border-emerald-100 flex items-center justify-center text-emerald-500">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
            </div>
          </div>
        </div>

        {/* Dashboard Columns */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-8 animate-slide-up delay-200">
          {/* Action Column */}
          <section className="flex flex-col gap-5">
            <h2 className="text-xl font-bold tracking-tight text-slate-800 flex items-center gap-2">
              Action Required <span className="bg-amber-100 text-amber-700 text-xs px-2 py-0.5 rounded-full">{openIncidents.length}</span>
            </h2>
            {openIncidents.length > 0 ? (
              openIncidents.map((record) => (
                <IncidentCard key={record.incident.incidentId} record={record} />
              ))
            ) : (
              <div className="rounded-2xl border-2 border-dashed border-slate-200 bg-slate-50/50 p-10 text-center">
                <p className="text-sm font-medium text-slate-500 mb-1">Queue is empty</p>
                <p className="text-xs text-slate-400">Trigger an exception in Sentry or use JetBrains Demo Mode.</p>
              </div>
            )}
          </section>

          {/* History Column */}
          <section className="flex flex-col gap-5 opacity-80 transition hover:opacity-100">
            <h2 className="text-xl font-bold tracking-tight text-slate-800 flex items-center gap-2">
              Resolution History <span className="bg-emerald-100 text-emerald-700 text-xs px-2 py-0.5 rounded-full">{reviewedIncidents.length}</span>
            </h2>
            {reviewedIncidents.length > 0 ? (
              reviewedIncidents.map((record) => (
                <IncidentCard key={record.incident.incidentId} record={record} />
              ))
            ) : (
              <div className="rounded-2xl border-2 border-dashed border-slate-200 bg-slate-50/50 p-10 text-center">
                <p className="text-sm font-medium text-slate-500 mb-1">No history yet</p>
                <p className="text-xs text-slate-400">Reviewed incidents approved via IDE will appear here.</p>
              </div>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
