package dev.secureloop.plugin.services

import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.diagnostic.Logger
import dev.secureloop.plugin.model.AgentConnectionState
import dev.secureloop.plugin.model.AgentHealthResponse
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

    @Volatile
    private var connectionState: AgentConnectionState = AgentConnectionState.Connecting

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

    fun currentConnectionState(): AgentConnectionState = connectionState

    fun refreshStatus() {
        ApplicationManager.getApplication().executeOnPooledThread {
            publishConnectionState(resolveConnectionState())
        }
    }

    fun triggerDemoIncident() {
        ApplicationManager.getApplication().executeOnPooledThread {
            val token = loadToken()
            if (token.isNullOrBlank()) {
                publishConnectionState(
                    AgentConnectionState.WaitingForAgent(
                        "SecureLoop is waiting for the local agent token at ${tokenFilePath()}.",
                    ),
                )
                return@executeOnPooledThread
            }

            val health = fetchHealth()
            if (health == null) {
                publishConnectionState(
                    AgentConnectionState.WaitingForAgent(
                        "SecureLoop could not reach the local agent at ${agentBaseUrl()}.",
                    ),
                )
                return@executeOnPooledThread
            }

            if (!health.allowDebugEndpoints) {
                publishConnectionState(
                    AgentConnectionState.Connected(
                        baseUrl = agentBaseUrl(),
                        demoModeAvailable = false,
                    ),
                )
                return@executeOnPooledThread
            }

            try {
                val request = HttpRequest.newBuilder(URI.create("${agentBaseUrl()}/debug/incidents"))
                    .header("Authorization", "Bearer $token")
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(demoIncidentRequestBody()))
                    .timeout(Duration.ofSeconds(5))
                    .build()
                val response = client.send(request, HttpResponse.BodyHandlers.discarding())
                when (response.statusCode()) {
                    201 -> {
                        publishConnectionState(
                            AgentConnectionState.Connected(
                                baseUrl = agentBaseUrl(),
                                demoModeAvailable = true,
                            ),
                        )
                    }

                    401 -> {
                        publishConnectionState(
                            AgentConnectionState.Unauthorized(
                                "The IDE token was rejected by the local agent.",
                            ),
                        )
                    }

                    404 -> {
                        publishConnectionState(
                            AgentConnectionState.Connected(
                                baseUrl = agentBaseUrl(),
                                demoModeAvailable = false,
                            ),
                        )
                    }

                    else -> {
                        publishConnectionState(
                            AgentConnectionState.WaitingForAgent(
                                "Demo mode request failed with HTTP ${response.statusCode()}.",
                            ),
                        )
                    }
                }
            } catch (exception: Exception) {
                logger.warn("Failed to trigger SecureLoop demo incident.", exception)
                publishConnectionState(
                    AgentConnectionState.WaitingForAgent(
                        "SecureLoop could not send the demo incident to ${agentBaseUrl()}.",
                    ),
                )
            }
        }
    }

    fun markIncidentReviewed(incidentId: String) {
        ApplicationManager.getApplication().executeOnPooledThread {
            val token = loadToken() ?: return@executeOnPooledThread
            try {
                val request = HttpRequest.newBuilder(URI.create("${agentBaseUrl()}/ide/events/$incidentId/review"))
                    .header("Authorization", "Bearer $token")
                    .POST(HttpRequest.BodyPublishers.noBody())
                    .timeout(Duration.ofSeconds(5))
                    .build()
                val response = client.send(request, HttpResponse.BodyHandlers.discarding())
                if (response.statusCode() >= 400) {
                    logger.warn("Failed to mark incident $incidentId as reviewed. HTTP ${response.statusCode()}.")
                }
            } catch (exception: Exception) {
                logger.warn("Failed to mark incident $incidentId as reviewed", exception)
            }
        }
    }

    override fun dispose() {
        disposed = true
    }

    private fun connectionLoop() {
        while (!disposed) {
            val state = resolveConnectionState()
            publishConnectionState(state)

            val token = loadToken()
            if (state !is AgentConnectionState.Connected || token.isNullOrBlank()) {
                sleepBeforeReconnect()
                continue
            }

            try {
                streamIncidents(token, state)
            } catch (exception: Exception) {
                logger.warn("SecureLoop event stream disconnected.", exception)
                publishConnectionState(
                    AgentConnectionState.WaitingForAgent(
                        "The SecureLoop event stream disconnected from ${agentBaseUrl()}.",
                    ),
                )
            }

            sleepBeforeReconnect()
        }
    }

    private fun streamIncidents(
        token: String,
        state: AgentConnectionState.Connected,
    ) {
        val request = HttpRequest.newBuilder(URI.create("${agentBaseUrl()}/ide/events/stream"))
            .header("Accept", "text/event-stream")
            .header("Authorization", "Bearer $token")
            .timeout(Duration.ofMinutes(30))
            .GET()
            .build()

        val response = client.send(request, HttpResponse.BodyHandlers.ofInputStream())
        when (response.statusCode()) {
            200 -> {
                publishConnectionState(state)
            }

            401 -> {
                publishConnectionState(
                    AgentConnectionState.Unauthorized(
                        "The IDE token was rejected by the SecureLoop agent.",
                    ),
                )
                return
            }

            else -> {
                logger.warn("SecureLoop stream returned HTTP ${response.statusCode()}.")
                publishConnectionState(
                    AgentConnectionState.WaitingForAgent(
                        "SecureLoop could not open the event stream at ${agentBaseUrl()}.",
                    ),
                )
                return
            }
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

    private fun resolveConnectionState(): AgentConnectionState {
        val health = fetchHealth()
        if (health == null) {
            return AgentConnectionState.WaitingForAgent(
                "SecureLoop could not reach the local agent at ${agentBaseUrl()}. Start `pnpm dev` first.",
            )
        }

        val token = loadToken()
        if (token.isNullOrBlank()) {
            logger.warn("SecureLoop token not found. Expected ${tokenFilePath()}.")
            return AgentConnectionState.WaitingForAgent(
                "SecureLoop is waiting for the IDE token file at ${tokenFilePath()}.",
            )
        }

        return AgentConnectionState.Connected(
            baseUrl = agentBaseUrl(),
            demoModeAvailable = health.allowDebugEndpoints,
        )
    }

    private fun fetchHealth(): AgentHealthResponse? {
        return try {
            val request = HttpRequest.newBuilder(URI.create("${agentBaseUrl()}/health"))
                .header("Accept", "application/json")
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build()
            val response = client.send(request, HttpResponse.BodyHandlers.ofString())
            if (response.statusCode() != 200) {
                return null
            }
            json.decodeFromString<AgentHealthResponse>(response.body())
        } catch (exception: Exception) {
            null
        }
    }

    private fun publishConnectionState(state: AgentConnectionState) {
        if (state == connectionState) {
            return
        }
        connectionState = state
        ApplicationManager.getApplication()
            .messageBus
            .syncPublisher(AGENT_STATUS_TOPIC)
            .connectionStateChanged(state)
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

    private fun demoIncidentRequestBody(): String {
        return """
            {
              "repoRelativePath": "apps/target/src/main.py",
              "lineNumber": 37,
              "exceptionType": "RuntimeError",
              "exceptionMessage": "SecureLoop demo mode",
              "title": "SecureLoop demo incident",
              "functionName": "checkout",
              "codeContext": "warehouse_name = WAREHOUSES[warehouse_id]"
            }
        """.trimIndent()
    }

    private fun sleepBeforeReconnect() {
        try {
            Thread.sleep(3_000)
        } catch (_: InterruptedException) {
            Thread.currentThread().interrupt()
        }
    }
}
