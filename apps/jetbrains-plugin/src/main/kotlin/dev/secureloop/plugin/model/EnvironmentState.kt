package dev.secureloop.plugin.model

import kotlinx.serialization.Serializable

@Serializable
data class AgentHealthResponse(
    val status: String,
    val sqlitePath: String? = null,
    val ideTokenFile: String? = null,
    val allowDebugEndpoints: Boolean = false,
    val openIncidentCount: Int = 0,
    val reviewedIncidentCount: Int = 0,
    val totalIncidentCount: Int = 0,
)

@Serializable
data class AgentStatusResponse(
    val autopilotEnabled: Boolean = false,
    val githubRepo: String? = null,
    val codexAvailable: Boolean = false,
)

sealed interface AgentConnectionState {
    data object Connecting : AgentConnectionState

    data class Connected(
        val baseUrl: String,
        val demoModeAvailable: Boolean,
        val autopilotEnabled: Boolean = false,
    ) : AgentConnectionState

    data class WaitingForAgent(
        val reason: String,
    ) : AgentConnectionState

    data class Unauthorized(
        val reason: String,
    ) : AgentConnectionState
}

sealed interface ProjectCompatibilityState {
    data class DemoReady(
        val targetPath: String,
        val policyPath: String,
    ) : ProjectCompatibilityState

    data class Supported(
        val policySource: PolicySource,
    ) : ProjectCompatibilityState

    data class Unsupported(
        val reason: String,
    ) : ProjectCompatibilityState

    sealed interface PolicySource {
        data class Project(val path: String) : PolicySource
        data object Bundled : PolicySource
    }
}
