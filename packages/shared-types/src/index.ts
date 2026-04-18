export type SessionStatus =
  | "pending"
  | "analyzing"
  | "reproducing"
  | "fixing"
  | "writing_coe"
  | "creating_pr"
  | "complete"
  | "failed";

export interface Session {
  id: string;
  sentry_event_id: string;
  status: SessionStatus;
  created_at: string;
  updated_at: string;
  pr_url: string | null;
}

export type StepType =
  | "parse_trace"
  | "introspect_schema"
  | "generate_sql"
  | "run_sql"
  | "generate_test"
  | "run_test"
  | "generate_fix"
  | "run_fix_test"
  | "write_coe"
  | "create_pr"
  | "step_failed"
  | "done";

export interface AgentStep {
  id: number;
  session_id: string;
  step_type: StepType;
  summary: string;
  detail: string | null;
  created_at: string;
}

export type ArtifactType = "pytest" | "fix_diff" | "coe_markdown" | "sql_query";

export interface Artifact {
  id: number;
  session_id: string;
  artifact_type: ArtifactType;
  content: string;
  created_at: string;
}

export interface SentryException {
  type: string;
  value: string;
  stacktrace?: {
    frames: Array<{
      filename: string;
      function: string;
      lineno: number;
      context_line?: string;
    }>;
  };
}

export interface SentryEvent {
  id: string;
  title: string;
  culprit: string;
  event?: {
    exception?: {
      values: SentryException[];
    };
    request?: {
      url: string;
      method: string;
      data?: unknown;
    };
    tags?: Array<{ key: string; value: string }>;
    extra?: Record<string, unknown>;
  };
  project?: {
    slug: string;
  };
  url?: string;
}

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
