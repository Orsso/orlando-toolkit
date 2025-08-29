from __future__ import annotations

"""Plugin installation and dependency management.

Provides the PluginInstaller class that handles the installation workflow
for Orlando Toolkit plugins including dependency resolution, file copying,
validation, and cleanup operations.
"""

import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
import tempfile

from .metadata import PluginMetadata, validate_plugin_metadata
from .exceptions import (
    PluginInstallationError,
    PluginDependencyError,
    PluginValidationError
)

logger = logging.getLogger(__name__)


class InstallationContext:
    """Context information for plugin installation."""
    
    def __init__(self, plugin_dir: Path, target_dir: Path, metadata: PluginMetadata):
        self.plugin_dir = plugin_dir
        self.target_dir = target_dir
        self.metadata = metadata
        self.temp_dirs: List[Path] = []
        self.installed_dependencies: List[str] = []
        self.backup_dir: Optional[Path] = None
        self.success = False
    
    def add_temp_dir(self, temp_dir: Path) -> None:
        """Add temporary directory for cleanup."""
        self.temp_dirs.append(temp_dir)
    
    def cleanup_temp_dirs(self) -> None:
        """Clean up temporary directories."""
        for temp_dir in self.temp_dirs:
            if temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    logger.warning("Failed to cleanup temp directory %s: %s", temp_dir, e)
        self.temp_dirs.clear()


