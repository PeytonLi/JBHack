package dev.secureloop.plugin.services

import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.diagnostic.Logger
import dev.secureloop.plugin.model.NormalizedIncident
import kotlinx.serialization.json.Json
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.nio.file.Files
import java.nio.file.Path
import java.time.Duration

@Service(Service.Level.APP)
class SecureLoopApplicationService : Disposable {
    private val logger = Logger.getInstance(SecureLoopApplicationService::class.java)
    private val json = Json { ignoreUnknownKeys = true }
    private val client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .build()

    @Volatile
    private var started = false

    @Volatile
    private var disposed = false

    fun start() {
        if (started) {
            return
        }

        synchronized(this) {
            if (started) {
                return
            }
            started = true
        }

        ApplicationManager.getApplication().executeOnPooledThread {
            connectionLoop()
        }
    }

    fun acknowledgeIncident(incidentId: String) {
        ApplicationManager.getApplication().executeOnPooledThread {
            val token = loadToken() ?: return@executeOnPooledThread
            try {
                val request = HttpRequest.newBuilder(URI.create("${agentBaseUrl()}/ide/events/$incidentId/ack"))
                    .header("Authorization", "Bearer $token")
                    .POST(HttpRequest.BodyPublishers.noBody())
                    .timeout(Duration.ofSeconds(5))
                    .build()
                client.send(request, HttpResponse.BodyHandlers.discarding())
            } catch (exception: Exception) {
                logger.warn("Failed to acknowledge incident $incidentId", exception)
            }
        }
    }

    override fun dispose() {
        disposed = true
    }

    private fun connectionLoop() {
        while (!disposed) {
            val token = loadToken()
            if (token.isNullOrBlank()) {
                logger.warn("SecureLoop token not found. Expected ${tokenFilePath()}.")
                sleepBeforeReconnect()
                continue
            }

            try {
                streamIncidents(token)
            } catch (exception: Exception) {
                logger.warn("SecureLoop event stream disconnected.", exception)
            }

            sleepBeforeReconnect()
        }
    }

    private fun streamIncidents(token: String) {
        val request = HttpRequest.newBuilder(URI.create("${agentBaseUrl()}/ide/events/stream"))
            .header("Accept", "text/event-stream")
            .header("Authorization", "Bearer $token")
            .timeout(Duration.ofMinutes(30))
            .GET()
            .build()

        val response = client.send(request, HttpResponse.BodyHandlers.ofInputStream())
        if (response.statusCode() != 200) {
            logger.warn("SecureLoop stream returned HTTP ${response.statusCode()}.")
            return
        }

        BufferedReader(InputStreamReader(response.body())).use { reader ->
            readServerSentEvents(reader)
        }
    }

    private fun readServerSentEvents(reader: BufferedReader) {
        val payload = StringBuilder()
        while (!disposed) {
            val line = reader.readLine() ?: break
            when {
                line.startsWith("data:") -> {
                    payload.append(line.removePrefix("data:").trimStart())
                }

                line.isBlank() && payload.isNotEmpty() -> {
                    handlePayload(payload.toString())
                    payload.setLength(0)
                }
            }
        }
    }

    private fun handlePayload(payload: String) {
        val incident = json.decodeFromString<NormalizedIncident>(payload)
        ApplicationManager.getApplication()
            .messageBus
            .syncPublisher(INCIDENT_TOPIC)
            .incidentReceived(incident)
    }

    private fun loadToken(): String? {
        val fromEnvironment = System.getenv("SECURE_LOOP_IDE_TOKEN")?.trim()
        if (!fromEnvironment.isNullOrEmpty()) {
            return fromEnvironment
        }

        val tokenFile = tokenFilePath()
        if (!Files.exists(tokenFile)) {
            return null
        }
        return Files.readString(tokenFile).trim().ifBlank { null }
    }

    private fun tokenFilePath(): Path {
        return Path.of(System.getProperty("user.home"), ".secureloop", "ide-token")
    }

    private fun agentBaseUrl(): String {
        return System.getenv("SECURE_LOOP_AGENT_URL")?.trim().orEmpty()
            .ifBlank { "http://127.0.0.1:8001" }
    }

    private fun sleepBeforeReconnect() {
        try {
            Thread.sleep(3_000)
        } catch (_: InterruptedException) {
            Thread.currentThread().interrupt()
        }
    }
}
