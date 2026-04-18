package dev.secureloop.plugin.services

import com.intellij.ide.BrowserUtil
import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.components.service
import com.intellij.openapi.editor.markup.EffectType
import com.intellij.openapi.editor.markup.HighlighterLayer
import com.intellij.openapi.editor.markup.TextAttributes
import com.intellij.openapi.fileEditor.FileEditorManager
import com.intellij.openapi.fileEditor.OpenFileDescriptor
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.Disposer
import com.intellij.ui.JBColor
import dev.secureloop.plugin.model.IncidentPresentation
import dev.secureloop.plugin.model.NormalizedIncident
import dev.secureloop.plugin.model.ResolutionState
import dev.secureloop.plugin.ui.SecureLoopGutterIconRenderer
import dev.secureloop.plugin.ui.SecureLoopToolWindowPanel
import dev.secureloop.plugin.util.FileResolution
import dev.secureloop.plugin.util.ProjectFileResolver
import java.awt.Color
import java.awt.Font

@Service(Service.Level.PROJECT)
class SecureLoopProjectService(
    private val project: Project,
) : Disposable {
    private val incidents = mutableListOf<IncidentPresentation>()
    private var panel: SecureLoopToolWindowPanel? = null

    init {
        ApplicationManager.getApplication().messageBus.connect(this).subscribe(
            INCIDENT_TOPIC,
            object : IncidentListener {
                override fun incidentReceived(incident: NormalizedIncident) {
                    handleIncident(incident)
                }
            },
        )
    }

    fun attachPanel(toolWindowPanel: SecureLoopToolWindowPanel) {
        panel = toolWindowPanel
        ApplicationManager.getApplication().invokeLater {
            toolWindowPanel.replaceIncidents(incidents)
        }
    }

    fun openSelectionInEditor(presentation: IncidentPresentation) {
        val resolution = presentation.resolution
        if (resolution is ResolutionState.Resolved) {
            val resolved = ProjectFileResolver.findByAbsolutePath(project, resolution.filePath)
            if (resolved != null) {
                openAndHighlight(resolved, resolution.lineNumber, presentation.incident)
            }
        }
    }

    fun openIncidentInBrowser(presentation: IncidentPresentation) {
        BrowserUtil.browse(presentation.incident.eventWebUrl)
    }

    override fun dispose() {
        panel = null
    }

    private fun handleIncident(incident: NormalizedIncident) {
        val placeholder = IncidentPresentation(incident = incident)
        upsertIncident(placeholder)
        notifyIncident(incident)

        val resolution = ProjectFileResolver.resolve(project, incident)
        val resolvedPresentation = placeholder.copy(resolution = resolution.toPresentationState())
        upsertIncident(resolvedPresentation)

        if (resolution is FileResolution.Resolved && isProjectWindowActive()) {
            openAndHighlight(resolution.file, resolution.lineNumber, incident)
        }

        service<SecureLoopApplicationService>().acknowledgeIncident(incident.incidentId)
    }

    private fun upsertIncident(presentation: IncidentPresentation) {
        val index = incidents.indexOfFirst { it.incident.incidentId == presentation.incident.incidentId }
        if (index == -1) {
            incidents.add(0, presentation)
        } else {
            incidents[index] = presentation
        }

        ApplicationManager.getApplication().invokeLater {
            panel?.upsertIncident(presentation)
        }
    }

    private fun notifyIncident(incident: NormalizedIncident) {
        val content = buildString {
            append(incident.exceptionType)
            incident.repoRelativePath?.let { append(" in $it") }
            incident.lineNumber?.let { append(":$it") }
        }
        NotificationGroupManager.getInstance()
            .getNotificationGroup("SecureLoop Alerts")
            .createNotification("SecureLoop incident received", content, NotificationType.WARNING)
            .notify(project)
    }

    private fun isProjectWindowActive(): Boolean {
        val frame = com.intellij.openapi.wm.WindowManager.getInstance().getFrame(project)
        return frame?.isActive == true
    }

    private fun openAndHighlight(
        file: com.intellij.openapi.vfs.VirtualFile,
        lineNumber: Int,
        incident: NormalizedIncident,
    ) {
        ApplicationManager.getApplication().invokeLater {
            val descriptor = OpenFileDescriptor(project, file, (lineNumber - 1).coerceAtLeast(0), 0)
            val editor = FileEditorManager.getInstance(project).openTextEditor(descriptor, true) ?: return@invokeLater
            val safeLine = (lineNumber - 1).coerceIn(0, editor.document.lineCount - 1)

            val attributes = TextAttributes(
                JBColor(Color(255, 244, 214), Color(77, 63, 27)),
                null,
                JBColor(Color(232, 144, 0), Color(255, 199, 107)),
                EffectType.ROUNDED_BOX,
                Font.PLAIN,
            )
            val highlighter = editor.markupModel.addLineHighlighter(
                safeLine,
                HighlighterLayer.ERROR + 1,
                attributes,
            )
            highlighter.gutterIconRenderer = SecureLoopGutterIconRenderer(incident)
            Disposer.register(this, Disposable {
                editor.markupModel.removeHighlighter(highlighter)
            })
        }
    }

    private fun FileResolution.toPresentationState(): ResolutionState {
        return when (this) {
            is FileResolution.Resolved -> ResolutionState.Resolved(file.path, lineNumber)
            is FileResolution.Ambiguous -> ResolutionState.Ambiguous(candidates)
            is FileResolution.Unresolved -> ResolutionState.Unresolved(reason)
        }
    }
}
