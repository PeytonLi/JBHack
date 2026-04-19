package dev.secureloop.plugin.model

import kotlinx.serialization.Serializable

@Serializable
data class AnalyzeIncidentRequest(
    val incidentId: String,
    val repoRelativePath: String,
    val lineNumber: Int,
    val exceptionType: String,
    val exceptionMessage: String,
    val title: String,
    val sourceContext: String,
    val policyText: String,
)

@Serializable
data class AnalyzePatch(
    val repoRelativePath: String,
    val oldText: String,
    val newText: String,
)

@Serializable
data class DepVuln(
    val id: String,
    val severity: String,
    val `package`: String,
    val version: String,
    val fixedVersion: String? = null,
    val summary: String,
)

@Serializable
data class DepCheckResult(
    val scanner: String,
    val vulnerabilities: List<DepVuln> = emptyList(),
    val advisoryUrl: String? = null,
    val scannedAt: String,
)

@Serializable
data class AnalyzeIncidentResponse(
    val severity: String,
    val category: String,
    val cwe: String,
    val title: String,
    val explanation: String,
    val violatedPolicy: List<String>,
    val fixPlan: List<String>,
    val diff: String,
    val patch: AnalyzePatch,
    val reasoningSteps: List<String> = emptyList(),
    val rootCause: String = "",
    val fixSummary: String = "",
    val prevention: String = "",
    val impact: String = "",
    val severityRationale: String = "",
    val depCheck: DepCheckResult? = null,
)

@Serializable
data class PullRequestResult(
    val prUrl: String? = null,
    val prNumber: Int? = null,
    val branch: String? = null,
    val localArtifactPath: String? = null,
    val error: String? = null,
)

sealed interface AnalysisState {
    data object Idle : AnalysisState

    data object Loading : AnalysisState

    data object Ready : AnalysisState

    data object Applying : AnalysisState

    data class Applied(val stagedInGit: Boolean = false) : AnalysisState

    data object Failed : AnalysisState
}
