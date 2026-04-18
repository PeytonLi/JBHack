package dev.secureloop.plugin.model

import kotlinx.serialization.Serializable

@Serializable
data class NormalizedIncident(
    val incidentId: String,
    val sentryEventId: String,
    val issueId: String,
    val projectSlug: String? = null,
    val environment: String? = null,
    val title: String,
    val exceptionType: String,
    val exceptionMessage: String,
    val repoRelativePath: String? = null,
    val originalFramePath: String? = null,
    val lineNumber: Int? = null,
    val functionName: String? = null,
    val codeContext: String? = null,
    val eventWebUrl: String,
    val receivedAt: String,
)
