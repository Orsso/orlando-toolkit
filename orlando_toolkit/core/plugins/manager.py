from __future__ import annotations

"""Plugin management system for installation, removal, and updates.

Provides the PluginManager class that handles the complete lifecycle of
plugin management including downloading from GitHub repositories, installing
dependencies, validating plugins, and managing the local plugin directory.
"""

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
import subprocess
import sys

from .loader import PluginLoader, PluginInfo, get_user_plugins_dir
from .downloader import GitHubPluginDownloader
from .installer import PluginInstaller
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
        self._plugins_dir = get_user_plugins_dir()
        self._downloader = GitHubPluginDownloader()
        self._installer = PluginInstaller()
        self._logger = logging.getLogger(f"{__name__}.PluginManager")
        
        # Ensure plugins directory exists
        self._plugins_dir.mkdir(parents=True, exist_ok=True)
    
    # -------------------------------------------------------------------------
    # Plugin Installation
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
            
            # Refresh plugin loader if available
            if self.plugin_loader:
                try:
                    self.plugin_loader.discover_plugins()
                    result.add_warning("Plugin loader refreshed - restart may be required for full activation")
                except Exception as e:
                    result.add_warning(f"Failed to refresh plugin loader: {e}")
            
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
            List of plugin identifiers
        """
        if not self._plugins_dir.exists():
            return []
        
        plugins = []
        for item in self._plugins_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                # Check if it has plugin.json
                if (item / "plugin.json").exists():
                    plugins.append(item.name)
        
        return sorted(plugins)
    
    def get_plugin_metadata(self, plugin_id: str) -> Optional[PluginMetadata]:
        """Get metadata for an installed plugin.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            PluginMetadata or None if not found
        """
        return self._get_installed_plugin_metadata(plugin_id)
    
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
    # Statistics and Information
    # -------------------------------------------------------------------------
    
    def get_manager_stats(self) -> Dict[str, Any]:
        """Get plugin manager statistics.
        
        Returns:
            Dictionary with manager statistics
        """
        installed_plugins = self.get_installed_plugins()
        
        stats = {
            "plugins_directory": str(self._plugins_dir),
            "installed_plugins_count": len(installed_plugins),
            "installed_plugins": installed_plugins
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