package dev.secureloop.plugin.model

data class IncidentPresentation(
    val incident: NormalizedIncident,
    val resolution: ResolutionState = ResolutionState.Pending,
    val reviewed: Boolean = false,
    val analysis: AnalysisResponse? = null,
)

sealed interface ResolutionState {
    data object Pending : ResolutionState

    data class Resolved(
        val filePath: String,
        val lineNumber: Int,
    ) : ResolutionState

    data class Ambiguous(
        val candidates: List<String>,
    ) : ResolutionState

    data class Unresolved(
        val reason: String,
    ) : ResolutionState
}