class PluginInstaller:
    """Plugin installation workflow manager.
    
    Handles the complete installation process including:
    - File validation and structure checks
    - Dependency installation using pip
    - Plugin file copying and organization
    - Rollback on installation failure
    - Security and safety validation
    """
    
    def __init__(self):
        self._logger = logging.getLogger(f"{__name__}.PluginInstaller")
        
        # Installation options
        self._pip_timeout = 300  # 5 minutes for dependency installation
        self._backup_existing = True
        self._validate_before_install = True
    
    # -------------------------------------------------------------------------
    # Public Installation API
    # -------------------------------------------------------------------------
    
    def install_plugin(self, plugin_dir: Path, target_dir: Path, 
                      force: bool = False) -> Dict[str, Any]:
        """Install a plugin from source directory to target directory.
        
        Args:
            plugin_dir: Source plugin directory
            target_dir: Target installation directory  
            force: Force installation even if target exists
            
        Returns:
            Dictionary with installation result and metadata
        """
        self._logger.info("Installing plugin from %s to %s", plugin_dir, target_dir)
        
        try:
            # Validate plugin structure and metadata
            metadata = self._validate_plugin_for_installation(plugin_dir)
            
            # Create installation context
            context = InstallationContext(plugin_dir, target_dir, metadata)
            
            # Check if target already exists
            if target_dir.exists() and not force:
                if self._is_same_plugin_version(target_dir, metadata):
                    return self._create_result(False, f"Plugin {metadata.name} v{metadata.version} is already installed")
                else:
                    # Different version - backup existing
                    context.backup_dir = self._create_backup(target_dir)
            
            # Perform installation steps
            try:
                # Step 1: Install dependencies
                if not self._install_dependencies(context):
                    raise PluginInstallationError("Failed to install plugin dependencies")
                
                # Step 2: Validate plugin safety
                if self._validate_before_install:
                    safety_issues = self._validate_plugin_safety(context)
                    if safety_issues:
                        self._logger.warning("Plugin safety issues detected: %s", safety_issues)
                        if not force:
                            raise PluginInstallationError(f"Plugin safety validation failed: {safety_issues}")
                
                # Step 3: Copy plugin files
                if not self._copy_plugin_files(context):
                    raise PluginInstallationError("Failed to copy plugin files")
                
                # Step 4: Finalize installation
                self._finalize_installation(context)
                
                context.success = True
                self._logger.info("Plugin installation completed successfully: %s v%s", 
                                metadata.name, metadata.version)
                
                return self._create_result(True, f"Plugin {metadata.name} v{metadata.version} installed successfully", 
                                         metadata=metadata)
                
            except Exception as e:
                # Installation failed - perform rollback
                self._logger.error("Plugin installation failed, performing rollback: %s", e)
                self._rollback_installation(context)
                raise
                
        except PluginValidationError as e:
            return self._create_result(False, f"Plugin validation failed: {e}")
        except PluginInstallationError as e:
            return self._create_result(False, str(e))
        except Exception as e:
            self._logger.error("Unexpected error during plugin installation: %s", e)
            return self._create_result(False, f"Installation failed: {e}")
        finally:
            # Always cleanup temporary resources
            if 'context' in locals():
                context.cleanup_temp_dirs()
    
    def uninstall_plugin(self, target_dir: Path, keep_config: bool = True) -> Dict[str, Any]:
        """Uninstall a plugin from the target directory.
        
        Args:
            target_dir: Plugin installation directory
            keep_config: Whether to preserve configuration files
            
        Returns:
            Dictionary with uninstallation result
        """
        self._logger.info("Uninstalling plugin from %s", target_dir)
        
        try:
            if not target_dir.exists():
                return self._create_result(True, "Plugin directory does not exist")
            
            # Get plugin metadata before removal
            metadata = None
            try:
                metadata_file = target_dir / "plugin.json"
                if metadata_file.exists():
                    metadata = validate_plugin_metadata(metadata_file, target_dir)
            except Exception:
                pass  # Continue even if metadata can't be loaded
            
            # Remove plugin directory
            shutil.rmtree(target_dir)
            
            plugin_name = metadata.name if metadata else target_dir.name
            self._logger.info("Plugin uninstalled successfully: %s", plugin_name)
            
            return self._create_result(True, f"Plugin {plugin_name} uninstalled successfully")
            
        except Exception as e:
            self._logger.error("Failed to uninstall plugin: %s", e)
            return self._create_result(False, f"Uninstallation failed: {e}")
    
    # -------------------------------------------------------------------------
    # Plugin Validation
    # -------------------------------------------------------------------------
    
    def _validate_plugin_for_installation(self, plugin_dir: Path) -> PluginMetadata:
        """Validate plugin structure and metadata for installation.
        
        Args:
            plugin_dir: Plugin directory to validate
            
        Returns:
            PluginMetadata object
            
        Raises:
            PluginValidationError: If validation fails
        """
        if not plugin_dir.exists() or not plugin_dir.is_dir():
            raise PluginValidationError(f"Plugin directory does not exist: {plugin_dir}")
        
        # Validate plugin.json
        metadata_file = plugin_dir / "plugin.json"
        metadata = validate_plugin_metadata(metadata_file, plugin_dir)
        
        # Additional validation checks
        if metadata.category != "pipeline":
            raise PluginValidationError(f"Unsupported plugin category: {metadata.category}. Only 'pipeline' plugins are supported.")
        
        # Check entry point module exists
        if not self._validate_entry_point_exists(plugin_dir, metadata.entry_point):
            raise PluginValidationError(f"Entry point module not found: {metadata.entry_point}")
        
        return metadata
    
    def _validate_entry_point_exists(self, plugin_dir: Path, entry_point: str) -> bool:
        """Validate that the entry point module exists."""
        try:
            # Convert entry point to module path (e.g., "src.plugin.MyPlugin" -> "src/plugin.py")
            parts = entry_point.split(".")
            if len(parts) < 2:
                return False
            
            # Remove class name, keep module path
            module_parts = parts[:-1]
            module_file = plugin_dir / ("/".join(module_parts) + ".py")
            
            if module_file.exists():
                return True
            
            # Also check for package with __init__.py
            module_dir = plugin_dir / "/".join(module_parts)
            init_file = module_dir / "__init__.py"
            
            return init_file.exists()
            
        except Exception:
            return False
    
    def _validate_plugin_safety(self, context: InstallationContext) -> List[str]:
        """Validate plugin for safety and security issues.
        
        Args:
            context: Installation context
            
        Returns:
            List of safety warnings (empty if safe)
        """
        warnings = []
        plugin_dir = context.plugin_dir
        
        # Check for executable files
        executable_patterns = ["*.exe", "*.bat", "*.cmd", "*.sh", "*.ps1", "*.scr", "*.com"]
        for pattern in executable_patterns:
            if list(plugin_dir.rglob(pattern)):
                warnings.append(f"Plugin contains executable files: {pattern}")
        
        # Check for binary libraries
        library_patterns = ["*.dll", "*.so", "*.dylib"]
        for pattern in library_patterns:
            if list(plugin_dir.rglob(pattern)):
                warnings.append(f"Plugin contains binary libraries: {pattern}")
        
        # Check plugin permissions
        metadata = context.metadata
        if metadata.requires_permission("network_access"):
            warnings.append("Plugin requests network access permission")
        
        if metadata.requires_permission("file_system_write"):
            warnings.append("Plugin requests file system write permission")
        
        # Check for suspicious dependency packages
        if metadata.dependencies and metadata.dependencies.get("packages"):
            suspicious_packages = self._check_suspicious_dependencies(metadata.dependencies["packages"])
            for pkg in suspicious_packages:
                warnings.append(f"Plugin requires potentially dangerous package: {pkg}")
        
        return warnings
    
    def _check_suspicious_dependencies(self, packages: List[str]) -> List[str]:
        """Check for suspicious dependency packages.
        
        Args:
            packages: List of package requirements
            
        Returns:
            List of suspicious packages
        """
        # List of packages that might indicate suspicious activity
        suspicious_keywords = [
            "requests",  # Network access
            "urllib3",   # Network access
            "subprocess", # System commands
            "os",        # System access
            "sys",       # System access
            "socket",    # Network sockets
        ]
        
        suspicious = []
        for pkg in packages:
            pkg_name = pkg.split(">=")[0].split("==")[0].split("<")[0].strip()
            if any(keyword in pkg_name.lower() for keyword in suspicious_keywords):
                suspicious.append(pkg)
        
        return suspicious
    
    # -------------------------------------------------------------------------
    # Dependency Management
    # -------------------------------------------------------------------------
    
    def _install_dependencies(self, context: InstallationContext) -> bool:
        """Install plugin dependencies using pip.
        
        Args:
            context: Installation context
            
        Returns:
            True if dependencies installed successfully
        """
        metadata = context.metadata
        plugin_dir = context.plugin_dir
        
        # Check if plugin has dependencies
        if not metadata.dependencies or not metadata.dependencies.get("packages"):
            self._logger.debug("No dependencies specified for plugin %s", metadata.name)
            return True
        
        # Check if requirements.txt exists
        requirements_file = plugin_dir / "requirements.txt"
        if not requirements_file.exists():
            self._logger.warning("Plugin specifies dependencies but requirements.txt not found")
            return True  # Continue installation - dependencies might be optional
        
        try:
            # Install dependencies using pip
            self._logger.info("Installing dependencies for plugin %s", metadata.name)
            
            cmd = [
                sys.executable, "-m", "pip", "install",
                "-r", str(requirements_file),
                "--quiet",  # Reduce output
                "--timeout", str(self._pip_timeout)
            ]
            
            self._logger.debug("Running pip command: %s", " ".join(cmd))
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._pip_timeout)
            
            if result.returncode != 0:
                self._logger.error("Failed to install dependencies for %s: %s", 
                                 metadata.name, result.stderr)
                return False
            
            # Track installed packages for potential rollback
            if result.stdout:
                # Parse pip output to track installed packages
                context.installed_dependencies = self._parse_pip_output(result.stdout)
            
            self._logger.info("Dependencies installed successfully for plugin %s", metadata.name)
            return True
            
        except subprocess.TimeoutExpired:
            self._logger.error("Timeout installing dependencies for plugin %s", metadata.name)
            return False
        except Exception as e:
            self._logger.error("Exception installing dependencies for %s: %s", metadata.name, e)
            return False
    
    def _parse_pip_output(self, pip_output: str) -> List[str]:
        """Parse pip output to extract installed package names."""
        # This is a simplified parser - in production you might want more sophisticated parsing
        packages = []
        for line in pip_output.split('\n'):
            if 'Successfully installed' in line:
                # Extract package names from "Successfully installed package1-version package2-version"
                parts = line.split('Successfully installed')[1].strip().split()
                for part in parts:
                    # Extract package name (before version)
                    pkg_name = part.split('-')[0]
                    if pkg_name:
                        packages.append(pkg_name)
        return packages
    
    # -------------------------------------------------------------------------
    # File Operations
    # -------------------------------------------------------------------------
    
    def _copy_plugin_files(self, context: InstallationContext) -> bool:
        """Copy plugin files to target directory.
        
        Args:
            context: Installation context
            
        Returns:
            True if files copied successfully
        """
        try:
            source_dir = context.plugin_dir
            target_dir = context.target_dir
            
            # Ensure target directory parent exists
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy all files and directories
            shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)
            
            self._logger.debug("Plugin files copied from %s to %s", source_dir, target_dir)
            return True
            
        except Exception as e:
            self._logger.error("Failed to copy plugin files: %s", e)
            return False
    
    def _create_backup(self, target_dir: Path) -> Optional[Path]:
        """Create backup of existing plugin installation.
        
        Args:
            target_dir: Directory to backup
            
        Returns:
            Path to backup directory or None if backup failed
        """
        if not self._backup_existing:
            return None
        
        try:
            backup_dir = target_dir.with_suffix(".backup")
            
            # Remove existing backup if present
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
            
            # Create backup
            shutil.copytree(target_dir, backup_dir)
            
            self._logger.debug("Created backup of existing installation: %s", backup_dir)
            return backup_dir
            
        except Exception as e:
            self._logger.error("Failed to create backup of %s: %s", target_dir, e)
            return None
    
    def _restore_backup(self, backup_dir: Path, target_dir: Path) -> bool:
        """Restore plugin from backup directory.
        
        Args:
            backup_dir: Backup directory
            target_dir: Target restoration directory
            
        Returns:
            True if restore successful
        """
        try:
            if not backup_dir.exists():
                return False
            
            # Remove current installation
            if target_dir.exists():
                shutil.rmtree(target_dir)
            
            # Restore from backup
            shutil.copytree(backup_dir, target_dir)
            
            self._logger.debug("Restored plugin from backup: %s -> %s", backup_dir, target_dir)
            return True
            
        except Exception as e:
            self._logger.error("Failed to restore backup from %s: %s", backup_dir, e)
            return False
    
    # -------------------------------------------------------------------------
    # Installation Lifecycle
    # -------------------------------------------------------------------------
    
    def _finalize_installation(self, context: InstallationContext) -> None:
        """Finalize plugin installation.
        
        Args:
            context: Installation context
        """
        # Remove backup if installation successful
        if context.backup_dir and context.backup_dir.exists():
            try:
                shutil.rmtree(context.backup_dir)
                self._logger.debug("Removed backup directory: %s", context.backup_dir)
            except Exception as e:
                self._logger.warning("Failed to remove backup directory %s: %s", 
                                   context.backup_dir, e)
        
        # Set installation metadata
        # In the future, we might want to store installation timestamp, version, etc.
        
        self._logger.debug("Plugin installation finalized: %s", context.metadata.name)
    
    def _rollback_installation(self, context: InstallationContext) -> None:
        """Rollback failed plugin installation.
        
        Args:
            context: Installation context
        """
        try:
            # Remove partially installed files
            if context.target_dir.exists():
                shutil.rmtree(context.target_dir)
                self._logger.debug("Removed failed installation: %s", context.target_dir)
            
            # Restore backup if available
            if context.backup_dir:
                if self._restore_backup(context.backup_dir, context.target_dir):
                    self._logger.info("Restored previous plugin version from backup")
                else:
                    self._logger.error("Failed to restore backup during rollback")
            
            # Note: We don't attempt to uninstall dependencies during rollback
            # as they might be used by other plugins or the system
            
        except Exception as e:
            self._logger.error("Error during installation rollback: %s", e)
    
    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------
    
    def _is_same_plugin_version(self, target_dir: Path, metadata: PluginMetadata) -> bool:
        """Check if target directory contains the same plugin version.
        
        Args:
            target_dir: Target installation directory
            metadata: New plugin metadata
            
        Returns:
            True if same plugin and version
        """
        try:
            existing_metadata_file = target_dir / "plugin.json"
            if not existing_metadata_file.exists():
                return False
            
            existing_metadata = validate_plugin_metadata(existing_metadata_file, target_dir)
            
            return (existing_metadata.name == metadata.name and 
                   existing_metadata.version == metadata.version)
            
        except Exception:
            return False
    
    def _create_result(self, success: bool, message: str, **kwargs) -> Dict[str, Any]:
        """Create installation result dictionary.
        
        Args:
            success: Whether operation succeeded
            message: Result message
            **kwargs: Additional result data
            
        Returns:
            Result dictionary
        """
        result = {
            "success": success,
            "message": message,
            "timestamp": self._get_current_timestamp()
        }
        result.update(kwargs)
        return result
    
    def _get_current_timestamp(self) -> str:
        """Get current timestamp as ISO string."""
        from datetime import datetime
        return datetime.now().isoformat()