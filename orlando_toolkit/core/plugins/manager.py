from __future__ import annotations

"""Plugin management system for installation, removal, and updates.

Provides the PluginManager class that handles the complete lifecycle of
plugin management including downloading from GitHub repositories, installing
dependencies, validating plugins, and managing the local plugin directory.
"""

import json
import logging
import shutil
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
import subprocess
import sys

from .loader import PluginLoader, PluginInfo, get_user_plugins_dir
from .downloader import GitHubPluginDownloader
from .installer import PluginInstaller
from .github_fetcher import GitHubMetadataFetcher
from .metadata import validate_plugin_metadata, PluginMetadata
from .exceptions import (
    PluginError,
    PluginInstallationError,
    PluginValidationError,
    PluginDependencyError,
    PluginRemovalError
)

logger = logging.getLogger(__name__)


class PluginInstallResult:
    """Result of a plugin installation operation."""
    
    def __init__(self, plugin_id: str, success: bool, message: str = "",
                 warnings: Optional[List[str]] = None, metadata: Optional[PluginMetadata] = None):
        self.plugin_id = plugin_id
        self.success = success
        self.message = message
        self.warnings = warnings or []
        self.metadata = metadata
    
    def add_warning(self, warning: str) -> None:
        """Add a warning to the result."""
        self.warnings.append(warning)
    
    def __str__(self) -> str:
        status = "SUCCESS" if self.success else "FAILED"
        return f"[{status}] {self.plugin_id}: {self.message}"


