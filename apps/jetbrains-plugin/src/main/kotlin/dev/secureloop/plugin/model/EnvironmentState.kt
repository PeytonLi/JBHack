package dev.secureloop.plugin.model

import kotlinx.serialization.Serializable

@Serializable
data class AgentHealthResponse(
    val status: String,
    val sqlitePath: String? = null,
    val ideTokenFile: String? = null,
    val allowDebugEndpoints: Boolean = false,
)

sealed interface AgentConnectionState {
    data object Connecting : AgentConnectionState

    data class Connected(
        val baseUrl: String,
        val demoModeAvailable: Boolean,
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

    data class Unsupported(
        val reason: String,
    ) : ProjectCompatibilityState
}
