package dev.secureloop.plugin.util

import com.intellij.openapi.project.Project
import com.intellij.openapi.roots.ProjectRootManager
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VfsUtilCore
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.openapi.vfs.VirtualFileFilter
import com.intellij.util.indexing.ContentIterator
import dev.secureloop.plugin.model.NormalizedIncident
import java.nio.file.Path

sealed interface FileResolution {
    data class Resolved(
        val file: VirtualFile,
        val lineNumber: Int,
    ) : FileResolution

    data class Ambiguous(
        val candidates: List<String>,
    ) : FileResolution

    data class Unresolved(
        val reason: String,
    ) : FileResolution
}

object ProjectFileResolver {
    private val ignoredDirectories = setOf(".git", ".idea", ".gradle", "node_modules", "build", "dist")

    fun resolve(project: Project, incident: NormalizedIncident): FileResolution {
        val repoRelative = normalizePath(incident.repoRelativePath)
        val original = normalizePath(incident.originalFramePath)
        val safeLine = (incident.lineNumber ?: 1).coerceAtLeast(1)

        if (project.basePath == null) {
            return FileResolution.Unresolved("no_open_project")
        }

        val direct = repoRelative?.let { findDirectMatch(project, it) }
            ?: original?.let { findAbsolutePath(it) }
        if (direct != null) {
            return FileResolution.Resolved(direct, safeLine)
        }

        val suffixMatches = repoRelative?.let { findSuffixMatches(project, it) }.orEmpty()
        if (suffixMatches.size == 1) {
            return FileResolution.Resolved(suffixMatches.first(), safeLine)
        }
        if (suffixMatches.size > 1) {
            return FileResolution.Ambiguous(suffixMatches.map(VirtualFile::getPath).sorted())
        }

        val basenameMatches = basename(repoRelative ?: original)?.let { findBasenameMatches(project, it) }.orEmpty()
        if (basenameMatches.size == 1) {
            return FileResolution.Resolved(basenameMatches.first(), safeLine)
        }
        if (basenameMatches.size > 1) {
            return FileResolution.Ambiguous(basenameMatches.map(VirtualFile::getPath).sorted())
        }

        return FileResolution.Unresolved("file_not_found")
    }

    fun findByAbsolutePath(project: Project, filePath: String): VirtualFile? {
        val normalized = normalizePath(filePath) ?: return null
        return findAbsolutePath(normalized) ?: findDirectMatch(project, normalized)
    }

    private fun findDirectMatch(project: Project, repoRelativePath: String): VirtualFile? {
        val basePath = project.basePath ?: return null
        val path = Path.of(basePath).resolve(repoRelativePath).normalize()
        return LocalFileSystem.getInstance().refreshAndFindFileByPath(path.toString().replace("\\", "/"))
    }

    private fun findAbsolutePath(path: String): VirtualFile? {
        return LocalFileSystem.getInstance().refreshAndFindFileByPath(path)
    }

    private fun findSuffixMatches(project: Project, suffix: String): List<VirtualFile> {
        val normalizedSuffix = suffix.removePrefix("/")
        return scanProjectFiles(project) { file ->
            val normalizedPath = normalizePath(file.path) ?: return@scanProjectFiles false
            normalizedPath == normalizedSuffix || normalizedPath.endsWith("/$normalizedSuffix")
        }
    }

    private fun findBasenameMatches(project: Project, basename: String): List<VirtualFile> {
        return scanProjectFiles(project) { file -> file.name == basename }
    }

    private fun scanProjectFiles(project: Project, predicate: (VirtualFile) -> Boolean): List<VirtualFile> {
        val results = linkedSetOf<VirtualFile>()
        val roots = ProjectRootManager.getInstance(project).contentRootsFromAllModules
        for (root in roots) {
            VfsUtilCore.iterateChildrenRecursively(
                root,
                VirtualFileFilter { file ->
                    !file.isDirectory || file.name !in ignoredDirectories
                },
                ContentIterator { file ->
                    if (!file.isDirectory && predicate(file)) {
                        results.add(file)
                    }
                    true
                },
            )
        }
        return results.toList()
    }

    private fun basename(path: String?): String? {
        val normalized = normalizePath(path) ?: return null
        return normalized.substringAfterLast('/')
    }

    private fun normalizePath(path: String?): String? {
        if (path.isNullOrBlank()) {
            return null
        }
        return path.replace("\\", "/").trim().removePrefix("file:///")
    }
}
