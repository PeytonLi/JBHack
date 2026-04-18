package dev.secureloop.plugin.services

import com.intellij.util.messages.Topic
import dev.secureloop.plugin.model.NormalizedIncident

interface IncidentListener {
    fun incidentReceived(incident: NormalizedIncident)
}

val INCIDENT_TOPIC: Topic<IncidentListener> = Topic.create(
    "SecureLoopIncidentTopic",
    IncidentListener::class.java,
)
