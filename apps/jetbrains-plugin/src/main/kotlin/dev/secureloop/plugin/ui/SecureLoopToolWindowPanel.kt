package dev.secureloop.plugin.ui

import com.intellij.ui.ColoredListCellRenderer
import com.intellij.ui.SimpleTextAttributes
import com.intellij.ui.components.JBList
import com.intellij.ui.components.JBScrollPane
import com.intellij.ui.components.JBTextArea
import dev.secureloop.plugin.model.IncidentPresentation
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
    private val detailArea = JBTextArea()
    private val openFileButton = JButton("Open File")
    private val openSentryButton = JButton("Open Sentry")

    init {
        incidentList.selectionMode = ListSelectionModel.SINGLE_SELECTION
        incidentList.cellRenderer = IncidentCellRenderer()
        incidentList.addListSelectionListener {
            renderSelection()
        }

        detailArea.isEditable = false
        detailArea.lineWrap = true
        detailArea.wrapStyleWord = true

        openFileButton.addActionListener {
            selectedIncident()?.let(projectService::openSelectionInEditor)
        }
        openSentryButton.addActionListener {
            selectedIncident()?.let(projectService::openIncidentInBrowser)
        }

        val buttonBar = JPanel().apply {
            add(openFileButton)
            add(openSentryButton)
        }

        val splitPane = JSplitPane(
            JSplitPane.VERTICAL_SPLIT,
            JBScrollPane(incidentList),
            JBScrollPane(detailArea),
        ).apply {
            resizeWeight = 0.55
        }

        add(buttonBar, BorderLayout.NORTH)
        add(splitPane, BorderLayout.CENTER)
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

    private fun renderSelection() {
        val presentation = selectedIncident()
        if (presentation == null) {
            detailArea.text = "Waiting for a signed Sentry incident from the SecureLoop companion service."
            openFileButton.isEnabled = false
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
            presentation.incident.codeContext?.takeIf { it.isNotBlank() }?.let {
                appendLine()
                appendLine("Code context:")
                appendLine(it)
            }
        }

        openSentryButton.isEnabled = true
        openFileButton.isEnabled = presentation.resolution is ResolutionState.Resolved
    }

    private fun selectedIncident(): IncidentPresentation? = incidentList.selectedValue

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
        }
    }
}
