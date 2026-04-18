package dev.secureloop.plugin.services

import com.intellij.openapi.components.service
import com.intellij.openapi.project.Project
import com.intellij.openapi.startup.ProjectActivity

class SecureLoopStartupActivity : ProjectActivity {
    override suspend fun execute(project: Project) {
        service<SecureLoopApplicationService>().start()
        project.service<SecureLoopProjectService>()
    }
}
