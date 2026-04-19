package dev.secureloop.plugin.services

import com.intellij.util.messages.Topic
import dev.secureloop.plugin.model.AgentConnectionState
import dev.secureloop.plugin.model.NavigateRequest
import dev.secureloop.plugin.model.NormalizedIncident
import dev.secureloop.plugin.model.PipelineState

interface IncidentListener {
    fun incidentReceived(incident: NormalizedIncident)
}

interface AgentStatusListener {
    fun connectionStateChanged(state: AgentConnectionState)
}

interface NavigateListener {
    fun navigateRequested(request: NavigateRequest)
}

interface PipelineListener {
    fun pipelineStateChanged(state: PipelineState)
}

val INCIDENT_TOPIC: Topic<IncidentListener> = Topic.create(
    "SecureLoopIncidentTopic",
    IncidentListener::class.java,
)

val AGENT_STATUS_TOPIC: Topic<AgentStatusListener> = Topic.create(
    "SecureLoopAgentStatusTopic",
    AgentStatusListener::class.java,
)

val NAVIGATE_TOPIC: Topic<NavigateListener> = Topic.create(
    "SecureLoopNavigateTopic",
    NavigateListener::class.java,
)

val PIPELINE_TOPIC: Topic<PipelineListener> = Topic.create(
    "SecureLoopPipelineTopic",
    PipelineListener::class.java,
)
