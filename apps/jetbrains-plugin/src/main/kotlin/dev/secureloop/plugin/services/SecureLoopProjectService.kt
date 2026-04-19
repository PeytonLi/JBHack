package dev.secureloop.plugin.services

import com.intellij.ide.BrowserUtil
import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.command.WriteCommandAction
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
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.ui.JBColor
import dev.secureloop.plugin.model.AgentConnectionState
import dev.secureloop.plugin.model.AnalysisState
import dev.secureloop.plugin.model.AnalyzeIncidentRequest
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
import kotlin.text.Regex

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

    fun scanCurrentFile() {
        if (connectionState !is AgentConnectionState.Connected) {
            presentLocalScanError("SecureLoop is not connected to the local agent.")
            return
        }

        if (projectCompatibility !is ProjectCompatibilityState.DemoReady) {
            presentLocalScanError("Open the SecureLoop demo repo before scanning the current file.")
            return
        }

        val editor = FileEditorManager.getInstance(project).selectedTextEditor ?: run {
            presentLocalScanError("Open a file in the SecureLoop demo repo before scanning.")
            return
        }

        val file = FileDocumentManager.getInstance().getFile(editor.document) ?: run {
            presentLocalScanError("SecureLoop could not resolve the active editor file.")
            return
        }

        val repoRelativePath = repoRelativePathFor(file.path) ?: run {
            presentLocalScanError(
                "SecureLoop could not determine a repo-relative path for the active file.",
                absoluteFilePath = file.path,
            )
            return
        }

        val fileText = currentFileText(file) ?: run {
            presentLocalScanError(
                "SecureLoop could not read the active file.",
                repoRelativePath = repoRelativePath,
                absoluteFilePath = file.path,
            )
            return
        }

        val caretLine = (editor.caretModel.primaryCaret.logicalPosition.line + 1).coerceAtLeast(1)
        val scanTarget = chooseScanTarget(fileText, caretLine)
        val lineNumber = scanTarget.lineNumber

        val sourceContext = collectSourceContext(fileText, lineNumber) ?: run {
            presentLocalScanError(
                "SecureLoop could not collect source context from the active file.",
                repoRelativePath = repoRelativePath,
                absoluteFilePath = file.path,
                lineNumber = lineNumber,
            )
            return
        }

        val policyText = readPolicyText() ?: run {
            presentLocalScanError(
                "SecureLoop could not read security-policy.md from the project root.",
                repoRelativePath = repoRelativePath,
                absoluteFilePath = file.path,
                lineNumber = lineNumber,
            )
            return
        }

        val incidentId = localScanIncidentId(repoRelativePath)
        val incident = createLocalScanIncident(
            incidentId = incidentId,
            file = file,
            repoRelativePath = repoRelativePath,
            lineNumber = lineNumber,
            sourceContext = sourceContext,
            scanReason = scanTarget.reason,
        )

        upsertIncident(
            IncidentPresentation(
                incident = incident,
                resolution = ResolutionState.Resolved(file.path, lineNumber),
                analysisState = AnalysisState.Loading,
            ),
        )
        focusIncidentAsync(incidentId)

        service<SecureLoopApplicationService>().analyzeIncident(
            payload = AnalyzeIncidentRequest(
                incidentId = incidentId,
                repoRelativePath = repoRelativePath,
                lineNumber = lineNumber,
                exceptionType = incident.exceptionType,
                exceptionMessage = incident.exceptionMessage,
                title = incident.title,
                sourceContext = sourceContext,
                policyText = policyText,
            ),
            onSuccess = { analysis ->
                updateIncident(incidentId) {
                    it.copy(
                        analysis = analysis,
                        analysisState = AnalysisState.Ready,
                        analysisError = null,
                    )
                }
            },
            onError = { message ->
                failAnalysis(incidentId, message)
            },
        )
    }

    fun analyzeSelection(presentation: IncidentPresentation) {
        val resolved = presentation.resolution as? ResolutionState.Resolved ?: return
        if (connectionState !is AgentConnectionState.Connected) {
            failAnalysis(presentation.incident.incidentId, "SecureLoop is not connected to the local agent.")
            return
        }

        val repoRelativePath = repoRelativePathFor(presentation, resolved)
        if (repoRelativePath == null) {
            failAnalysis(presentation.incident.incidentId, "SecureLoop could not determine the repo-relative path.")
            return
        }

        val resolvedFile = resolvedVirtualFile(resolved.filePath)
        if (resolvedFile == null) {
            failAnalysis(presentation.incident.incidentId, "SecureLoop could not open the resolved file.")
            return
        }

        val sourceContext = collectSourceContext(resolvedFile, resolved.lineNumber)
        if (sourceContext == null) {
            failAnalysis(presentation.incident.incidentId, "SecureLoop could not collect source context.")
            return
        }

        val policyText = readPolicyText()
        if (policyText == null) {
            failAnalysis(presentation.incident.incidentId, "SecureLoop could not read security-policy.md from the project root.")
            return
        }

        updateIncident(presentation.incident.incidentId) {
            it.copy(
                analysisState = AnalysisState.Loading,
                analysisError = null,
            )
        }

        service<SecureLoopApplicationService>().analyzeIncident(
            payload = AnalyzeIncidentRequest(
                incidentId = presentation.incident.incidentId,
                repoRelativePath = repoRelativePath,
                lineNumber = resolved.lineNumber,
                exceptionType = presentation.incident.exceptionType,
                exceptionMessage = presentation.incident.exceptionMessage,
                title = presentation.incident.title,
                sourceContext = sourceContext,
                policyText = policyText,
            ),
            onSuccess = { analysis ->
                updateIncident(presentation.incident.incidentId) {
                    it.copy(
                        analysis = analysis,
                        analysisState = AnalysisState.Ready,
                        analysisError = null,
                    )
                }
            },
            onError = { message ->
                failAnalysis(presentation.incident.incidentId, message)
            },
        )
    }

    fun rejectAnalysis(presentation: IncidentPresentation) {
        updateIncident(presentation.incident.incidentId) {
            it.copy(
                analysis = null,
                analysisState = AnalysisState.Idle,
                analysisError = null,
            )
        }
    }

    fun approveFix(presentation: IncidentPresentation) {
        val resolved = presentation.resolution as? ResolutionState.Resolved ?: run {
            failAnalysis(presentation.incident.incidentId, "SecureLoop can only apply fixes for resolved incidents.")
            return
        }
        val analysis = presentation.analysis ?: run {
            failAnalysis(presentation.incident.incidentId, "Run Analyze with Codex before approving a fix.")
            return
        }

        val resolvedFile = resolvedVirtualFile(resolved.filePath) ?: run {
            failAnalysis(presentation.incident.incidentId, "SecureLoop could not reopen the resolved file.")
            return
        }
        val document = FileDocumentManager.getInstance().getDocument(resolvedFile) ?: run {
            failAnalysis(presentation.incident.incidentId, "SecureLoop could not load a writable document for the resolved file.")
            return
        }

        if (!patchMatchesTarget(presentation, resolved, analysis.patch.repoRelativePath)) {
            failAnalysis(presentation.incident.incidentId, "Patch target does not match the selected incident.")
            return
        }

        val currentText = document.text
        val occurrenceCount = Regex.fromLiteral(analysis.patch.oldText).findAll(currentText).count()
        if (occurrenceCount != 1) {
            failAnalysis(
                presentation.incident.incidentId,
                "Patch precondition failed: expected oldText exactly once, found $occurrenceCount matches.",
            )
            return
        }

        val updatedText = currentText.replaceFirst(analysis.patch.oldText, analysis.patch.newText)
        if (updatedText == currentText) {
            failAnalysis(presentation.incident.incidentId, "Patch precondition failed: replacement produced no file changes.")
            return
        }

        updateIncident(presentation.incident.incidentId) {
            it.copy(
                analysisState = AnalysisState.Applying,
                analysisError = null,
            )
        }

        try {
            WriteCommandAction.runWriteCommandAction(project) {
                document.setText(updatedText)
                FileDocumentManager.getInstance().saveDocument(document)
            }
            updateIncident(presentation.incident.incidentId) {
                it.copy(
                    analysisState = AnalysisState.Applied,
                    analysisError = null,
                )
            }
        } catch (exception: Throwable) {
            failAnalysis(
                presentation.incident.incidentId,
                "SecureLoop could not apply the approved patch: ${exception.message ?: "unknown error"}.",
            )
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

    private fun updateIncident(
        incidentId: String,
        transform: (IncidentPresentation) -> IncidentPresentation,
    ) {
        val existing = incidents.firstOrNull { it.incident.incidentId == incidentId } ?: return
        upsertIncident(transform(existing))
    }

    private fun failAnalysis(incidentId: String, message: String) {
        updateIncident(incidentId) {
            it.copy(
                analysisState = AnalysisState.Failed,
                analysisError = message,
            )
        }
    }

    private fun presentLocalScanError(
        message: String,
        repoRelativePath: String? = null,
        absoluteFilePath: String? = null,
        lineNumber: Int? = null,
    ) {
        val incidentId = localScanIncidentId(repoRelativePath)
        val incident = NormalizedIncident(
            incidentId = incidentId,
            sentryEventId = incidentId,
            issueId = incidentId,
            projectSlug = project.name,
            environment = "local-scan",
            title = "Pre-Commit Scan",
            exceptionType = "LocalScan",
            exceptionMessage = message,
            repoRelativePath = repoRelativePath,
            originalFramePath = absoluteFilePath,
            lineNumber = lineNumber,
            functionName = null,
            codeContext = null,
            eventWebUrl = "about:blank",
            receivedAt = java.time.Instant.now().toString(),
        )
        val resolution = if (absoluteFilePath != null && lineNumber != null) {
            ResolutionState.Resolved(absoluteFilePath, lineNumber)
        } else {
            ResolutionState.Unresolved(message)
        }

        upsertIncident(
            IncidentPresentation(
                incident = incident,
                resolution = resolution,
                analysisState = AnalysisState.Failed,
                analysisError = message,
            ),
        )
        focusIncidentAsync(incidentId)
    }

    private fun updateEnvironment() {
        ApplicationManager.getApplication().invokeLater {
            panel?.updateEnvironment(connectionState, projectCompatibility)
        }
    }

    private fun focusIncidentAsync(incidentId: String) {
        ApplicationManager.getApplication().invokeLater {
            panel?.selectIncidentById(incidentId)
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

    private fun resolvedVirtualFile(filePath: String): VirtualFile? {
        return ProjectFileResolver.findByAbsolutePath(project, filePath)
    }

    private fun repoRelativePathFor(
        presentation: IncidentPresentation,
        resolved: ResolutionState.Resolved,
    ): String? {
        presentation.incident.repoRelativePath?.takeIf { it.isNotBlank() }?.let { return normalizePath(it) }
        val basePath = project.basePath ?: return null
        val root = Path.of(basePath).normalize()
        val filePath = Path.of(resolved.filePath).normalize()
        return try {
            normalizePath(root.relativize(filePath).toString())
        } catch (_: IllegalArgumentException) {
            null
        }
    }

    private fun repoRelativePathFor(filePath: String): String? {
        val basePath = project.basePath ?: return null
        val root = Path.of(basePath).normalize()
        val absolutePath = Path.of(filePath).normalize()
        return try {
            normalizePath(root.relativize(absolutePath).toString())
        } catch (_: IllegalArgumentException) {
            null
        }
    }

    private fun collectSourceContext(file: VirtualFile, lineNumber: Int): String? {
        val text = currentFileText(file) ?: return null
        return collectSourceContext(text, lineNumber)
    }

    private fun collectSourceContext(text: String, lineNumber: Int): String? {
        val lines = text.lines()
        if (lines.isEmpty()) {
            return text
        }

        val zeroBasedLine = (lineNumber - 1).coerceIn(0, lines.lastIndex)
        val start = (zeroBasedLine - 8).coerceAtLeast(0)
        val end = (zeroBasedLine + 8).coerceAtMost(lines.lastIndex)
        return lines.subList(start, end + 1).joinToString("\n")
    }

    private fun currentFileText(file: VirtualFile): String? {
        val document = FileDocumentManager.getInstance().getDocument(file)
        if (document != null) {
            return document.text
        }
        return try {
            String(file.contentsToByteArray(), file.charset)
        } catch (_: Exception) {
            null
        }
    }

    private data class LocalScanTarget(
        val lineNumber: Int,
        val reason: String,
    )

    private data class LocalScanPattern(
        val needle: String,
        val reason: String,
    )

    private fun chooseScanTarget(fileText: String, caretLine: Int): LocalScanTarget {
        val detectedTarget = detectHighConfidenceFinding(fileText)
        if (detectedTarget != null) {
            return detectedTarget
        }

        return LocalScanTarget(
            lineNumber = caretLine,
            reason = "No high-confidence pattern was detected automatically; scanning the current caret line.",
        )
    }

    private fun detectHighConfidenceFinding(fileText: String): LocalScanTarget? {
        val patterns = listOf(
            LocalScanPattern(
                needle = "WAREHOUSES[warehouse_id]",
                reason = "Detected unchecked warehouse lookup that can raise an unhandled KeyError.",
            ),
            LocalScanPattern(
                needle = "shell=True",
                reason = "Detected shell command execution that should be reviewed for injection risk.",
            ),
            LocalScanPattern(
                needle = "eval(",
                reason = "Detected dynamic code execution that should be reviewed before commit.",
            ),
            LocalScanPattern(
                needle = "exec(",
                reason = "Detected dynamic code execution that should be reviewed before commit.",
            ),
        )

        fileText.lines().forEachIndexed { index, line ->
            val matchedPattern = patterns.firstOrNull { pattern -> line.contains(pattern.needle) }
            if (matchedPattern != null) {
                return LocalScanTarget(
                    lineNumber = index + 1,
                    reason = matchedPattern.reason,
                )
            }
        }

        return null
    }

    private fun readPolicyText(): String? {
        val basePath = project.basePath ?: return null
        val policyPath = Path.of(basePath).resolve("security-policy.md").normalize()
        return try {
            Files.readString(policyPath)
        } catch (_: Exception) {
            null
        }
    }

    private fun patchMatchesTarget(
        presentation: IncidentPresentation,
        resolved: ResolutionState.Resolved,
        patchPath: String,
    ): Boolean {
        val normalizedPatchPath = normalizePath(patchPath)
        val normalizedIncidentPath = presentation.incident.repoRelativePath?.let(::normalizePath)
        val normalizedResolvedPath = normalizePath(resolved.filePath)
        return normalizedPatchPath == normalizedIncidentPath ||
            normalizedResolvedPath.endsWith("/$normalizedPatchPath") ||
            normalizedResolvedPath == normalizedPatchPath
    }

    private fun localScanIncidentId(repoRelativePath: String?): String {
        val normalized = repoRelativePath?.takeIf { it.isNotBlank() }?.let(::normalizePath)
        return if (normalized.isNullOrBlank()) {
            "local-scan:error"
        } else {
            "local-scan:$normalized"
        }
    }

    private fun createLocalScanIncident(
        incidentId: String,
        file: VirtualFile,
        repoRelativePath: String,
        lineNumber: Int,
        sourceContext: String,
        scanReason: String,
    ): NormalizedIncident {
        return NormalizedIncident(
            incidentId = incidentId,
            sentryEventId = incidentId,
            issueId = incidentId,
            projectSlug = project.name,
            environment = "local-scan",
            title = "Pre-Commit Scan",
            exceptionType = "LocalScan",
            exceptionMessage = scanReason,
            repoRelativePath = repoRelativePath,
            originalFramePath = file.path,
            lineNumber = lineNumber,
            functionName = null,
            codeContext = sourceContext,
            eventWebUrl = file.url,
            receivedAt = java.time.Instant.now().toString(),
        )
    }

    private fun normalizePath(path: String): String {
        return path.replace("\\", "/").trim().removePrefix("file:///")
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
