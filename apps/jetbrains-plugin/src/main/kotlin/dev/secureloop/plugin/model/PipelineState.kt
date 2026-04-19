package dev.secureloop.plugin.model

import kotlinx.serialization.Serializable

enum class PipelineStepId(val wire: String) {
    FETCH_SOURCE("fetch_source"),
    ANALYZE("analyze"),
    SANDBOX("sandbox"),
    OPEN_PR("open_pr");

    companion object {
        fun fromWire(value: String?): PipelineStepId? =
            values().firstOrNull { it.wire == value }
    }
}

@Serializable
data class PipelineEventPayload(
    val incidentId: String,
    val step: String? = null,
    val reason: String? = null,
    val detail: String? = null,
    val path: String? = null,
    val traceback: String? = null,
    val prUrl: String? = null,
    val prNumber: Int? = null,
    val branch: String? = null,
    val localArtifactPath: String? = null,
    val error: String? = null,
)

sealed interface PipelineState {
    val incidentId: String

    data class Running(
        override val incidentId: String,
        val step: PipelineStepId,
    ) : PipelineState

    data class Completed(
        override val incidentId: String,
        val prUrl: String?,
        val prNumber: Int?,
        val branch: String?,
        val localArtifactPath: String?,
    ) : PipelineState

    data class Failed(
        override val incidentId: String,
        val reason: String,
        val detail: String? = null,
    ) : PipelineState
}

object PipelineFailureReasons {
    fun label(reason: String): String = when (reason) {
        "incident_not_found" -> "Incident not found"
        "missing_source_metadata" -> "Missing source metadata"
        "source_file_not_found" -> "Source file not found"
        "patch_mismatch" -> "Patch did not apply"
        "sandbox_test_generation_failed" -> "Test generation failed"
        "sandbox_did_not_reproduce" -> "Did not reproduce bug"
        "sandbox_fix_failed" -> "Fix did not pass sandbox"
        "sandbox_timeout" -> "Sandbox timed out"
        "sandbox_runner_error" -> "Sandbox runner error"
        "internal_error" -> "Internal error"
        else -> reason
    }
}
