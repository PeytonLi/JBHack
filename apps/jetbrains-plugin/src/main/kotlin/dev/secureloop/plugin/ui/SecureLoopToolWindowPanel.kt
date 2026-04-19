package dev.secureloop.plugin.ui

import com.intellij.ui.ColoredListCellRenderer
import com.intellij.ui.SimpleTextAttributes
import com.intellij.ui.components.JBList
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBScrollPane
import com.intellij.ui.components.JBTextArea
import dev.secureloop.plugin.model.AgentConnectionState
import dev.secureloop.plugin.model.AnalysisState
import dev.secureloop.plugin.model.AnalyzeIncidentResponse
import dev.secureloop.plugin.model.IncidentPresentation
import dev.secureloop.plugin.model.ProjectCompatibilityState
import dev.secureloop.plugin.model.ResolutionState
import dev.secureloop.plugin.services.SecureLoopProjectService
import java.awt.BorderLayout
import javax.swing.DefaultListModel
import javax.swing.JButton
import javax.swing.JList
import javax.swing.JPanel
import javax.swing.JSplitPane
import javax.swing.ListSelectionModel

class SecureLoopToolWindowPanel(
    private val projectService: SecureLoopProjectService,
) : JPanel(BorderLayout()) {
    private val listModel = DefaultListModel<IncidentPresentation>()
    private val incidentList = JBList(listModel)
    private val statusLabel = JBLabel()
    private val statusArea = JBTextArea()
    private val detailArea = JBTextArea()
    private val runDemoButton = JButton("Run Demo")
    private val scanCurrentFileButton = JButton("Scan Current File")
    private val retryConnectionButton = JButton("Retry Connection")
    private val setupGuideButton = JButton("Open Setup Guide")
    private val openFileButton = JButton("Open File")
    private val analyzeButton = JButton("Analyze with Codex")
    private val approveFixButton = JButton("Approve Fix")
    private val showDiffButton = JButton("Show Diff")
    private val openPrButton = JButton("Open Pull Request")
    private val rejectButton = JButton("Reject")
    private val markReviewedButton = JButton("Mark Reviewed")
    private val openSentryButton = JButton("Open Sentry")
    private val badgeLabel = JBLabel()
    private var connectionState: AgentConnectionState = AgentConnectionState.Connecting
    private var projectCompatibility: ProjectCompatibilityState = ProjectCompatibilityState.Unsupported(
        "Open the SecureLoop demo repo to get started.",
    )

    init {
        incidentList.selectionMode = ListSelectionModel.SINGLE_SELECTION
        incidentList.cellRenderer = IncidentCellRenderer()
        incidentList.addListSelectionListener {
            renderSelection()
        }

        statusArea.isEditable = false
        statusArea.lineWrap = true
        statusArea.wrapStyleWord = true
        statusArea.isOpaque = false

        detailArea.isEditable = false
        detailArea.lineWrap = true
        detailArea.wrapStyleWord = true

        runDemoButton.addActionListener {
            projectService.runDemoIncident()
        }
        scanCurrentFileButton.addActionListener {
            projectService.scanCurrentFile()
        }
        retryConnectionButton.addActionListener {
            projectService.retryConnection()
        }
        setupGuideButton.addActionListener {
            projectService.openSetupGuide()
        }
        openFileButton.addActionListener {
            selectedIncident()?.let(projectService::openSelectionInEditor)
        }
        analyzeButton.addActionListener {
            selectedIncident()?.let(projectService::analyzeSelection)
        }
        approveFixButton.addActionListener {
            selectedIncident()?.let(projectService::approveFix)
        }
        showDiffButton.addActionListener {
            selectedIncident()?.let(projectService::showDiff)
        }
        openPrButton.addActionListener {
            selectedIncident()?.let(projectService::openPullRequest)
        }
        rejectButton.addActionListener {
            selectedIncident()?.let(projectService::rejectAnalysis)
        }
        markReviewedButton.addActionListener {
            selectedIncident()?.let(projectService::markIncidentReviewed)
            renderSelection()
        }
        openSentryButton.addActionListener {
            selectedIncident()?.let(projectService::openIncidentInBrowser)
        }

        val statusPanel = JPanel(BorderLayout()).apply {
            add(statusLabel, BorderLayout.NORTH)
            add(statusArea, BorderLayout.CENTER)
        }

        val buttonBar = JPanel().apply {
            add(runDemoButton)
            add(scanCurrentFileButton)
            add(retryConnectionButton)
            add(setupGuideButton)
            add(openFileButton)
            add(analyzeButton)
            add(approveFixButton)
            add(showDiffButton)
            add(openPrButton)
            add(rejectButton)
            add(markReviewedButton)
            add(openSentryButton)
        }

        val topPanel = JPanel(BorderLayout()).apply {
            add(statusPanel, BorderLayout.CENTER)
            add(buttonBar, BorderLayout.SOUTH)
        }

        val detailPanel = JPanel(BorderLayout()).apply {
            add(badgeLabel, BorderLayout.NORTH)
            add(JBScrollPane(detailArea), BorderLayout.CENTER)
        }

        val splitPane = JSplitPane(
            JSplitPane.VERTICAL_SPLIT,
            JBScrollPane(incidentList),
            detailPanel,
        ).apply {
            resizeWeight = 0.55
        }

        add(topPanel, BorderLayout.NORTH)
        add(splitPane, BorderLayout.CENTER)
        renderSelection()
    }

    fun updateEnvironment(
        connectionState: AgentConnectionState,
        projectCompatibility: ProjectCompatibilityState,
    ) {
        this.connectionState = connectionState
        this.projectCompatibility = projectCompatibility
        renderSelection()
    }

    fun replaceIncidents(incidents: List<IncidentPresentation>) {
        listModel.clear()
        incidents.forEach(listModel::addElement)
        if (!listModel.isEmpty) {
            incidentList.selectedIndex = 0
        } else {
            renderSelection()
        }
    }

    fun selectIncidentById(incidentId: String) {
        val index = (0 until listModel.size()).firstOrNull {
            listModel.getElementAt(it).incident.incidentId == incidentId
        } ?: return

        incidentList.selectedIndex = index
        incidentList.ensureIndexIsVisible(index)
        renderSelection()
    }

    fun upsertIncident(incident: IncidentPresentation) {
        val index = (0 until listModel.size()).firstOrNull {
            listModel.getElementAt(it).incident.incidentId == incident.incident.incidentId
        }

        if (index == null) {
            listModel.add(0, incident)
            if (incidentList.selectedIndex == -1) {
                incidentList.selectedIndex = 0
            }
        } else {
            listModel.set(index, incident)
            if (incidentList.selectedIndex == index) {
                renderSelection()
            }
        }
    }

    private fun renderSelection() {
        renderEnvironment()
        val presentation = selectedIncident()
        if (presentation == null) {
            detailArea.text = onboardingMessage()
            badgeLabel.text = ""
            openFileButton.isEnabled = false
            analyzeButton.isEnabled = false
            approveFixButton.isEnabled = false
            showDiffButton.isEnabled = false
            openPrButton.isEnabled = false
            rejectButton.isEnabled = false
            markReviewedButton.isEnabled = false
            openSentryButton.isEnabled = false
            return
        }

        badgeLabel.text = renderBadgeHtml(presentation.analysis)

        detailArea.text = buildString {
            appendLine(presentation.incident.title)
            appendLine()
            appendLine("Exception: ${presentation.incident.exceptionType}")
            appendLine("Message: ${presentation.incident.exceptionMessage}")
            appendLine("Project: ${presentation.incident.projectSlug ?: "Unknown"}")
            appendLine("Environment: ${presentation.incident.environment ?: "Unknown"}")
            appendLine("Repo path: ${presentation.incident.repoRelativePath ?: "Unavailable"}")
            appendLine("Original frame: ${presentation.incident.originalFramePath ?: "Unavailable"}")
            appendLine("Line: ${presentation.incident.lineNumber ?: "Unavailable"}")
            appendLine("Function: ${presentation.incident.functionName ?: "Unavailable"}")
            appendLine("Resolution: ${resolutionText(presentation.resolution)}")
            appendLine("Review state: ${if (presentation.reviewed) "Reviewed" else "Open"}")
            appendLine("Analysis state: ${analysisStateText(presentation.analysisState)}")
            presentation.analysisError?.takeIf { it.isNotBlank() }?.let {
                appendLine()
                appendLine("Analysis error:")
                appendLine(it)
            }
            presentation.incident.codeContext?.takeIf { it.isNotBlank() }?.let {
                appendLine()
                appendLine("Code context:")
                appendLine(it)
            }
            presentation.analysis?.let { analysis ->
                appendLine()
                append(analysisText(analysis))
            }
        }

        val resolved = presentation.resolution is ResolutionState.Resolved
        val connected = connectionState is AgentConnectionState.Connected
        val analyzing = presentation.analysisState == AnalysisState.Loading
        val applying = presentation.analysisState == AnalysisState.Applying
        openSentryButton.isEnabled = presentation.incident.eventWebUrl.startsWith("http")
        openFileButton.isEnabled = resolved
        analyzeButton.isEnabled = resolved && connected && !analyzing && !applying
        approveFixButton.isEnabled = resolved &&
            presentation.analysis != null &&
            presentation.analysisState == AnalysisState.Ready
        showDiffButton.isEnabled = presentation.analysis != null &&
            presentation.analysis.diff.isNotBlank()
        openPrButton.isEnabled = resolved &&
            presentation.analysis != null &&
            presentation.analysisState is AnalysisState.Applied
        rejectButton.isEnabled = presentation.analysis != null && presentation.analysisState != AnalysisState.Applying
        markReviewedButton.isEnabled = !presentation.reviewed
    }

    private fun renderBadgeHtml(analysis: AnalyzeIncidentResponse?): String {
        if (analysis == null) {
            return ""
        }
        val severityColor = when (analysis.severity.trim().lowercase()) {
            "critical" -> "#b00020"
            "high" -> "#d84315"
            "medium" -> "#e8900c"
            "low" -> "#2e7d32"
            else -> "#546e7a"
        }
        val severityBadge = "<span style='background:$severityColor;color:#ffffff;" +
            "padding:2px 8px;border-radius:8px;font-weight:600;'>" +
            escapeHtml(analysis.severity.uppercase()) + "</span>"
        val cwePill = "<span style='background:#263238;color:#ffffff;" +
            "padding:2px 8px;border-radius:8px;margin-left:6px;'>" +
            escapeHtml(analysis.cwe) + "</span>"
        val category = "<span style='margin-left:8px;color:#455a64;'>" +
            escapeHtml(analysis.category) + "</span>"
        return "<html><body style='margin:4px;'>" + severityBadge + cwePill + category +
            "</body></html>"
    }

    private fun escapeHtml(value: String): String {
        return value
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    }

    private fun selectedIncident(): IncidentPresentation? = incidentList.selectedValue

    private fun renderEnvironment() {
        statusLabel.text = statusTitle()
        statusArea.text = statusMessage()

        val compatibility = projectCompatibility
        val state = connectionState
        val demoReady = compatibility is ProjectCompatibilityState.DemoReady &&
            state is AgentConnectionState.Connected &&
            state.demoModeAvailable
        runDemoButton.isEnabled = demoReady
        scanCurrentFileButton.isEnabled = compatibility is ProjectCompatibilityState.DemoReady &&
            state is AgentConnectionState.Connected
        retryConnectionButton.isEnabled = true
        setupGuideButton.isEnabled = true
    }

    private fun onboardingMessage(): String {
        val compatibility = projectCompatibility
        return when (compatibility) {
            is ProjectCompatibilityState.DemoReady -> {
                when (val state = connectionState) {
                    AgentConnectionState.Connecting ->
                        "SecureLoop is connecting to the local companion service."

                    is AgentConnectionState.Connected -> {
                        if (state.demoModeAvailable) {
                            "Demo mode is ready. Click Run Demo to load a sample incident or Scan Current File to analyze the active editor."
                        } else {
                            "The local agent is connected. Scan Current File is available, but Run Demo is disabled until SECURE_LOOP_ALLOW_DEBUG_ENDPOINTS=1 is enabled."
                        }
                    }

                    is AgentConnectionState.WaitingForAgent -> state.reason
                    is AgentConnectionState.Unauthorized -> state.reason
                }
            }

            is ProjectCompatibilityState.Unsupported -> compatibility.reason
        }
    }

    private fun statusTitle(): String {
        if (projectCompatibility is ProjectCompatibilityState.Unsupported) {
            return "Unsupported project"
        }

        return when (val state = connectionState) {
            AgentConnectionState.Connecting -> "Connecting to local agent"
            is AgentConnectionState.Connected -> if (state.demoModeAvailable) "Demo ready" else "Connected to local agent"
            is AgentConnectionState.WaitingForAgent -> "Waiting for local agent"
            is AgentConnectionState.Unauthorized -> "Agent authorization failed"
        }
    }

    private fun statusMessage(): String {
        return buildString {
            when (val compatibility = projectCompatibility) {
                is ProjectCompatibilityState.DemoReady -> {
                    appendLine("Demo repo detected: ${compatibility.targetPath}")
                    appendLine("Security policy detected: ${compatibility.policyPath}")
                }

                is ProjectCompatibilityState.Unsupported -> {
                    appendLine(compatibility.reason)
                }
            }

            when (val state = connectionState) {
                AgentConnectionState.Connecting -> {
                    append("Checking SecureLoop agent health at http://127.0.0.1:8001.")
                }

                is AgentConnectionState.Connected -> {
                    append("Connected to ${state.baseUrl}.")
                    if (state.demoModeAvailable) {
                        append(" Run Demo will load a sample incident into the tool window. Scan Current File will analyze the active editor.")
                    } else {
                        append(" Scan Current File is still available. Run Demo is off until SECURE_LOOP_ALLOW_DEBUG_ENDPOINTS=1 is enabled.")
                    }
                }

                is AgentConnectionState.WaitingForAgent -> append(state.reason)
                is AgentConnectionState.Unauthorized -> append(state.reason)
            }
        }
    }

    private fun resolutionText(resolution: ResolutionState): String {
        return when (resolution) {
            ResolutionState.Pending -> "Resolving local file..."
            is ResolutionState.Resolved -> "${resolution.filePath}:${resolution.lineNumber}"
            is ResolutionState.Ambiguous -> "Ambiguous: ${resolution.candidates.joinToString()}"
            is ResolutionState.Unresolved -> "Unresolved: ${resolution.reason}"
        }
    }

    private fun analysisStateText(state: AnalysisState): String {
        return when (state) {
            AnalysisState.Idle -> "Idle"
            AnalysisState.Loading -> "Analyzing..."
            AnalysisState.Ready -> "Analysis ready"
            AnalysisState.Applying -> "Applying approved patch..."
            is AnalysisState.Applied -> if (state.stagedInGit) {
                "Saved + staged in Git"
            } else {
                "Saved (Git not detected)"
            }
            AnalysisState.Failed -> "Failed"
        }
    }

    private fun analysisText(analysis: AnalyzeIncidentResponse): String {
        return buildString {
            appendLine("Analysis")
            appendLine("Severity: ${analysis.severity}")
            appendLine("Category: ${analysis.category}")
            appendLine("CWE: ${analysis.cwe}")
            appendLine("Title: ${analysis.title}")
            appendLine()
            appendLine("Explanation:")
            appendLine(analysis.explanation)
            appendLine()
            appendLine("Violated policy:")
            analysis.violatedPolicy.forEach { rule ->
                appendLine("- $rule")
            }
            appendLine()
            appendLine("Fix plan:")
            analysis.fixPlan.forEachIndexed { index, step ->
                appendLine("${index + 1}. $step")
            }
            if (analysis.reasoningSteps.isNotEmpty()) {
                appendLine()
                appendLine("Reasoning steps:")
                analysis.reasoningSteps.forEachIndexed { index, step ->
                    appendLine("${index + 1}. $step")
                }
            }
            analysis.depCheck?.let { dep ->
                appendLine()
                appendLine("Dependency scan (${dep.scanner}):")
                if (dep.vulnerabilities.isEmpty()) {
                    appendLine("- No vulnerable dependencies detected.")
                } else {
                    dep.vulnerabilities.forEach { vuln ->
                        val fixed = vuln.fixedVersion?.let { " -> $it" } ?: ""
                        appendLine("- [${vuln.severity}] ${vuln.id} ${vuln.`package`}==${vuln.version}$fixed")
                        appendLine("    ${vuln.summary}")
                    }
                }
                dep.advisoryUrl?.takeIf { it.isNotBlank() }?.let {
                    appendLine("Advisory: $it")
                }
            }
            appendLine()
            appendLine("Diff:")
            appendLine(analysis.diff)
        }
    }

    private class IncidentCellRenderer : ColoredListCellRenderer<IncidentPresentation>() {
        override fun customizeCellRenderer(
            list: JList<out IncidentPresentation>,
            value: IncidentPresentation,
            index: Int,
            selected: Boolean,
            hasFocus: Boolean,
        ) {
            append(value.incident.exceptionType, SimpleTextAttributes.REGULAR_BOLD_ATTRIBUTES)
            append(" ${value.incident.title}", SimpleTextAttributes.REGULAR_ATTRIBUTES)

            val location = buildString {
                value.incident.repoRelativePath?.let { append(it) }
                value.incident.lineNumber?.let { append(":$it") }
            }.ifBlank { "location unavailable" }
            append("  $location", SimpleTextAttributes.GRAY_ATTRIBUTES)

            val status = when (value.resolution) {
                ResolutionState.Pending -> "pending"
                is ResolutionState.Resolved -> "resolved"
                is ResolutionState.Ambiguous -> "ambiguous"
                is ResolutionState.Unresolved -> "unresolved"
            }
            append("  [$status]", SimpleTextAttributes.GRAYED_SMALL_ATTRIBUTES)
            if (value.reviewed) {
                append("  [reviewed]", SimpleTextAttributes.GRAYED_SMALL_ATTRIBUTES)
            }
        }
    }
}
