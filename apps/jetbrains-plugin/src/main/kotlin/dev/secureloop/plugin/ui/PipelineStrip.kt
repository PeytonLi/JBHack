package dev.secureloop.plugin.ui

import com.intellij.ide.BrowserUtil
import com.intellij.ui.components.JBLabel
import com.intellij.util.ui.JBUI
import dev.secureloop.plugin.model.PipelineFailureReasons
import dev.secureloop.plugin.model.PipelineState
import dev.secureloop.plugin.model.PipelineStepId
import java.awt.Color
import java.awt.Cursor
import java.awt.FlowLayout
import java.awt.event.MouseAdapter
import java.awt.event.MouseEvent
import javax.swing.BorderFactory
import javax.swing.JPanel

class PipelineStrip : JPanel(FlowLayout(FlowLayout.LEFT, 6, 0)) {
    private val stepOrder = listOf(
        PipelineStepId.FETCH_SOURCE to "Fetch",
        PipelineStepId.ANALYZE to "Analyze",
        PipelineStepId.SANDBOX to "Sandbox",
        PipelineStepId.OPEN_PR to "Open PR",
    )
    private val pills: Map<PipelineStepId, JBLabel>
    private val statusLabel = JBLabel()
    private val prLink = JBLabel()

    init {
        border = BorderFactory.createEmptyBorder(4, 8, 4, 8)
        val built = mutableMapOf<PipelineStepId, JBLabel>()
        stepOrder.forEachIndexed { index, (step, label) ->
            val pill = pillLabel(label)
            built[step] = pill
            add(pill)
            if (index < stepOrder.lastIndex) {
                add(JBLabel("›"))
            }
        }
        pills = built
        add(statusLabel)
        add(prLink)
        applyState(null)
    }

    fun applyState(state: PipelineState?) {
        if (state == null) {
            isVisible = false
            return
        }
        isVisible = true
        when (state) {
            is PipelineState.Running -> {
                val currentIdx = stepOrder.indexOfFirst { it.first == state.step }
                stepOrder.forEachIndexed { idx, (step, _) ->
                    val pill = pills[step] ?: return@forEachIndexed
                    pill.background = when {
                        idx < currentIdx -> DONE_BG
                        idx == currentIdx -> ACTIVE_BG
                        else -> IDLE_BG
                    }
                    pill.foreground = if (idx <= currentIdx) Color.WHITE else INACTIVE_FG
                }
                statusLabel.text = "Running: ${stepOrder[currentIdx.coerceAtLeast(0)].second}"
                statusLabel.foreground = ACTIVE_BG
                prLink.text = ""
                prLink.removeMouseListeners()
            }

            is PipelineState.Completed -> {
                stepOrder.forEach { (step, _) ->
                    val pill = pills[step] ?: return@forEach
                    pill.background = DONE_BG
                    pill.foreground = Color.WHITE
                }
                statusLabel.text = "Pipeline completed"
                statusLabel.foreground = DONE_BG
                val prUrl = state.prUrl
                if (prUrl != null) {
                    prLink.text = "  Open PR #${state.prNumber ?: ""} ↗"
                    prLink.foreground = LINK_FG
                    prLink.cursor = Cursor.getPredefinedCursor(Cursor.HAND_CURSOR)
                    prLink.removeMouseListeners()
                    prLink.addMouseListener(object : MouseAdapter() {
                        override fun mouseClicked(e: MouseEvent?) {
                            BrowserUtil.browse(prUrl)
                        }
                    })
                } else {
                    prLink.text = ""
                    prLink.removeMouseListeners()
                }
            }

            is PipelineState.Failed -> {
                stepOrder.forEach { (step, _) ->
                    val pill = pills[step] ?: return@forEach
                    pill.background = IDLE_BG
                    pill.foreground = INACTIVE_FG
                }
                statusLabel.text = "Failed: ${PipelineFailureReasons.label(state.reason)}"
                statusLabel.foreground = FAILED_FG
                prLink.text = ""
                prLink.removeMouseListeners()
            }
        }
        revalidate()
        repaint()
    }

    private fun pillLabel(text: String): JBLabel {
        val label = JBLabel(" $text ")
        label.isOpaque = true
        label.background = IDLE_BG
        label.foreground = INACTIVE_FG
        label.border = JBUI.Borders.empty(2, 8)
        return label
    }

    private fun JBLabel.removeMouseListeners() {
        mouseListeners.toList().forEach { removeMouseListener(it) }
        cursor = Cursor.getDefaultCursor()
    }

    private companion object {
        val IDLE_BG: Color = Color(60, 63, 65)
        val ACTIVE_BG: Color = Color(56, 139, 253)
        val DONE_BG: Color = Color(46, 160, 67)
        val INACTIVE_FG: Color = Color(180, 180, 180)
        val LINK_FG: Color = Color(88, 166, 255)
        val FAILED_FG: Color = Color(248, 81, 73)
    }
}
