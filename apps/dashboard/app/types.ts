export type IncidentStatus = "open" | "reviewed";

export type SentryResolutionStatus = "unresolved" | "resolved" | "ignored";

export type NormalizedIncident = {
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
  sentryStatus: SentryResolutionStatus | null;
  assignee: string | null;
};

export type IncidentRecord = {
  incident: NormalizedIncident;
  status: IncidentStatus;
  createdAt: string;
  reviewedAt: string | null;
};

export type IncidentFeedResponse = {
  summary: {
    openCount: number;
    reviewedCount: number;
    totalCount: number;
  };
  incidents: IncidentRecord[];
};

export type AgentHealthResponse = {
  status: string;
  allowDebugEndpoints: boolean;
  openIncidentCount: number;
  reviewedIncidentCount: number;
  totalIncidentCount: number;
};

export type NavigateResponse = {
  delivered: boolean;
  subscribers: number;
  incidentId: string;
};

export type DeleteIncidentsResponse = {
  status: "all" | "open" | "reviewed";
  deletedCount: number;
  incidentIds: string[];
};

export type IncidentsClearedEvent = {
  status: "all" | "open" | "reviewed";
  deletedCount: number;
  incidentIds: string[];
};

export type AgentStatusResponse = {
  autopilotEnabled: boolean;
  githubRepo: string | null;
  codexAvailable: boolean;
};

export type AutopilotStepId = "fetch_source" | "analyze" | "open_pr";

export type AutopilotStepEvent = {
  incidentId: string;
  step: AutopilotStepId;
};

export type AutopilotCompletedEvent = {
  incidentId: string;
  prUrl: string;
  prNumber: number;
  branch?: string;
};

export type AutopilotFailedEvent = {
  incidentId: string;
  reason: string;
  path?: string;
  traceback?: string;
};

export type AutopilotStatus =
  | { phase: "idle" }
  | { phase: "running"; step: AutopilotStepId }
  | { phase: "completed"; prUrl: string; prNumber: number; branch?: string }
  | { phase: "failed"; reason: string; path?: string };

export type PipelineStepId =
  | "ingested"
  | "analyzing"
  | "analyzed"
  | "pr_opening"
  | "pr_ready";
export type PipelineStepStatus = "pending" | "running" | "completed" | "failed";
export type PipelineStepEvent = {
  incidentId: string;
  step: PipelineStepId;
  status: PipelineStepStatus;
  prUrl?: string | null;
  error?: string | null;
};
export type PipelineStep = {
  id: PipelineStepId;
  label: string;
  status: PipelineStepStatus;
  updatedAt: string | null;
  detail?: string | null;
};
