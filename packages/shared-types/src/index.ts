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
