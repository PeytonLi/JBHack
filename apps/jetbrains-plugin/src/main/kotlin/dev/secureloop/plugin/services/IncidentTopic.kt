package dev.secureloop.plugin.services

import com.intellij.util.messages.Topic
import dev.secureloop.plugin.model.AgentConnectionState
import dev.secureloop.plugin.model.NormalizedIncident

interface IncidentListener {
    fun incidentReceived(incident: NormalizedIncident)
}

interface AgentStatusListener {
    fun connectionStateChanged(state: AgentConnectionState)
}

val INCIDENT_TOPIC: Topic<IncidentListener> = Topic.create(
    "SecureLoopIncidentTopic",
    IncidentListener::class.java,
)

val AGENT_STATUS_TOPIC: Topic<AgentStatusListener> = Topic.create(
    "SecureLoopAgentStatusTopic",
    AgentStatusListener::class.java,
)
