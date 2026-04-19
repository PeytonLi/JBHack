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
