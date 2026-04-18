package dev.secureloop.plugin.ui

import com.intellij.icons.AllIcons
import com.intellij.openapi.editor.markup.GutterIconRenderer
import dev.secureloop.plugin.model.NormalizedIncident

class SecureLoopGutterIconRenderer(
    private val incident: NormalizedIncident,
) : GutterIconRenderer() {
    override fun equals(other: Any?): Boolean {
        return other is SecureLoopGutterIconRenderer && other.incident.incidentId == incident.incidentId
    }

    override fun hashCode(): Int = incident.incidentId.hashCode()

    override fun getIcon() = AllIcons.General.Warning

    override fun getTooltipText(): String {
        return "SecureLoop incident: ${incident.exceptionType}"
    }
}
