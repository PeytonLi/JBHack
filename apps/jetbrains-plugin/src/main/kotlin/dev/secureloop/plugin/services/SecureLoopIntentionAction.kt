package dev.secureloop.plugin.services

import com.intellij.codeInsight.intention.IntentionAction
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.command.WriteCommandAction
import com.intellij.openapi.components.service
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiFile
import dev.secureloop.plugin.model.GenerateCodeBody
import dev.secureloop.plugin.model.GenerateCodeResponse
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.decodeFromString
import java.net.URI
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Duration

class SecureLoopIntentionAction : IntentionAction {
    override fun getText(): String = "SecureLoop: Generate secure code with Codex 5.3"
    override fun getFamilyName(): String = "SecureLoop"
    override fun isAvailable(project: Project, editor: Editor?, file: PsiFile?): Boolean = true
    override fun startInWriteAction(): Boolean = false

    override fun invoke(project: Project, editor: Editor?, file: PsiFile?) {
        if (editor == null || file == null) return
        val caretOffset = editor.caretModel.offset
        val document = editor.document
        val sourceContext = document.text.substring(0, caretOffset).takeLast(1000)

        // Read security policy if exists
        val basePath = project.basePath
        var policyText: String? = null
        if (basePath != null) {
            val policyPath = java.nio.file.Path.of(basePath).resolve("security-policy.md")
            if (java.nio.file.Files.exists(policyPath)) {
                policyText = try {
                    java.nio.file.Files.readString(policyPath)
                } catch (e: Exception) { null }
            }
        }

        val appService = service<SecureLoopApplicationService>()
        ApplicationManager.getApplication().executeOnPooledThread {
            val token = appService.loadToken() ?: return@executeOnPooledThread
            try {
                val bodyJson = buildString {
                    append("{\"sourceContext\":")
                    append(Json.encodeToString(sourceContext))
                    if (policyText != null) {
                        append(",\"policyText\":")
                        append(Json.encodeToString(policyText))
                    }
                    append(",\"language\":\"kotlin\"}")
                }
                
                val request = HttpRequest.newBuilder(URI.create("${appService.agentBaseUrl()}/ide/generate"))
                    .header("Authorization", "Bearer \$token")
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(bodyJson))
                    .timeout(Duration.ofSeconds(30))
                    .build()

                val response = appService.client.send(request, HttpResponse.BodyHandlers.ofString())
                if (response.statusCode() == 200) {
                    val genResponse = Json.decodeFromString<GenerateCodeResponse>(response.body())
                    ApplicationManager.getApplication().invokeLater {
                        WriteCommandAction.runWriteCommandAction(project) {
                            document.insertString(caretOffset, genResponse.completion)
                        }
                    }
                }
            } catch (e: Exception) {
                // Ignore failure for demo
            }
        }
    }
}
