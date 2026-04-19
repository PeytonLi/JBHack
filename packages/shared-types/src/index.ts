export type SentryResolutionStatus = "unresolved" | "resolved" | "ignored";

export interface NormalizedIncident {
  incidentId: string;
  sentryEventId: string;
  issueId: string;
  projectSlug: string | null;
  environment: string | null;
  title: string;
  exceptionType: string;
  exceptionMessage: string;
  repoRelativePath: string | null;
  originalFramePath: string | null;
  lineNumber: number | null;
  functionName: string | null;
  codeContext: string | null;
  eventWebUrl: string;
  sentryStatus: SentryResolutionStatus | null;
  assignee: string | null;
  receivedAt: string;
}

export type IncidentStatus = "open" | "reviewed";

export interface IncidentRecord {
  incident: NormalizedIncident;
  status: IncidentStatus;
  createdAt: string;
  reviewedAt: string | null;
}

export interface IncidentSummary {
  openCount: number;
  reviewedCount: number;
  totalCount: number;
}

export interface IncidentFeedResponse {
  summary: IncidentSummary;
  incidents: IncidentRecord[];
}

export type IncidentStreamEvent =
  | { type: "incident.created"; incident: IncidentRecord }
  | { type: "incident.updated"; incident: IncidentRecord };

export interface AgentHealthResponse {
  status: string;
  sqlitePath: string | null;
  ideTokenFile: string | null;
  allowDebugEndpoints: boolean;
  openIncidentCount: number;
  reviewedIncidentCount: number;
  totalIncidentCount: number;
}

export type IncidentResolution =
  | {
      status: "resolved";
      filePath: string;
      lineNumber: number;
    }
  | {
      status: "ambiguous";
      candidates: string[];
    }
  | {
      status: "unresolved";
      reason: "file_not_found" | "line_missing" | "no_open_project";
    };

export interface DepVuln {
  id: string;
  severity: string;
  package: string;
  version: string;
  fixedVersion: string | null;
  summary: string;
}

export interface DepCheckResult {
  scanner: "pip-audit";
  vulnerabilities: DepVuln[];
  advisoryUrl: string | null;
  scannedAt: string;
}

export interface AnalyzePatch {
  repoRelativePath: string;
  oldText: string;
  newText: string;
}

export interface AnalyzeIncidentResponse {
  severity: "Critical" | "High" | "Medium" | "Low";
  category: string;
  cwe: string;
  title: string;
  explanation: string;
  violatedPolicy: string[];
  fixPlan: string[];
  diff: string;
  patch: AnalyzePatch;
  reasoningSteps: string[];
  depCheck: DepCheckResult | null;
}

export interface PullRequestResult {
  prUrl: string | null;
  prNumber: number | null;
  branch: string | null;
  localArtifactPath: string | null;
  error: string | null;
}

export type PipelineStepId =
  | "ingested"
  | "analyzing"
  | "analyzed"
  | "pr_opening"
  | "pr_ready";
export type PipelineStepStatus = "pending" | "running" | "completed" | "failed";
export interface PipelineStepEvent {
  incidentId: string;
  step: PipelineStepId;
  status: PipelineStepStatus;
  prUrl?: string | null;
  error?: string | null;
}