class PluginManager:
    """Plugin installation and management system.
    
    Provides comprehensive plugin management including:
    - Installation from GitHub repositories
    - Dependency management using pip
    - Plugin validation and safety checks
    - Plugin removal and cleanup
    - Update detection and management
    - Integration with plugin loader
    """
    
    def __init__(self, plugin_loader: Optional[PluginLoader] = None):
        """Initialize plugin manager.
        
        Args:
            plugin_loader: Optional PluginLoader instance for integration
        """
        self.plugin_loader = plugin_loader
        
        # Check if we're in dev mode by examining the plugin loader
        self._dev_mode = (plugin_loader and hasattr(plugin_loader, '_dev_mode') and plugin_loader._dev_mode)
        
        if self._dev_mode:
            # Dev mode: use local plugins directory
            self._plugins_dir = Path.cwd().parent / 'plugins'
            # Dev mode state files go in the dev plugins directory
            self._state_file = self._plugins_dir / ".dev_plugin_states.json"
            self._fetched_file = self._plugins_dir / ".dev_fetched_plugins.json"
            self._logger = logging.getLogger(f"{__name__}.PluginManager[DEV]")
            self._logger.info("DEV MODE: Using dev plugin management in %s", self._plugins_dir)
        else:
            # Production mode: use user plugins directory
            self._plugins_dir = get_user_plugins_dir()
            self._state_file = self._plugins_dir.parent / "plugin_states.json"
            self._fetched_file = self._plugins_dir.parent / "fetched_plugins.json"
            self._logger = logging.getLogger(f"{__name__}.PluginManager")
        
        self._downloader = GitHubPluginDownloader()
        self._installer = PluginInstaller()
        self._github_fetcher = GitHubMetadataFetcher()
        
        # Ensure plugins directory exists
        self._plugins_dir.mkdir(parents=True, exist_ok=True)
        
        self._logger.debug("Plugin state file: %s", self._state_file)
        self._logger.debug("Fetched plugins file: %s", self._fetched_file)
        
        # Fetched plugins support
        self._fetched_plugins = {}
        self._load_fetched_plugins()
    
    # -------------------------------------------------------------------------
    # Plugin State Persistence
    # -------------------------------------------------------------------------
    
    def load_plugin_states(self) -> Dict[str, bool]:
        """Load plugin activation states from disk.
        
        Returns:
            Dictionary mapping plugin_id -> is_active
        """
        try:
            if self._state_file.exists():
                with open(self._state_file, 'r') as f:
                    states = json.load(f)
                    self._logger.debug("Loaded plugin states: %s", states)
                    return states
            else:
                self._logger.debug("No plugin state file found at: %s", self._state_file)
        except Exception as e:
            self._logger.warning("Failed to load plugin states: %s", e)
        return {}
    
    def save_plugin_states(self) -> None:
        """Save current plugin activation states to disk."""
        try:
            if not self.plugin_loader:
                return
                
            states = {}
            for plugin_id in self.plugin_loader.get_all_plugins().keys():
                states[plugin_id] = self.is_plugin_active(plugin_id)
            
            # Ensure parent directory exists
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self._state_file, 'w') as f:
                json.dump(states, f, indent=2)
                
            self._logger.debug("Saved plugin states to %s: %s", self._state_file, states)
                
        except Exception as e:
            self._logger.error("Failed to save plugin states: %s", e)
    
    def restore_plugin_states(self) -> None:
        """Restore plugin activation states from saved state."""
        if not self.plugin_loader:
            return
            
        saved_states = self.load_plugin_states()
        for plugin_id, should_be_active in saved_states.items():
            if should_be_active and not self.is_plugin_active(plugin_id):
                try:
                    self.plugin_loader.activate_plugin(plugin_id)
                    self._logger.info("Restored plugin activation: %s", plugin_id)
                except Exception as e:
                    self._logger.error("Failed to restore plugin %s: %s", plugin_id, e)
    
    # -------------------------------------------------------------------------
    # Two-Phase Plugin Installation (Fetch → Install)
    # -------------------------------------------------------------------------

    def add_plugin_from_github(self, repo_url: str) -> dict:
        """Fetch plugin metadata and image from GitHub (does not install).
        
        Args:
            repo_url: GitHub repository URL
            
        Returns:
            dict: Result with format:
                {
                    "success": bool,
                    "message": str,
                    "plugin_info": {
                        "name": str,
                        "version": str,
                        "description": str,
                        "has_image": bool
                    } or None
                }
        """
        self._logger.info("Fetching plugin metadata from: %s", repo_url)
        
        try:
            # Fetch plugin info using GitHub fetcher
            result = self._github_fetcher.fetch_plugin_info(repo_url)
            
            if result.get("error"):
                return {
                    "success": False,
                    "message": f"Failed to fetch plugin: {result['error']}",
                    "plugin_info": None
                }
            
            metadata = result["metadata"]
            
            # Store fetched plugin info (overwrite if already exists)
            self._fetched_plugins[repo_url] = {
                "metadata": metadata,
                "image_data": result.get("image_data"),
                "has_image": result.get("has_image", False),
                "fetch_time": str(int(time.time())),  # Simple timestamp
                # Official flag removed; UI is the source of truth
            }
            
            # Save to JSON file
            self._save_fetched_plugins()
            
            return {
                "success": True,
                "message": f"Plugin '{metadata['name']}' ready to install",
                "plugin_info": {
                    "name": metadata["name"],
                    "version": metadata["version"],
                    "description": metadata.get("description", ""),
                    "has_image": result.get("has_image", False)
                }
            }
            
        except Exception as e:
            self._logger.error("Failed to fetch plugin %s: %s", repo_url, e)
            return {
                "success": False,
                "message": f"Error fetching plugin: {e}",
                "plugin_info": None
            }
    
    def get_fetched_plugins(self) -> dict:
        """Return all fetched but not installed plugins.
        
        Returns:
            dict: Mapping of repo_url -> plugin_info
        """
        return self._fetched_plugins.copy()
    
    def install_fetched_plugin(self, repo_url: str) -> PluginInstallResult:
        """Install a previously fetched plugin.
        
        Args:
            repo_url: GitHub repository URL of fetched plugin
            
        Returns:
            PluginInstallResult with installation status
        """
        if repo_url not in self._fetched_plugins:
            return PluginInstallResult(
                plugin_id="unknown",
                success=False,
                message="Plugin not found in fetched plugins"
            )
        
        # Get fetched plugin info
        fetched_info = self._fetched_plugins[repo_url]
        metadata = fetched_info["metadata"]
        
        self._logger.info("Installing fetched plugin: %s v%s", 
                         metadata["name"], metadata["version"])
        
        # Use existing installation logic
        result = self.install_plugin_from_github(repo_url)
        
        # Remove from fetched plugins if installation successful
        if result.success:
            del self._fetched_plugins[repo_url]
            self._save_fetched_plugins()
            self._logger.info("Removed installed plugin from fetched list: %s", repo_url)
        
        return result
    
    def _load_fetched_plugins(self) -> None:
        """Load fetched plugins from JSON file."""
        try:
            if self._fetched_file.exists():
                with open(self._fetched_file, 'r') as f:
                    data = json.load(f)
                    # Convert base64 back to bytes for image data
                    import base64
                    for url, info in data.items():
                        if info.get("image_data") and isinstance(info["image_data"], str):
                            info["image_data"] = base64.b64decode(info["image_data"])
                    
                    self._fetched_plugins = data
                    self._logger.debug("Loaded %d fetched plugins", len(self._fetched_plugins))
            else:
                self._logger.debug("No fetched plugins file found, starting empty")
        except Exception as e:
            self._logger.error("Failed to load fetched plugins: %s", e)
            self._fetched_plugins = {}
    
    def _save_fetched_plugins(self) -> None:
        """Save fetched plugins to JSON file."""
        try:
            with open(self._fetched_file, 'w') as f:
                # Convert image bytes to base64 for JSON serialization
                serializable_data = {}
                for url, info in self._fetched_plugins.items():
                    serializable_info = info.copy()
                    if info.get("image_data"):
                        import base64
                        serializable_info["image_data"] = base64.b64encode(info["image_data"]).decode('utf-8')
                    serializable_data[url] = serializable_info
                
                json.dump(serializable_data, f, indent=2)
                self._logger.debug("Saved %d fetched plugins", len(self._fetched_plugins))
        except Exception as e:
            self._logger.error("Failed to save fetched plugins: %s", e)
    
    # -------------------------------------------------------------------------
    # Plugin Installation (Legacy/Direct)
    # -------------------------------------------------------------------------
    
    def install_plugin_from_github(self, repository_url: str, 
                                 branch: str = "main") -> PluginInstallResult:
        """Install a plugin from a GitHub repository.
        
        Args:
            repository_url: GitHub repository URL
            branch: Branch to install from (default: "main")
            
        Returns:
            PluginInstallResult with installation status and metadata
        """
        self._logger.info("Installing plugin from GitHub: %s (branch: %s)", 
                         repository_url, branch)
        
        temp_dir = None
        try:
            # Create temporary directory for download
            temp_dir = Path(tempfile.mkdtemp(prefix="orlando_plugin_"))
            
            # Download plugin from GitHub
            self._logger.debug("Downloading plugin archive...")
            download_result = self._downloader.download_repository(
                repository_url, branch, temp_dir
            )
            
            if not download_result.success:
                return PluginInstallResult(
                    plugin_id="unknown",
                    success=False,
                    message=f"Download failed: {download_result.message}"
                )
            
            # Validate plugin structure and metadata
            plugin_dir = download_result.extracted_path
            self._logger.debug("Validating plugin metadata...")
            
            try:
                metadata_file = plugin_dir / "plugin.json"
                metadata = validate_plugin_metadata(metadata_file, plugin_dir)
            except PluginValidationError as e:
                return PluginInstallResult(
                    plugin_id="unknown",
                    success=False,
                    message=f"Plugin validation failed: {e}"
                )
            
            # Check if plugin is already installed
            target_dir = self._plugins_dir / metadata.name
            if target_dir.exists():
                existing_metadata = self._get_installed_plugin_metadata(metadata.name)
                if existing_metadata:
                    if existing_metadata.version == metadata.version:
                        return PluginInstallResult(
                            plugin_id=metadata.name,
                            success=False,
                            message=f"Plugin {metadata.name} v{metadata.version} is already installed"
                        )
                    else:
                        # This is an update - remove old version first
                        self._logger.info("Updating plugin %s from v%s to v%s",
                                        metadata.name, existing_metadata.version, metadata.version)
                        self._remove_plugin_directory(metadata.name)
            
            # Install dependencies if specified
            if metadata.dependencies and metadata.dependencies.get("packages"):
                self._logger.debug("Installing plugin dependencies...")
                dep_result = self._install_dependencies(plugin_dir, metadata)
                if not dep_result:
                    return PluginInstallResult(
                        plugin_id=metadata.name,
                        success=False,
                        message="Failed to install plugin dependencies"
                    )
            
            # Move plugin to final location
            self._logger.debug("Installing plugin to %s...", target_dir)
            shutil.copytree(plugin_dir, target_dir)
            
            # Create installation success result
            result = PluginInstallResult(
                plugin_id=metadata.name,
                success=True,
                message=f"Plugin {metadata.name} v{metadata.version} installed successfully",
                metadata=metadata
            )
            
            # Refresh plugin loader if available, preserving activation states
            if self.plugin_loader:
                try:
                    # Capture currently active plugin IDs before discovery
                    previously_active = set(self.get_active_plugin_ids())

                    # Proactively clear registrations for previously-active plugins to avoid stale conflicts
                    for pid in previously_active:
                        try:
                            self.service_registry.unregister_plugin_services(pid)
                        except Exception:
                            pass
                        try:
                            if self.plugin_loader.app_context and getattr(self.plugin_loader.app_context, 'ui_registry', None):
                                self.plugin_loader.app_context.ui_registry.cleanup_plugin_components(pid)
                        except Exception:
                            pass

                    # Rediscover plugins (updates metadata, may update internal maps)
                    self.plugin_loader.discover_plugins()

                    # Restore activation state only for plugins that lost ACTIVE state
                    for pid in previously_active:
                        try:
                            info = self.plugin_loader.get_plugin_info(pid)
                            if info is None:
                                continue
                            if info.is_active():
                                continue  # Already active, do not re-activate
                            self.plugin_loader.activate_plugin(pid)
                        except Exception:
                            # Non-fatal: keep going for other plugins
                            pass

                    # Persist states after restoration
                    self.save_plugin_states()
                    result.add_warning("Plugin loader refreshed and previous activation states restored")
                except Exception as e:
                    result.add_warning(f"Failed to refresh/restore plugin loader state: {e}")
            
            self._logger.info("Plugin installation completed successfully: %s", metadata.name)
            return result
            
        except Exception as e:
            self._logger.error("Unexpected error during plugin installation: %s", e)
            return PluginInstallResult(
                plugin_id="unknown",
                success=False,
                message=f"Installation failed: {e}"
            )
        finally:
            # Cleanup temporary directory
            if temp_dir and temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    self._logger.warning("Failed to cleanup temporary directory %s: %s", 
                                       temp_dir, e)
    
    def install_plugin_from_directory(self, source_dir: Path) -> PluginInstallResult:
        """Install a plugin from a local directory.
        
        Args:
            source_dir: Path to plugin directory
            
        Returns:
            PluginInstallResult with installation status
        """
        self._logger.info("Installing plugin from directory: %s", source_dir)
        
        try:
            # Validate plugin structure and metadata
            metadata_file = source_dir / "plugin.json"
            metadata = validate_plugin_metadata(metadata_file, source_dir)
            
            # Check if plugin is already installed
            target_dir = self._plugins_dir / metadata.name
            if target_dir.exists():
                return PluginInstallResult(
                    plugin_id=metadata.name,
                    success=False,
                    message=f"Plugin {metadata.name} is already installed"
                )
            
            # Install dependencies if specified
            if metadata.dependencies and metadata.dependencies.get("packages"):
                dep_result = self._install_dependencies(source_dir, metadata)
                if not dep_result:
                    return PluginInstallResult(
                        plugin_id=metadata.name,
                        success=False,
                        message="Failed to install plugin dependencies"
                    )
            
            # Copy plugin to final location
            shutil.copytree(source_dir, target_dir)
            
            result = PluginInstallResult(
                plugin_id=metadata.name,
                success=True,
                message=f"Plugin {metadata.name} v{metadata.version} installed successfully",
                metadata=metadata
            )
            
            # Refresh plugin loader if available
            if self.plugin_loader:
                try:
                    self.plugin_loader.discover_plugins()
                    result.add_warning("Plugin loader refreshed")
                except Exception as e:
                    result.add_warning(f"Failed to refresh plugin loader: {e}")
            
            return result
            
        except PluginValidationError as e:
            return PluginInstallResult(
                plugin_id="unknown",
                success=False,
                message=f"Plugin validation failed: {e}"
            )
        except Exception as e:
            self._logger.error("Unexpected error during plugin installation: %s", e)
            return PluginInstallResult(
                plugin_id="unknown",
                success=False,
                message=f"Installation failed: {e}"
            )
    
    # -------------------------------------------------------------------------
    # Plugin Removal
    # -------------------------------------------------------------------------
    
    def remove_plugin(self, plugin_id: str, force: bool = False) -> bool:
        """Remove an installed plugin.
        
        Args:
            plugin_id: Plugin identifier to remove
            force: Force removal even if plugin is active
            
        Returns:
            True if plugin was removed successfully
            
        Raises:
            PluginRemovalError: If removal fails
        """
        self._logger.info("Removing plugin: %s (force: %s)", plugin_id, force)
        
        plugin_dir = self._plugins_dir / plugin_id
        if not plugin_dir.exists():
            self._logger.warning("Plugin directory not found: %s", plugin_id)
            return False
        
        try:
            # Check if plugin is active and deactivate if needed
            if self.plugin_loader:
                plugin_info = self.plugin_loader.get_plugin_info(plugin_id)
                if plugin_info and plugin_info.is_active():
                    if not force:
                        raise PluginRemovalError(
                            f"Plugin {plugin_id} is active. Use force=True to remove anyway."
                        )
                    
                    # Deactivate and unload plugin
                    self._logger.debug("Deactivating plugin before removal: %s", plugin_id)
                    self.plugin_loader.deactivate_plugin(plugin_id)
                    self.plugin_loader.unload_plugin(plugin_id)
            
            # Remove plugin directory
            self._remove_plugin_directory(plugin_id)
            
            self._logger.info("Plugin removed successfully: %s", plugin_id)
            return True
            
        except Exception as e:
            self._logger.error("Failed to remove plugin %s: %s", plugin_id, e)
            raise PluginRemovalError(f"Failed to remove plugin {plugin_id}: {e}")
    
    def _remove_plugin_directory(self, plugin_id: str) -> None:
        """Remove plugin directory and all contents."""
        plugin_dir = self._plugins_dir / plugin_id
        if plugin_dir.exists():
            try:
                shutil.rmtree(plugin_dir)
                self._logger.debug("Removed plugin directory: %s", plugin_dir)
            except Exception as e:
                self._logger.error("Failed to remove plugin directory %s: %s", plugin_dir, e)
                raise
    
    # -------------------------------------------------------------------------
    # Plugin Updates
    # -------------------------------------------------------------------------
    
    def check_for_updates(self, plugin_id: Optional[str] = None) -> Dict[str, Dict[str, str]]:
        """Check for available plugin updates.
        
        Args:
            plugin_id: Check specific plugin, or None for all plugins
            
        Returns:
            Dictionary mapping plugin_id to update information
        """
        updates = {}
        
        if plugin_id:
            plugins_to_check = [plugin_id]
        else:
            plugins_to_check = self.get_installed_plugins()
        
        for p_id in plugins_to_check:
            try:
                update_info = self._check_plugin_update(p_id)
                if update_info:
                    updates[p_id] = update_info
            except Exception as e:
                self._logger.error("Failed to check updates for plugin %s: %s", p_id, e)
        
        return updates
    
    def _check_plugin_update(self, plugin_id: str) -> Optional[Dict[str, str]]:
        """Check if a plugin has available updates.
        
        Args:
            plugin_id: Plugin to check
            
        Returns:
            Update information or None if no update available
        """
        # This is a placeholder implementation
        # In a real implementation, you would:
        # 1. Get plugin's repository URL from metadata
        # 2. Check GitHub API for latest release/commit
        # 3. Compare with installed version
        
        # For now, return None (no updates)
        return None
    
    def update_plugin(self, plugin_id: str, force: bool = False) -> PluginInstallResult:
        """Update an installed plugin to the latest version.
        
        Args:
            plugin_id: Plugin to update
            force: Force update even if no newer version detected
            
        Returns:
            PluginInstallResult with update status
        """
        self._logger.info("Updating plugin: %s", plugin_id)
        
        # Get current plugin metadata
        metadata = self._get_installed_plugin_metadata(plugin_id)
        if not metadata:
            return PluginInstallResult(
                plugin_id=plugin_id,
                success=False,
                message=f"Plugin {plugin_id} is not installed"
            )
        
        # For now, return not implemented
        # In a real implementation, you would:
        # 1. Check for available updates
        # 2. Download new version
        # 3. Remove old version
        # 4. Install new version
        
        return PluginInstallResult(
            plugin_id=plugin_id,
            success=False,
            message="Plugin updates not yet implemented"
        )
    
    # -------------------------------------------------------------------------
    # Dependency Management
    # -------------------------------------------------------------------------
    
    def _install_dependencies(self, plugin_dir: Path, metadata: PluginMetadata) -> bool:
        """Install plugin dependencies using pip.
        
        Args:
            plugin_dir: Plugin directory containing requirements.txt
            metadata: Plugin metadata
            
        Returns:
            True if dependencies installed successfully
        """
        requirements_file = plugin_dir / "requirements.txt"
        
        if not requirements_file.exists():
            self._logger.warning("Plugin %s specifies dependencies but no requirements.txt found",
                               metadata.name)
            return True  # Continue installation - dependencies might be optional
        
        try:
            # Install dependencies using the same Python environment
            cmd = [
                sys.executable, "-m", "pip", "install", 
                "-r", str(requirements_file),
                "--quiet"  # Reduce output noise
            ]
            
            self._logger.debug("Installing dependencies: %s", " ".join(cmd))
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                self._logger.error("Failed to install dependencies for plugin %s: %s",
                                 metadata.name, result.stderr)
                return False
            
            self._logger.debug("Dependencies installed successfully for plugin %s", metadata.name)
            return True
            
        except Exception as e:
            self._logger.error("Exception while installing dependencies for plugin %s: %s",
                             metadata.name, e)
            return False
    
    # -------------------------------------------------------------------------
    # Plugin Information
    # -------------------------------------------------------------------------
    
    def get_installed_plugins(self) -> List[str]:
        """Get list of installed plugin IDs.
        
        Returns:
            List of plugin identifiers (from JSON "name" field, not directory names)
        """
        if not self._plugins_dir.exists():
            return []
        
        plugins = []
        for item in self._plugins_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                # Check if it has plugin.json
                if (item / "plugin.json").exists():
                    try:
                        # Get the actual plugin ID from the JSON "name" field
                        metadata = self._get_installed_plugin_metadata(item.name)
                        if metadata:
                            plugins.append(metadata.name)  # Use JSON "name", not directory name
                        else:
                            # Fallback to directory name if metadata can't be read
                            plugins.append(item.name)
                    except Exception:
                        # Fallback to directory name if there's any error
                        plugins.append(item.name)
        
        return sorted(plugins)
    
    def get_plugin_metadata(self, plugin_id: str) -> Optional[PluginMetadata]:
        """Get metadata for an installed plugin.
        
        Args:
            plugin_id: Plugin identifier (from JSON "name" field)
            
        Returns:
            PluginMetadata or None if not found
        """
        # First try plugin_loader if available (works for loaded plugins)
        if self.plugin_loader:
            plugin_info = self.plugin_loader.get_plugin_info(plugin_id)
            if plugin_info:
                return plugin_info.metadata
        
        # Fallback: scan directories to find the one with matching plugin_id
        if not self._plugins_dir.exists():
            return None
            
        for item in self._plugins_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                if (item / "plugin.json").exists():
                    try:
                        metadata = self._get_installed_plugin_metadata(item.name)  # item.name = directory
                        if metadata and metadata.name == plugin_id:  # metadata.name = JSON "name" field
                            return metadata
                    except Exception:
                        continue
        
        return None
    
    def _get_installed_plugin_metadata(self, plugin_id: str) -> Optional[PluginMetadata]:
        """Internal method to get plugin metadata."""
        plugin_dir = self._plugins_dir / plugin_id
        metadata_file = plugin_dir / "plugin.json"
        
        if not metadata_file.exists():
            return None
        
        try:
            return validate_plugin_metadata(metadata_file, plugin_dir)
        except Exception as e:
            self._logger.error("Failed to load metadata for plugin %s: %s", plugin_id, e)
            return None
    
    def is_plugin_installed(self, plugin_id: str) -> bool:
        """Check if a plugin is installed.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            True if plugin is installed
        """
        plugin_dir = self._plugins_dir / plugin_id
        return plugin_dir.exists() and (plugin_dir / "plugin.json").exists()
    
    def get_installation_status(self, plugin_id: str) -> Dict[str, Any]:
        """Get detailed installation status for a plugin.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            Dictionary with status information
        """
        status = {
            "installed": self.is_plugin_installed(plugin_id),
            "loaded": False,
            "active": False,
            "error": None
        }
        
        if self.plugin_loader:
            plugin_info = self.plugin_loader.get_plugin_info(plugin_id)
            if plugin_info:
                status["loaded"] = plugin_info.is_loaded()
                status["active"] = plugin_info.is_active()
                if plugin_info.load_error:
                    status["error"] = str(plugin_info.load_error)
        
        return status
    
    # -------------------------------------------------------------------------
    # Validation and Safety
    # -------------------------------------------------------------------------
    
    def validate_plugin_safety(self, plugin_dir: Path) -> List[str]:
        """Validate plugin for safety and security issues.
        
        Args:
            plugin_dir: Plugin directory to validate
            
        Returns:
            List of safety warnings (empty if safe)
        """
        warnings = []
        
        # Check for suspicious files
        suspicious_files = [
            "*.exe", "*.bat", "*.sh", "*.ps1", "*.cmd",
            "*.dll", "*.so", "*.dylib"
        ]
        
        for pattern in suspicious_files:
            if list(plugin_dir.glob(pattern)):
                warnings.append(f"Plugin contains potentially dangerous files: {pattern}")
        
        # Check plugin metadata for suspicious permissions
        try:
            metadata_file = plugin_dir / "plugin.json"
            metadata = validate_plugin_metadata(metadata_file, plugin_dir)
            
            # Check for network access permission
            if metadata.requires_permission("network_access"):
                warnings.append("Plugin requests network access - review carefully")
            
            # Check for file system write permission
            if metadata.requires_permission("file_system_write"):
                warnings.append("Plugin requests file system write access")
                
        except Exception:
            warnings.append("Could not validate plugin metadata for security")
        
        return warnings
    
    # -------------------------------------------------------------------------
    # Service Lifecycle Management
    # -------------------------------------------------------------------------
    
    def is_plugin_active(self, plugin_id: str) -> bool:
        """Check if a plugin is currently active.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            True if plugin is active, False otherwise
        """
        if not self.plugin_loader:
            return False
        
        try:
            # Plugin is active if it's in ACTIVE state (single source of truth)
            plugin_info = self.plugin_loader.get_plugin_info(plugin_id)
            
            if plugin_info is None:
                return False
            
            # Check both state and instance for consistency
            return plugin_info.is_active() and plugin_info.instance is not None
            
        except Exception as e:
            self._logger.warning("Error checking plugin status %s: %s", plugin_id, e)
            return False
    
    def get_active_plugin_ids(self) -> List[str]:
        """Get list of currently active plugin IDs.
        
        Returns:
            List of active plugin identifiers
        """
        if not self.plugin_loader:
            return []
        
        try:
            loaded_plugins = self.plugin_loader.get_loaded_plugins()
            active_plugins = []
            
            for plugin_info in loaded_plugins:
                # Use the correct attribute name 'instance' (not 'plugin_instance')
                if plugin_info.instance and self.is_plugin_active(plugin_info.plugin_id):
                    active_plugins.append(plugin_info.plugin_id)
            
            return active_plugins
            
        except Exception as e:
            self._logger.warning("Error getting active plugins: %s", e)
            return []
    
    def get_active_pipeline_plugins(self) -> List[Dict[str, Any]]:
        """Get list of active pipeline plugins with their configuration.
        
        Returns:
            List of active pipeline plugin configurations
        """
        active_plugins = []
        
        try:
            active_ids = self.get_active_plugin_ids()
            
            for plugin_id in active_ids:
                if self.plugin_loader:
                    loaded_plugins = self.plugin_loader.get_loaded_plugins()
                    
                    # Find matching plugin info
                    plugin_info = None
                    for plugin in loaded_plugins:
                        if plugin.plugin_id == plugin_id:
                            plugin_info = plugin
                            break
                    
                    if plugin_info and plugin_info.metadata and plugin_info.metadata.category == "pipeline":
                        # Build plugin configuration for splash screen
                        config = {
                            'plugin_id': plugin_id,
                            'display_name': plugin_info.metadata.display_name,
                            'description': plugin_info.metadata.description,
                            'button_text': getattr(plugin_info.metadata, 'ui', {}).get('splash_button', {}).get('text', plugin_info.metadata.display_name),
                            'icon': getattr(plugin_info.metadata, 'ui', {}).get('splash_button', {}).get('icon', 'default-plugin-icon.png'),
                            'tooltip': getattr(plugin_info.metadata, 'ui', {}).get('splash_button', {}).get('tooltip', plugin_info.metadata.description)
                        }
                        active_plugins.append(config)
            
            return active_plugins
            
        except Exception as e:
            self._logger.warning("Error getting active pipeline plugins: %s", e)
            return []
    
    def activate_plugin(self, plugin_id: str) -> bool:
        """Activate a plugin by loading and registering its services.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            True if plugin was successfully activated
        """
        try:
            if self.is_plugin_active(plugin_id):
                self._logger.debug("Plugin %s is already active", plugin_id)
                return True
            
            # Activate plugin (this will load it first if needed)
            if self.plugin_loader:
                success = self.plugin_loader.activate_plugin(plugin_id)
                if not success:
                    self._logger.error("Failed to activate plugin %s", plugin_id)
                    return False
                
                self._logger.info("Plugin %s activated successfully", plugin_id)
                self.save_plugin_states()
                return True
            
            return False
            
        except Exception as e:
            self._logger.error("Error activating plugin %s: %s", plugin_id, e)
            return False
    
    def deactivate_plugin(self, plugin_id: str) -> bool:
        """Deactivate a plugin by unloading it and cleaning up services.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            True if plugin was successfully deactivated
        """
        try:
            if not self.is_plugin_active(plugin_id):
                self._logger.debug("Plugin %s is not active", plugin_id)
                return True
            
            # Deactivate plugin (keeps it loaded but inactive)
            if self.plugin_loader:
                success = self.plugin_loader.deactivate_plugin(plugin_id)
                if success:
                    self._logger.info("Plugin %s deactivated successfully", plugin_id)
                    self.save_plugin_states()
                else:
                    self._logger.warning("Failed to cleanly deactivate plugin %s", plugin_id)
                
                return success
            
            return False
            
        except Exception as e:
            self._logger.error("Error deactivating plugin %s: %s", plugin_id, e)
            return False
    
    # -------------------------------------------------------------------------
    # Statistics and Information
    # -------------------------------------------------------------------------
    
    def get_manager_stats(self) -> Dict[str, Any]:
        """Get plugin manager statistics.
        
        Returns:
            Dictionary with manager statistics
        """
        installed_plugins = self.get_installed_plugins()
        active_plugins = self.get_active_plugin_ids()
        
        stats = {
            "plugins_directory": str(self._plugins_dir),
            "installed_plugins_count": len(installed_plugins),
            "installed_plugins": installed_plugins,
            "active_plugins_count": len(active_plugins),
            "active_plugins": active_plugins
        }
        
        if self.plugin_loader:
            loader_stats = self.plugin_loader.get_loader_stats()
            stats.update(loader_stats)
        
        return stats


# Custom exceptions for plugin management
class PluginInstallationError(PluginError):
    """Raised when plugin installation fails."""
    pass


class PluginRemovalError(PluginError):
    """Raised when plugin removal fails.""" 
    pass