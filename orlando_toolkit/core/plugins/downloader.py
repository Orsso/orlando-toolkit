from __future__ import annotations

"""GitHub plugin download functionality.

Provides the GitHubPluginDownloader class that handles downloading plugin
repositories from GitHub, extracting ZIP archives, and preparing plugins
for installation. Includes robust error handling for network issues and
GitHub API rate limits.
"""

import logging
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import urlparse
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
import json

logger = logging.getLogger(__name__)


class DownloadResult:
    """Result of a plugin download operation."""
    
    def __init__(self, success: bool, message: str = "", 
                 extracted_path: Optional[Path] = None,
                 metadata: Optional[Dict[str, Any]] = None):
        self.success = success
        self.message = message
        self.extracted_path = extracted_path
        self.metadata = metadata
    
    def __str__(self) -> str:
        status = "SUCCESS" if self.success else "FAILED"
        return f"[{status}] {self.message}"


class GitHubPluginDownloader:
    """GitHub repository downloader for Orlando Toolkit plugins.
    
    Handles downloading plugin repositories from GitHub as ZIP archives,
    extracting them to local directories, and providing error handling
    for network issues and GitHub API limitations.
    """
    
    def __init__(self):
        self._logger = logging.getLogger(f"{__name__}.GitHubPluginDownloader")
        
        # User agent for GitHub API requests
        self._user_agent = "OrlandoToolkit-PluginManager/1.0"
        
        # Timeout for network requests (seconds)
        self._request_timeout = 30
    
    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------
    
    def download_repository(self, repository_url: str, branch: str = "main",
                          target_dir: Optional[Path] = None) -> DownloadResult:
        """Download a GitHub repository as a ZIP archive.
        
        Args:
            repository_url: GitHub repository URL (various formats accepted)
            branch: Branch to download (default: "main")
            target_dir: Directory to extract to (temp dir if None)
            
        Returns:
            DownloadResult with success status and extracted path
        """
        self._logger.info("Downloading repository: %s (branch: %s)", repository_url, branch)
        
        try:
            # Parse and validate repository URL
            repo_info = self._parse_repository_url(repository_url)
            if not repo_info:
                return DownloadResult(
                    success=False,
                    message="Invalid GitHub repository URL"
                )
            
            owner, repo = repo_info["owner"], repo_info["repo"]
            
            # Create target directory if not provided
            if target_dir is None:
                target_dir = Path(tempfile.mkdtemp(prefix="orlando_plugin_download_"))
            
            # Build ZIP download URL
            zip_url = f"https://github.com/{owner}/{repo}/archive/{branch}.zip"
            
            # Download the ZIP archive
            self._logger.debug("Downloading ZIP archive: %s", zip_url)
            download_result = self._download_zip_file(zip_url, target_dir)
            
            if not download_result.success:
                return download_result
            
            # Extract the ZIP archive
            zip_file_path = download_result.extracted_path
            extract_result = self._extract_zip_archive(zip_file_path, target_dir)
            
            if not extract_result.success:
                return extract_result
            
            # Find the extracted repository directory
            repo_dir = self._find_repository_directory(target_dir, repo, branch)
            if not repo_dir:
                return DownloadResult(
                    success=False,
                    message="Could not find extracted repository directory"
                )
            
            # Validate basic plugin structure
            if not self._validate_plugin_structure(repo_dir):
                return DownloadResult(
                    success=False,
                    message="Repository does not contain a valid Orlando Toolkit plugin"
                )
            
            self._logger.info("Repository downloaded and extracted successfully: %s", repo_dir)
            
            return DownloadResult(
                success=True,
                message=f"Downloaded {owner}/{repo} successfully",
                extracted_path=repo_dir,
                metadata={
                    "owner": owner,
                    "repository": repo,
                    "branch": branch,
                    "url": repository_url
                }
            )
            
        except Exception as e:
            self._logger.error("Unexpected error during repository download: %s", e)
            return DownloadResult(
                success=False,
                message=f"Download failed: {e}"
            )
    
    def check_repository_exists(self, repository_url: str) -> bool:
        """Check if a GitHub repository exists and is accessible.
        
        Args:
            repository_url: GitHub repository URL
            
        Returns:
            True if repository exists and is accessible
        """
        try:
            repo_info = self._parse_repository_url(repository_url)
            if not repo_info:
                return False
            
            owner, repo = repo_info["owner"], repo_info["repo"]
            
            # Use GitHub API to check repository
            api_url = f"https://api.github.com/repos/{owner}/{repo}"
            
            request = Request(api_url)
            request.add_header("User-Agent", self._user_agent)
            
            with urlopen(request, timeout=self._request_timeout) as response:
                if response.getcode() == 200:
                    return True
            
            return False
            
        except (HTTPError, URLError, Exception) as e:
            self._logger.debug("Repository check failed for %s: %s", repository_url, e)
            return False
    
    def get_repository_info(self, repository_url: str) -> Optional[Dict[str, Any]]:
        """Get information about a GitHub repository.
        
        Args:
            repository_url: GitHub repository URL
            
        Returns:
            Dictionary with repository information or None if failed
        """
        try:
            repo_info = self._parse_repository_url(repository_url)
            if not repo_info:
                return None
            
            owner, repo = repo_info["owner"], repo_info["repo"]
            
            # Use GitHub API to get repository info
            api_url = f"https://api.github.com/repos/{owner}/{repo}"
            
            request = Request(api_url)
            request.add_header("User-Agent", self._user_agent)
            
            with urlopen(request, timeout=self._request_timeout) as response:
                if response.getcode() == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    
                    return {
                        "name": data.get("name"),
                        "full_name": data.get("full_name"),
                        "description": data.get("description"),
                        "default_branch": data.get("default_branch"),
                        "homepage": data.get("homepage"),
                        "clone_url": data.get("clone_url"),
                        "updated_at": data.get("updated_at"),
                        "stars": data.get("stargazers_count"),
                        "language": data.get("language")
                    }
            
            return None
            
        except Exception as e:
            self._logger.debug("Failed to get repository info for %s: %s", repository_url, e)
            return None
    
    # -------------------------------------------------------------------------
    # Internal Helper Methods  
    # -------------------------------------------------------------------------
    
    def _parse_repository_url(self, url: str) -> Optional[Dict[str, str]]:
        """Parse GitHub repository URL and extract owner/repo information.
        
        Supports various URL formats:
        - https://github.com/owner/repo
        - https://github.com/owner/repo.git
        - git@github.com:owner/repo.git
        - owner/repo
        
        Args:
            url: Repository URL in various formats
            
        Returns:
            Dict with 'owner' and 'repo' keys, or None if invalid
        """
        try:
            # Handle different URL formats
            if url.startswith("git@github.com:"):
                # SSH format: git@github.com:owner/repo.git
                match = re.match(r"git@github\.com:([^/]+)/(.+?)(?:\.git)?$", url)
                if match:
                    return {"owner": match.group(1), "repo": match.group(2)}
                    
            elif url.startswith("https://github.com/") or url.startswith("http://github.com/"):
                # HTTPS format: https://github.com/owner/repo or https://github.com/owner/repo.git
                parsed = urlparse(url)
                path_parts = parsed.path.strip("/").split("/")
                if len(path_parts) >= 2:
                    owner = path_parts[0]
                    repo = path_parts[1]
                    # Remove .git suffix if present
                    if repo.endswith(".git"):
                        repo = repo[:-4]
                    return {"owner": owner, "repo": repo}
                    
            elif "/" in url and not url.startswith(("http://", "https://", "git@")):
                # Simple format: owner/repo
                parts = url.split("/")
                if len(parts) == 2:
                    return {"owner": parts[0], "repo": parts[1]}
            
            return None
            
        except Exception as e:
            self._logger.error("Error parsing repository URL %s: %s", url, e)
            return None
    
    def _download_zip_file(self, zip_url: str, target_dir: Path) -> DownloadResult:
        """Download ZIP file from GitHub.
        
        Args:
            zip_url: URL to ZIP archive
            target_dir: Directory to save file to
            
        Returns:
            DownloadResult with path to downloaded file
        """
        try:
            # Create request with proper headers
            request = Request(zip_url)
            request.add_header("User-Agent", self._user_agent)
            
            # Download the file
            with urlopen(request, timeout=self._request_timeout) as response:
                if response.getcode() != 200:
                    return DownloadResult(
                        success=False,
                        message=f"HTTP {response.getcode()}: Failed to download ZIP archive"
                    )
                
                # Generate filename
                zip_filename = target_dir / "plugin-archive.zip"
                
                # Write file content
                with open(zip_filename, 'wb') as f:
                    shutil.copyfileobj(response, f)
                
                self._logger.debug("ZIP archive downloaded: %s (%d bytes)", 
                                 zip_filename, zip_filename.stat().st_size)
                
                return DownloadResult(
                    success=True,
                    message="ZIP archive downloaded successfully",
                    extracted_path=zip_filename
                )
                
        except HTTPError as e:
            if e.code == 404:
                return DownloadResult(
                    success=False,
                    message="Repository or branch not found (404)"
                )
            elif e.code == 403:
                return DownloadResult(
                    success=False,
                    message="Access denied - repository may be private or rate limited (403)"
                )
            else:
                return DownloadResult(
                    success=False,
                    message=f"HTTP error {e.code}: {e.reason}"
                )
        except URLError as e:
            return DownloadResult(
                success=False,
                message=f"Network error: {e.reason}"
            )
        except Exception as e:
            self._logger.error("Unexpected error downloading ZIP: %s", e)
            return DownloadResult(
                success=False,
                message=f"Download failed: {e}"
            )
    
    def _extract_zip_archive(self, zip_path: Path, target_dir: Path) -> DownloadResult:
        """Extract ZIP archive to target directory.
        
        Args:
            zip_path: Path to ZIP file
            target_dir: Directory to extract to
            
        Returns:
            DownloadResult with extraction status
        """
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_file:
                # Check for suspicious files in the ZIP
                for file_info in zip_file.infolist():
                    if self._is_suspicious_zip_entry(file_info):
                        return DownloadResult(
                            success=False,
                            message=f"ZIP archive contains suspicious file: {file_info.filename}"
                        )
                
                # Extract all files
                zip_file.extractall(target_dir)
                
                self._logger.debug("ZIP archive extracted to: %s", target_dir)
                
                return DownloadResult(
                    success=True,
                    message="ZIP archive extracted successfully"
                )
                
        except zipfile.BadZipFile:
            return DownloadResult(
                success=False,
                message="Invalid ZIP archive - file may be corrupted"
            )
        except Exception as e:
            self._logger.error("Error extracting ZIP archive: %s", e)
            return DownloadResult(
                success=False,
                message=f"Extraction failed: {e}"
            )
    
    def _is_suspicious_zip_entry(self, file_info: zipfile.ZipInfo) -> bool:
        """Check if a ZIP entry is suspicious or dangerous.
        
        Args:
            file_info: ZIP file entry information
            
        Returns:
            True if entry is suspicious
        """
        filename = file_info.filename
        
        # Check for directory traversal attacks
        if ".." in filename or filename.startswith("/"):
            return True
        
        # Check for absolute paths
        if Path(filename).is_absolute():
            return True
        
        # Check for suspicious file extensions
        suspicious_extensions = [
            ".exe", ".bat", ".cmd", ".ps1", ".sh", ".scr",
            ".com", ".pif", ".dll", ".sys"
        ]
        
        if any(filename.lower().endswith(ext) for ext in suspicious_extensions):
            return True
        
        return False
    
    def _find_repository_directory(self, extract_dir: Path, repo_name: str, branch: str) -> Optional[Path]:
        """Find the extracted repository directory.
        
        GitHub ZIP archives typically extract to a directory named
        'repository-branch', so we need to find this directory.
        
        Args:
            extract_dir: Directory where ZIP was extracted
            repo_name: Repository name
            branch: Branch name
            
        Returns:
            Path to repository directory or None if not found
        """
        # Common patterns for GitHub ZIP extraction
        possible_names = [
            f"{repo_name}-{branch}",
            f"{repo_name}",
            branch
        ]
        
        for name in possible_names:
            repo_dir = extract_dir / name
            if repo_dir.exists() and repo_dir.is_dir():
                return repo_dir
        
        # If not found, look for any directory containing plugin.json
        for item in extract_dir.iterdir():
            if item.is_dir() and (item / "plugin.json").exists():
                return item
        
        return None
    
    def _validate_plugin_structure(self, repo_dir: Path) -> bool:
        """Validate that the repository contains a valid plugin structure.
        
        Args:
            repo_dir: Repository directory to validate
            
        Returns:
            True if structure appears valid
        """
        # Check for plugin.json
        plugin_json = repo_dir / "plugin.json"
        if not plugin_json.exists():
            return False
        
        # Try to parse plugin.json to ensure it's valid JSON
        try:
            with open(plugin_json, 'r', encoding='utf-8') as f:
                json.load(f)
        except (json.JSONDecodeError, Exception):
            return False
        
        return True