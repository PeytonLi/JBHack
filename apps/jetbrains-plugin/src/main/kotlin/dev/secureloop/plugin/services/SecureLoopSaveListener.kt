package dev.secureloop.plugin.services

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.service
import com.intellij.openapi.editor.Document
import com.intellij.openapi.fileEditor.FileDocumentManager
import com.intellij.openapi.fileEditor.FileDocumentManagerListener
import com.intellij.openapi.project.ProjectManager
import dev.secureloop.plugin.model.AnalyzeFileBody
import dev.secureloop.plugin.model.AnalyzeIncidentResponse
import kotlinx.serialization.encodeToString
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.Json
import java.net.URI
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.nio.file.Files
import java.nio.file.Path
import java.time.Duration

class SecureLoopSaveListener : FileDocumentManagerListener {

    override fun beforeDocumentSaving(document: Document) {
        val file = FileDocumentManager.getInstance().getFile(document) ?: return
        val project = ProjectManager.getInstance().openProjects.firstOrNull() ?: return
        
        val filePath = file.path
        val fileContents = document.text

        // Read security policy if exists
        var policyText: String? = null
        val basePath = project.basePath
        if (basePath != null) {
            val policyPath = Path.of(basePath).resolve("security-policy.md")
            if (Files.exists(policyPath)) {
                policyText = try {
                    Files.readString(policyPath)
                } catch (e: Exception) { null }
            }
        }

        val appService = service<SecureLoopApplicationService>()
        
        ApplicationManager.getApplication().executeOnPooledThread {
            val token = appService.loadToken() ?: return@executeOnPooledThread
            
            try {
                val bodyJson = buildString {
                    append("{\"filePath\":")
                    append(Json.encodeToString(filePath))
                    append(",\"fileContents\":")
                    append(Json.encodeToString(fileContents))
                    if (policyText != null) {
                        append(",\"policyText\":")
                        append(Json.encodeToString(policyText))
                    }
                    append("}")
                }
                
                val request = HttpRequest.newBuilder(URI.create("${appService.agentBaseUrl()}/ide/analyze-file"))
                    .header("Authorization", "Bearer \$token")
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(bodyJson))
                    .timeout(Duration.ofSeconds(60))
                    .build()

                val response = appService.client.send(request, HttpResponse.BodyHandlers.ofString())
                if (response.statusCode() == 200) {
                    val analysis = Json.decodeFromString<AnalyzeIncidentResponse>(response.body())
                    
                    if (analysis.severity == "High" || analysis.severity == "Critical") {
                        // Forward to project service to highlight and show in tool window
                        val projectService = project.getService(SecureLoopProjectService::class.java)
                        projectService?.reportVulnerability(file, analysis)
                    }
                }
            } catch (e: Exception) {
                // Ignore failure for demo
            }
        }
    }
}
