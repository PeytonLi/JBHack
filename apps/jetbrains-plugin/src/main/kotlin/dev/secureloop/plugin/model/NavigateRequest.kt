package dev.secureloop.plugin.model

import kotlinx.serialization.Serializable

@Serializable
data class NavigateRequest(
    val incidentId: String,
    val repoRelativePath: String? = null,
    val originalFramePath: String? = null,
    val lineNumber: Int? = null,
    val functionName: String? = null,
)
