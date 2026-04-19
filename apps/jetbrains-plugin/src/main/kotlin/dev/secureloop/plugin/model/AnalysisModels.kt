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
)

sealed interface AnalysisState {
    data object Idle : AnalysisState

    data object Loading : AnalysisState

    data object Ready : AnalysisState

    data object Applying : AnalysisState

    data object Applied : AnalysisState

    data object Failed : AnalysisState
}
