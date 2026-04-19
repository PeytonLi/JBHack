package dev.secureloop.plugin.model

import kotlinx.serialization.Serializable

@Serializable
data class AnalysisPatchData(
    val repoRelativePath: String,
    val oldText: String,
    val newText: String,
)

@Serializable
data class AnalysisResponse(
    val severity: String,
    val category: String? = null,
    val owasp: String? = null,
    val cwe: String? = null,
    val title: String,
    val explanation: String,
    val violatedPolicy: List<String> = emptyList(),
    val fixPlan: List<String> = emptyList(),
    val diff: String,
    val patch: AnalysisPatchData,
)
