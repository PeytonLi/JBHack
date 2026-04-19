package dev.secureloop.plugin.services

import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.diagnostic.Logger
import dev.secureloop.plugin.model.AgentConnectionState
import dev.secureloop.plugin.model.AgentHealthResponse
import dev.secureloop.plugin.model.AnalyzeIncidentRequest
import dev.secureloop.plugin.model.AnalyzeIncidentResponse
import dev.secureloop.plugin.model.NavigateRequest
import dev.secureloop.plugin.model.NormalizedIncident
import dev.secureloop.plugin.model.PullRequestResult
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.nio.charset.StandardCharsets
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

    fun analyzeIncident(
        payload: AnalyzeIncidentRequest,
        onSuccess: (AnalyzeIncidentResponse) -> Unit,
        onError: (String) -> Unit,
    ) {
        ApplicationManager.getApplication().executeOnPooledThread {
            val token = loadToken()
            if (token.isNullOrBlank()) {
                invokeOnUiThread {
                    onError("SecureLoop is waiting for the IDE token file at ${tokenFilePath()}.")
                }
                return@executeOnPooledThread
            }

            try {
                val requestBody = json.encodeToString(AnalyzeIncidentRequest.serializer(), payload)
                val requestBytes = requestBody.toByteArray(StandardCharsets.UTF_8)
                logger.warn(
                    "Sending SecureLoop analyze request body with ${requestBytes.size} bytes: ${requestBody.take(500)}",
                )
                val request = HttpRequest.newBuilder(URI.create("${agentBaseUrl()}/ide/analyze"))
                    .header("Authorization", "Bearer $token")
                    .header("Content-Type", "application/json; charset=utf-8")
                    .header("Accept", "application/json")
                    .method("POST", HttpRequest.BodyPublishers.ofByteArray(requestBytes))
                    .timeout(Duration.ofSeconds(15))
                    .build()
                val response = client.send(request, HttpResponse.BodyHandlers.ofString())
                val responseBody = truncatedResponseBody(response.body())
                when (response.statusCode()) {
                    200 -> {
                        val analysis = json.decodeFromString<AnalyzeIncidentResponse>(response.body())
                        invokeOnUiThread {
                            onSuccess(analysis)
                        }
                    }

                    401 -> {
                        logger.warn("Analyze request failed with HTTP ${response.statusCode()}: $responseBody")
                        publishConnectionState(
                            AgentConnectionState.Unauthorized(
                                "The IDE token was rejected by the SecureLoop agent.",
                            ),
                        )
                        invokeOnUiThread {
                            onError("Analyze request failed with HTTP ${response.statusCode()}: $responseBody")
                        }
                    }

                    else -> {
                        logger.warn("Analyze request failed with HTTP ${response.statusCode()}: $responseBody")
                        invokeOnUiThread {
                            onError("Analyze request failed with HTTP ${response.statusCode()}: $responseBody")
                        }
                    }
                }
            } catch (exception: Exception) {
                logger.warn("Failed to analyze SecureLoop incident.", exception)
                invokeOnUiThread {
                    onError("SecureLoop could not analyze the incident via ${agentBaseUrl()}.")
                }
            }
        }
    }

    fun openPullRequest(
        incidentId: String,
        updatedFileContent: String,
        relativePath: String?,
        onSuccess: (PullRequestResult) -> Unit,
        onError: (String) -> Unit,
    ) {
        ApplicationManager.getApplication().executeOnPooledThread {
            val token = loadToken()
            if (token.isNullOrBlank()) {
                invokeOnUiThread {
                    onError("SecureLoop is waiting for the IDE token file at ${tokenFilePath()}.")
                }
                return@executeOnPooledThread
            }

            try {
                val body = OpenPrRequestBody(
                    updatedFileContent = updatedFileContent,
                    relativePath = relativePath,
                )
                val requestBody = json.encodeToString(OpenPrRequestBody.serializer(), body)
                val request = HttpRequest.newBuilder(URI.create("${agentBaseUrl()}/ide/events/$incidentId/open-pr"))
                    .header("Authorization", "Bearer $token")
                    .header("Content-Type", "application/json; charset=utf-8")
                    .header("Accept", "application/json")
                    .method(
                        "POST",
                        HttpRequest.BodyPublishers.ofString(requestBody, StandardCharsets.UTF_8),
                    )
                    .timeout(Duration.ofSeconds(30))
                    .build()
                val response = client.send(request, HttpResponse.BodyHandlers.ofString())
                val responseBody = truncatedResponseBody(response.body())
                when (response.statusCode()) {
                    200 -> {
                        val result = json.decodeFromString<PullRequestResult>(response.body())
                        invokeOnUiThread { onSuccess(result) }
                    }

                    401 -> {
                        publishConnectionState(
                            AgentConnectionState.Unauthorized(
                                "The IDE token was rejected by the SecureLoop agent.",
                            ),
                        )
                        invokeOnUiThread {
                            onError("Open PR request failed with HTTP ${response.statusCode()}: $responseBody")
                        }
                    }

                    else -> {
                        logger.warn("Open PR failed with HTTP ${response.statusCode()}: $responseBody")
                        invokeOnUiThread {
                            onError("Open PR request failed with HTTP ${response.statusCode()}: $responseBody")
                        }
                    }
                }
            } catch (exception: Exception) {
                logger.warn("Failed to open SecureLoop pull request.", exception)
                invokeOnUiThread {
                    onError("SecureLoop could not open the pull request via ${agentBaseUrl()}.")
                }
            }
        }
    }

    override fun dispose() {
        disposed = true
    }

    @Serializable
    private data class OpenPrRequestBody(
        val updatedFileContent: String,
        val relativePath: String?,
    )

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
        var eventName: String? = null
        while (!disposed) {
            val line = reader.readLine() ?: break
            when {
                line.startsWith("event:") -> {
                    eventName = line.removePrefix("event:").trim()
                }

                line.startsWith("data:") -> {
                    payload.append(line.removePrefix("data:").trimStart())
                }

                line.isBlank() && payload.isNotEmpty() -> {
                    handlePayload(payload.toString(), eventName)
                    payload.setLength(0)
                    eventName = null
                }
            }
        }
    }

    private fun handlePayload(payload: String, eventName: String?) {
        try {
            when (eventName) {
                "ide.navigate" -> {
                    val req = json.decodeFromString<NavigateRequest>(payload)
                    ApplicationManager.getApplication()
                        .messageBus
                        .syncPublisher(NAVIGATE_TOPIC)
                        .navigateRequested(req)
                }

                else -> {
                    val incident = json.decodeFromString<NormalizedIncident>(payload)
                    ApplicationManager.getApplication()
                        .messageBus
                        .syncPublisher(INCIDENT_TOPIC)
                        .incidentReceived(incident)
                }
            }
        } catch (t: Throwable) {
            logger.warn("Failed to dispatch SSE payload for event=$eventName", t)
        }
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
              "lineNumber": 45,
              "exceptionType": "RuntimeError",
              "exceptionMessage": "SecureLoop demo mode",
              "title": "SecureLoop demo incident",
              "functionName": "checkout",
              "codeContext": "warehouse_name = WAREHOUSES[warehouse_id]"
            }
        """.trimIndent()
    }

    private fun invokeOnUiThread(action: () -> Unit) {
        ApplicationManager.getApplication().invokeLater(action)
    }

    private fun truncatedResponseBody(body: String?): String {
        val normalized = body?.trim().orEmpty().ifBlank { "<empty response body>" }
        return if (normalized.length <= 800) {
            normalized
        } else {
            normalized.take(800) + "..."
        }
    }

    private fun sleepBeforeReconnect() {
        try {
            Thread.sleep(3_000)
        } catch (_: InterruptedException) {
            Thread.currentThread().interrupt()
        }
    }
}
