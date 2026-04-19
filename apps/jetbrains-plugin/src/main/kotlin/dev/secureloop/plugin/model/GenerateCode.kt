package dev.secureloop.plugin.model

import kotlinx.serialization.Serializable

@Serializable
data class GenerateCodeBody(
    val sourceContext: String,
    val policyText: String? = null,
    val language: String = "python"
)

@Serializable
data class GenerateCodeResponse(
    val completion: String
)

@Serializable
data class AnalyzeFileBody(
    val filePath: String,
    val fileContents: String,
    val policyText: String? = null
)
