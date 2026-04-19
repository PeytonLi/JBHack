package dev.secureloop.plugin.ui

import com.intellij.ui.ColoredListCellRenderer
import com.intellij.ui.SimpleTextAttributes
import com.intellij.ui.components.JBList
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBScrollPane
import com.intellij.ui.components.JBTextArea
import dev.secureloop.plugin.model.AgentConnectionState
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
    private val retryConnectionButton = JButton("Retry Connection")
    private val setupGuideButton = JButton("Open Setup Guide")
    private val openFileButton = JButton("Open File")
    private val markReviewedButton = JButton("Mark Reviewed")
    private val openSentryButton = JButton("Open Sentry")
    private val analyzeButton = JButton("Analyze")
    private val approveButton = JButton("Approve (Apply & Open PR)")
    private val rejectButton = JButton("Reject")
    private var analyzing = false
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
        retryConnectionButton.addActionListener {
            projectService.retryConnection()
        }
        setupGuideButton.addActionListener {
            projectService.openSetupGuide()
        }
        openFileButton.addActionListener {
            selectedIncident()?.let(projectService::openSelectionInEditor)
        }
        markReviewedButton.addActionListener {
            selectedIncident()?.let(projectService::markIncidentReviewed)
            renderSelection()
        }
        openSentryButton.addActionListener {
            selectedIncident()?.let(projectService::openIncidentInBrowser)
        }
        analyzeButton.addActionListener {
            selectedIncident()?.let(projectService::analyzeSelectedIncident)
        }
        approveButton.addActionListener {
            selectedIncident()?.let(projectService::approveAndApplyFix)
        }
        rejectButton.addActionListener {
            selectedIncident()?.let(projectService::rejectFix)
        }

        val statusPanel = JPanel(BorderLayout()).apply {
            add(statusLabel, BorderLayout.NORTH)
            add(statusArea, BorderLayout.CENTER)
        }

        val buttonBar = JPanel().apply {
            add(runDemoButton)
            add(retryConnectionButton)
            add(setupGuideButton)
            add(openFileButton)
            add(markReviewedButton)
            add(openSentryButton)
            add(analyzeButton)
            add(approveButton)
            add(rejectButton)
        }

        val topPanel = JPanel(BorderLayout()).apply {
            add(statusPanel, BorderLayout.CENTER)
            add(buttonBar, BorderLayout.SOUTH)
        }

        val splitPane = JSplitPane(
            JSplitPane.VERTICAL_SPLIT,
            JBScrollPane(incidentList),
            JBScrollPane(detailArea),
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

    fun setAnalyzing(value: Boolean) {
        analyzing = value
        renderSelection()
    }

    private fun renderSelection() {
        renderEnvironment()
        val presentation = selectedIncident()
        if (presentation == null) {
            detailArea.text = onboardingMessage()
            openFileButton.isEnabled = false
            markReviewedButton.isEnabled = false
            openSentryButton.isEnabled = false
            return
        }

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
            presentation.incident.codeContext?.takeIf { it.isNotBlank() }?.let {
                appendLine()
                appendLine("Code context:")
                appendLine(it)
            }

            if (analyzing) {
                appendLine()
                appendLine("═══════════════════════════════════════")
                appendLine("⏳ Analyzing with Codex...")
                appendLine("═══════════════════════════════════════")
            }

            presentation.analysis?.let { analysis ->
                appendLine()
                appendLine("═══════════════════════════════════════")
                appendLine("SECURITY ANALYSIS")
                appendLine("═══════════════════════════════════════")
                appendLine("Severity: ${analysis.severity}")
                analysis.cwe?.let { appendLine("CWE: $it") }
                analysis.owasp?.let { appendLine("OWASP: $it") }
                analysis.category?.let { appendLine("Category: $it") }
                appendLine()
                appendLine("Explanation:")
                appendLine(analysis.explanation)
                if (analysis.violatedPolicy.isNotEmpty()) {
                    appendLine()
                    appendLine("Violated Policies:")
                    analysis.violatedPolicy.forEach { appendLine("  • $it") }
                }
                if (analysis.fixPlan.isNotEmpty()) {
                    appendLine()
                    appendLine("Fix Plan:")
                    analysis.fixPlan.forEach { appendLine("  • $it") }
                }
                appendLine()
                appendLine("Diff:")
                appendLine(analysis.diff)
            }
        }

        openSentryButton.isEnabled = true
        openFileButton.isEnabled = presentation.resolution is ResolutionState.Resolved
        markReviewedButton.isEnabled = !presentation.reviewed
        analyzeButton.isEnabled = presentation.resolution is ResolutionState.Resolved
            && presentation.analysis == null
            && !analyzing
        approveButton.isEnabled = presentation.analysis != null
        rejectButton.isEnabled = presentation.analysis != null
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
                            "Demo mode is ready. Click Run Demo to load a sample incident, open apps/target/src/main.py, and highlight the vulnerable line."
                        } else {
                            "The local agent is connected, but demo mode is disabled. Set SECURE_LOOP_ALLOW_DEBUG_ENDPOINTS=1 in the repo .env and restart pnpm dev."
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
                        append(" Run Demo will load a sample incident into the tool window.")
                    } else {
                        append(" Demo mode is off until SECURE_LOOP_ALLOW_DEBUG_ENDPOINTS=1 is enabled.")
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
