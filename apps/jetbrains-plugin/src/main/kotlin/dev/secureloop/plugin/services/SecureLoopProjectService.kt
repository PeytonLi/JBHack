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
import com.intellij.openapi.fileEditor.FileDocumentManager
import com.intellij.openapi.fileEditor.FileEditorManager
import com.intellij.openapi.fileEditor.OpenFileDescriptor
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.Disposer
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.ui.JBColor
import dev.secureloop.plugin.model.AgentConnectionState
import dev.secureloop.plugin.model.IncidentPresentation
import dev.secureloop.plugin.model.NormalizedIncident
import dev.secureloop.plugin.model.ProjectCompatibilityState
import dev.secureloop.plugin.model.ResolutionState
import dev.secureloop.plugin.ui.SecureLoopGutterIconRenderer
import dev.secureloop.plugin.ui.SecureLoopToolWindowPanel
import dev.secureloop.plugin.util.FileResolution
import dev.secureloop.plugin.util.ProjectFileResolver
import java.awt.Color
import java.awt.Font
import java.nio.file.Files
import java.nio.file.Path

@Service(Service.Level.PROJECT)
class SecureLoopProjectService(
    private val project: Project,
) : Disposable {
    private val incidents = mutableListOf<IncidentPresentation>()
    private val projectCompatibility = detectProjectCompatibility()
    private var panel: SecureLoopToolWindowPanel? = null
    private var connectionState: AgentConnectionState = AgentConnectionState.Connecting

    init {
        ApplicationManager.getApplication().messageBus.connect(this).subscribe(
            INCIDENT_TOPIC,
            object : IncidentListener {
                override fun incidentReceived(incident: NormalizedIncident) {
                    handleIncident(incident)
                }
            },
        )
        ApplicationManager.getApplication().messageBus.connect(this).subscribe(
            AGENT_STATUS_TOPIC,
            object : AgentStatusListener {
                override fun connectionStateChanged(state: AgentConnectionState) {
                    connectionState = state
                    updateEnvironment()
                }
            },
        )
    }

    fun attachPanel(toolWindowPanel: SecureLoopToolWindowPanel) {
        panel = toolWindowPanel
        val applicationService = service<SecureLoopApplicationService>()
        connectionState = applicationService.currentConnectionState()
        ApplicationManager.getApplication().invokeLater {
            toolWindowPanel.updateEnvironment(connectionState, projectCompatibility)
            toolWindowPanel.replaceIncidents(incidents)
        }
        applicationService.refreshStatus()
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

    fun markIncidentReviewed(presentation: IncidentPresentation) {
        if (presentation.reviewed) {
            return
        }

        service<SecureLoopApplicationService>().markIncidentReviewed(presentation.incident.incidentId)
        upsertIncident(presentation.copy(reviewed = true))
    }

    fun analyzeSelectedIncident(presentation: IncidentPresentation) {
        if (presentation.analysis != null) {
            return
        }

        val resolution = presentation.resolution
        if (resolution !is ResolutionState.Resolved) {
            return
        }

        val sourceContext = readSourceContext(resolution.filePath, resolution.lineNumber)
        if (sourceContext.isBlank()) {
            return
        }

        val policyText = readSecurityPolicy()

        upsertIncident(presentation.copy(
            analysis = null,
        ))
        ApplicationManager.getApplication().invokeLater {
            panel?.setAnalyzing(true)
        }

        service<SecureLoopApplicationService>().analyzeIncident(
            incidentId = presentation.incident.incidentId,
            sourceContext = sourceContext,
            policyText = policyText,
        ) { response ->
            val updated = presentation.copy(analysis = response)
            upsertIncident(updated)
            ApplicationManager.getApplication().invokeLater {
                panel?.setAnalyzing(false)
            }
        }
    }

    fun approveAndApplyFix(presentation: IncidentPresentation) {
        val analysis = presentation.analysis ?: return
        val patch = analysis.patch
        val file = ProjectFileResolver.findByAbsolutePath(project, patch.repoRelativePath) ?: return
        
        ApplicationManager.getApplication().invokeLater {
            com.intellij.openapi.command.WriteCommandAction.runWriteCommandAction(project) {
                val document = FileDocumentManager.getInstance().getDocument(file) ?: return@runWriteCommandAction
                val newText = document.text.replace(patch.oldText, patch.newText)
                document.setText(newText)
            }
            
            service<SecureLoopApplicationService>().openPR(presentation.incident.incidentId) {
                val url = it ?: "Unknown URL"
                com.intellij.openapi.ui.Messages.showMessageDialog(project, "PR created successfully!\n\n\$url", "PR Opened", com.intellij.openapi.ui.Messages.getInformationIcon())
            }
        }
    }

    fun rejectFix(presentation: IncidentPresentation) {
        val reason = com.intellij.openapi.ui.Messages.showInputDialog(
            project,
            "Why is this fix incorrect/rejected?",
            "Reject Fix",
            com.intellij.openapi.ui.Messages.getQuestionIcon()
        ) ?: return
        
        service<SecureLoopApplicationService>().rejectFix(presentation.incident.incidentId, reason)
    }

    fun reportVulnerability(file: com.intellij.openapi.vfs.VirtualFile, analysis: dev.secureloop.plugin.model.AnalysisResponse) {
        ApplicationManager.getApplication().invokeLater {
            val editor = com.intellij.openapi.fileEditor.FileEditorManager.getInstance(project).selectedTextEditor ?: return@invokeLater
            if (editor.virtualFile == file) {
               val text = editor.document.text
               val startOffset = text.indexOf(analysis.patch.oldText).takeIf { it >= 0 } ?: return@invokeLater
               val endOffset = startOffset + analysis.patch.oldText.length
               editor.markupModel.addRangeHighlighter(
                   startOffset, endOffset, HighlighterLayer.WARNING, 
                   TextAttributes(null, JBColor(Color(255, 0, 0, 40), Color(255, 0, 0, 40)), JBColor.RED, EffectType.WAVE_UNDERSCORE, Font.PLAIN), 
                   com.intellij.openapi.editor.markup.HighlighterTargetArea.EXACT_RANGE
               )
            }
        }
    }


    private fun readSourceContext(filePath: String, lineNumber: Int): String {
        val file = ProjectFileResolver.findByAbsolutePath(project, filePath) ?: return ""
        val document = ApplicationManager.getApplication().runReadAction<com.intellij.openapi.editor.Document?> {
            FileDocumentManager.getInstance().getDocument(file)
        } ?: return ""

        val totalLines = document.lineCount
        val targetLine = (lineNumber - 1).coerceIn(0, totalLines - 1)
        val startLine = (targetLine - 10).coerceAtLeast(0)
        val endLine = (targetLine + 10).coerceAtMost(totalLines - 1)

        return ApplicationManager.getApplication().runReadAction<String> {
            val startOffset = document.getLineStartOffset(startLine)
            val endOffset = document.getLineEndOffset(endLine)
            document.getText(com.intellij.openapi.util.TextRange(startOffset, endOffset))
        }
    }

    private fun readSecurityPolicy(): String? {
        val basePath = project.basePath ?: return null
        val policyPath = Path.of(basePath).resolve("security-policy.md")
        if (!Files.exists(policyPath)) {
            return null
        }
        return try {
            Files.readString(policyPath)
        } catch (_: Exception) {
            null
        }
    }

    fun runDemoIncident() {
        if (projectCompatibility is ProjectCompatibilityState.DemoReady) {
            service<SecureLoopApplicationService>().triggerDemoIncident()
        } else {
            openSetupGuide()
        }
    }

    fun retryConnection() {
        service<SecureLoopApplicationService>().refreshStatus()
    }

    fun openSetupGuide() {
        val basePath = project.basePath ?: return
        val guidePath = Path.of(basePath).resolve("README.md").normalize()
        val guideFile = LocalFileSystem.getInstance().refreshAndFindFileByPath(guidePath.toString().replace("\\", "/"))
        if (guideFile != null) {
            ApplicationManager.getApplication().invokeLater {
                FileEditorManager.getInstance(project).openFile(guideFile, true)
            }
        }
    }

    override fun dispose() {
        panel = null
    }

    private fun handleIncident(incident: NormalizedIncident) {
        val isNewIncident = incidents.none { it.incident.incidentId == incident.incidentId }
        val placeholder = IncidentPresentation(incident = incident)
        upsertIncident(placeholder)

        val resolution = ProjectFileResolver.resolve(project, incident)
        val resolvedPresentation = placeholder.copy(resolution = resolution.toPresentationState())
        upsertIncident(resolvedPresentation)

        if (!isNewIncident) {
            return
        }

        notifyIncident(incident)

        if (resolution is FileResolution.Resolved && isProjectWindowActive()) {
            openAndHighlight(resolution.file, resolution.lineNumber, incident)
        }
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

    private fun updateEnvironment() {
        ApplicationManager.getApplication().invokeLater {
            panel?.updateEnvironment(connectionState, projectCompatibility)
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

    private fun detectProjectCompatibility(): ProjectCompatibilityState {
        val basePath = project.basePath ?: return ProjectCompatibilityState.Unsupported(
            "Open the SecureLoop demo repo before running demo mode.",
        )

        val root = Path.of(basePath)
        val targetPath = root.resolve("apps/target/src/main.py")
        val policyPath = root.resolve("security-policy.md")
        if (Files.exists(targetPath) && Files.exists(policyPath)) {
            return ProjectCompatibilityState.DemoReady(
                targetPath = "apps/target/src/main.py",
                policyPath = "security-policy.md",
            )
        }

        return ProjectCompatibilityState.Unsupported(
            "v1 supports the SecureLoop demo repo only. Open a project containing apps/target/src/main.py and security-policy.md.",
        )
    }
}
