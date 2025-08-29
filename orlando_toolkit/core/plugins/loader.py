from __future__ import annotations

"""Plugin discovery and loading system.

Handles plugin discovery from the user's plugin directory, validation
of plugin metadata and structure, loading of plugin modules, and 
instantiation of plugin classes. Provides comprehensive error handling
and logging for plugin loading operations.
"""

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Type, Any
import os

from .base import BasePlugin, PluginState, AppContext
from .metadata import PluginMetadata, validate_plugin_metadata
from .registry import ServiceRegistry
from .exceptions import (
    PluginError,
    PluginLoadError,
    PluginValidationError,
    PluginDependencyError,
    PluginStateError
)

logger = logging.getLogger(__name__)


def get_user_plugins_dir() -> Path:
    """Get the user's plugin directory path.
    
    Returns the directory where plugins are installed:
    - Windows: %LOCALAPPDATA%\\OrlandoToolkit\\plugins
    - Unix: ~/.orlando_toolkit/plugins
    
    Returns:
        Path to user plugins directory
    """
    if os.name == 'nt':  # Windows
        local_appdata = os.environ.get('LOCALAPPDATA')
        if local_appdata:
            return Path(local_appdata) / "OrlandoToolkit" / "plugins"
        else:
            return Path.home() / "AppData" / "Local" / "OrlandoToolkit" / "plugins"
    else:  # Unix-like systems
        return Path.home() / ".orlando_toolkit" / "plugins"


class PluginInfo:
    """Information about a discovered plugin.
    
    Contains plugin metadata and state information for
    plugins that have been discovered but not necessarily loaded.
    """
    
    def __init__(self, plugin_dir: Path, metadata: PluginMetadata) -> None:
        self.plugin_dir = plugin_dir
        self.metadata = metadata
        self.state = PluginState.DISCOVERED
        self.instance: Optional[BasePlugin] = None
        self.load_error: Optional[Exception] = None
    
    @property
    def plugin_id(self) -> str:
        """Plugin identifier."""
        return self.metadata.name
    
    def is_loaded(self) -> bool:
        """Check if plugin is loaded."""
        return self.instance is not None
    
    def is_active(self) -> bool:
        """Check if plugin is active."""
        return self.state == PluginState.ACTIVE
    
    def __str__(self) -> str:
        return f"{self.metadata.name} v{self.metadata.version} ({self.state.value})"


class PluginLoader:
    """Plugin discovery and loading manager.
    
    Handles the complete plugin lifecycle from discovery through loading
    and activation. Provides error boundaries to ensure plugin failures
    do not crash the main application.
    """
    
    def __init__(self, service_registry: ServiceRegistry) -> None:
        """Initialize plugin loader.
        
        Args:
            service_registry: Service registry for plugin services
        """
        self.service_registry = service_registry
        self.app_context = AppContext(service_registry)
        
        self._plugins: Dict[str, PluginInfo] = {}
        self._logger = logging.getLogger(f"{__name__}.PluginLoader")
        self._plugins_dir = get_user_plugins_dir()
        
        # Ensure plugins directory exists
        self._plugins_dir.mkdir(parents=True, exist_ok=True)
        self._logger.debug("Plugin directory: %s", self._plugins_dir)
    
    # -------------------------------------------------------------------------
    # Plugin Discovery
    # -------------------------------------------------------------------------
    
    def discover_plugins(self) -> List[PluginInfo]:
        """Discover all plugins in the plugins directory.
        
        Scans the user's plugins directory for valid plugin directories
        and validates their metadata. Does not load the plugins.
        
        Returns:
            List of discovered plugin info objects
        """
        discovered = []
        
        if not self._plugins_dir.exists():
            self._logger.info("Plugins directory does not exist: %s", self._plugins_dir)
            return discovered
        
        self._logger.info("Discovering plugins in: %s", self._plugins_dir)
        
        # Scan for plugin directories
        for item in self._plugins_dir.iterdir():
            if not item.is_dir():
                continue
            
            plugin_name = item.name
            
            # Skip hidden directories and common non-plugin directories
            if plugin_name.startswith('.') or plugin_name in ['__pycache__', 'temp']:
                continue
            
            try:
                plugin_info = self._discover_single_plugin(item)
                if plugin_info:
                    discovered.append(plugin_info)
                    self._plugins[plugin_info.plugin_id] = plugin_info
                    self._logger.info("Discovered plugin: %s", plugin_info)
                    
            except Exception as e:
                self._logger.error("Failed to discover plugin in %s: %s", item, e)
                continue
        
        self._logger.info("Discovery complete: found %d plugins", len(discovered))
        return discovered
    
    def _discover_single_plugin(self, plugin_dir: Path) -> Optional[PluginInfo]:
        """Discover and validate a single plugin.
        
        Args:
            plugin_dir: Path to plugin directory
            
        Returns:
            PluginInfo object or None if invalid
            
        Raises:
            PluginValidationError: If plugin validation fails
        """
        metadata_file = plugin_dir / "plugin.json"
        
        try:
            # Validate plugin metadata
            metadata = validate_plugin_metadata(metadata_file, plugin_dir)
            
            # Create plugin info
            plugin_info = PluginInfo(plugin_dir, metadata)
            
            self._logger.debug("Validated plugin metadata: %s v%s", 
                             metadata.name, metadata.version)
            
            return plugin_info
            
        except PluginValidationError as e:
            self._logger.error("Plugin validation failed for %s: %s", 
                             plugin_dir.name, e)
            raise
        except Exception as e:
            self._logger.error("Unexpected error discovering plugin %s: %s",
                             plugin_dir.name, e)
            raise PluginValidationError(
                f"Unexpected error during plugin discovery: {e}",
                plugin_id=plugin_dir.name,
                cause=e
            )
    
    # -------------------------------------------------------------------------
    # Plugin Loading
    # -------------------------------------------------------------------------
    
    def load_plugin(self, plugin_id: str) -> bool:
        """Load a specific plugin by ID.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            True if plugin loaded successfully, False otherwise
        """
        if plugin_id not in self._plugins:
            self._logger.error("Plugin not found: %s", plugin_id)
            return False
        
        plugin_info = self._plugins[plugin_id]
        
        if plugin_info.is_loaded():
            self._logger.debug("Plugin already loaded: %s", plugin_id)
            return True
        
        try:
            return self._load_plugin_instance(plugin_info)
        except Exception as e:
            self._logger.error("Failed to load plugin %s: %s", plugin_id, e)
            plugin_info.load_error = e
            plugin_info.state = PluginState.ERROR
            return False
    
    def load_all_plugins(self) -> Dict[str, bool]:
        """Load all discovered plugins.
        
        Returns:
            Dictionary mapping plugin_id -> success status
        """
        results = {}
        
        for plugin_id in self._plugins:
            try:
                success = self.load_plugin(plugin_id)
                results[plugin_id] = success
            except Exception as e:
                self._logger.error("Unexpected error loading plugin %s: %s", 
                                 plugin_id, e)
                results[plugin_id] = False
        
        success_count = sum(results.values())
        total_count = len(results)
        
        self._logger.info("Plugin loading complete: %d/%d successful", 
                         success_count, total_count)
        
        return results
    
    def _load_plugin_instance(self, plugin_info: PluginInfo) -> bool:
        """Load a plugin instance from plugin info.
        
        Args:
            plugin_info: Plugin information
            
        Returns:
            True if loaded successfully
            
        Raises:
            PluginLoadError: If plugin loading fails
        """
        plugin_id = plugin_info.plugin_id
        metadata = plugin_info.metadata
        
        try:
            # Set loading state
            plugin_info.state = PluginState.LOADING
            
            # Import plugin module
            plugin_module = self._import_plugin_module(plugin_info)
            
            # Get plugin class from module
            plugin_class = self._get_plugin_class(plugin_module, metadata.entry_point)
            
            # Instantiate plugin
            plugin_instance = plugin_class(
                plugin_id=plugin_id,
                metadata=metadata,
                plugin_dir=str(plugin_info.plugin_dir)
            )
            
            # Validate plugin instance
            if not isinstance(plugin_instance, BasePlugin):
                raise PluginLoadError(
                    f"Plugin class does not inherit from BasePlugin: {plugin_class}",
                    plugin_id=plugin_id
                )
            
            # Call on_load lifecycle hook
            plugin_instance._set_state(PluginState.LOADING)
            plugin_instance.on_load(self.app_context)
            plugin_instance._set_state(PluginState.LOADED)
            
            # Update plugin info
            plugin_info.instance = plugin_instance
            plugin_info.state = PluginState.LOADED
            plugin_info.load_error = None
            
            self._logger.info("Plugin loaded successfully: %s v%s", 
                            metadata.name, metadata.version)
            
            return True
            
        except PluginLoadError:
            raise
        except Exception as e:
            raise PluginLoadError(
                f"Unexpected error during plugin loading: {e}",
                plugin_id=plugin_id,
                cause=e
            )
    
    def _import_plugin_module(self, plugin_info: PluginInfo) -> Any:
        """Import plugin module.
        
        Args:
            plugin_info: Plugin information
            
        Returns:
            Imported module
            
        Raises:
            PluginLoadError: If import fails
        """
        plugin_id = plugin_info.plugin_id
        entry_point = plugin_info.metadata.entry_point
        plugin_dir = plugin_info.plugin_dir
        
        try:
            # Add plugin directory to Python path temporarily
            original_path = sys.path.copy()
            if str(plugin_dir) not in sys.path:
                sys.path.insert(0, str(plugin_dir))
            
            try:
                # Convert entry point to module path (e.g., "src.plugin.MyPlugin" -> "src.plugin")
                module_parts = entry_point.split('.')
                module_path = '.'.join(module_parts[:-1])  # Remove class name
                
                # Import the module
                module = importlib.import_module(module_path)
                
                return module
                
            finally:
                # Restore original Python path
                sys.path[:] = original_path
                
        except ImportError as e:
            raise PluginLoadError(
                f"Failed to import plugin module '{module_path}': {e}",
                plugin_id=plugin_id,
                cause=e
            )
        except Exception as e:
            raise PluginLoadError(
                f"Unexpected error importing plugin module: {e}",
                plugin_id=plugin_id,
                cause=e
            )
    
    def _get_plugin_class(self, module: Any, entry_point: str) -> Type[BasePlugin]:
        """Get plugin class from module.
        
        Args:
            module: Imported plugin module
            entry_point: Full entry point (e.g., "src.plugin.MyPlugin")
            
        Returns:
            Plugin class
            
        Raises:
            PluginLoadError: If class not found or invalid
        """
        try:
            # Extract class name from entry point
            class_name = entry_point.split('.')[-1]
            
            # Get class from module
            if not hasattr(module, class_name):
                available_classes = [name for name in dir(module) 
                                   if not name.startswith('_') and 
                                   isinstance(getattr(module, name), type)]
                raise PluginLoadError(
                    f"Class '{class_name}' not found in module. "
                    f"Available classes: {available_classes}"
                )
            
            plugin_class = getattr(module, class_name)
            
            # Validate class
            if not isinstance(plugin_class, type):
                raise PluginLoadError(f"'{class_name}' is not a class")
            
            if not issubclass(plugin_class, BasePlugin):
                raise PluginLoadError(
                    f"Class '{class_name}' does not inherit from BasePlugin"
                )
            
            return plugin_class
            
        except PluginLoadError:
            raise
        except Exception as e:
            raise PluginLoadError(
                f"Error getting plugin class: {e}",
                cause=e
            )
    
    # -------------------------------------------------------------------------
    # Plugin Activation
    # -------------------------------------------------------------------------
    
    def activate_plugin(self, plugin_id: str) -> bool:
        """Activate a loaded plugin.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            True if activated successfully
        """
        if plugin_id not in self._plugins:
            self._logger.error("Plugin not found: %s", plugin_id)
            return False
        
        plugin_info = self._plugins[plugin_id]
        
        if not plugin_info.is_loaded():
            self._logger.error("Plugin not loaded, cannot activate: %s", plugin_id)
            return False
        
        if plugin_info.is_active():
            self._logger.debug("Plugin already active: %s", plugin_id)
            return True
        
        try:
            # Call activation lifecycle hook
            plugin_info.instance.on_activate()
            plugin_info.instance._set_state(PluginState.ACTIVE)
            plugin_info.state = PluginState.ACTIVE
            
            self._logger.info("Plugin activated: %s", plugin_id)
            return True
            
        except Exception as e:
            self._logger.error("Failed to activate plugin %s: %s", plugin_id, e)
            plugin_info.state = PluginState.ERROR
            plugin_info.load_error = e
            return False
    
    def deactivate_plugin(self, plugin_id: str) -> bool:
        """Deactivate an active plugin.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            True if deactivated successfully
        """
        if plugin_id not in self._plugins:
            self._logger.error("Plugin not found: %s", plugin_id)
            return False
        
        plugin_info = self._plugins[plugin_id]
        
        if not plugin_info.is_active():
            self._logger.debug("Plugin not active: %s", plugin_id)
            return True
        
        try:
            # Unregister plugin services
            self.service_registry.unregister_plugin_services(plugin_id)
            
            # Call deactivation lifecycle hook
            plugin_info.instance.on_deactivate()
            plugin_info.instance._set_state(PluginState.LOADED)
            plugin_info.state = PluginState.LOADED
            
            self._logger.info("Plugin deactivated: %s", plugin_id)
            return True
            
        except Exception as e:
            self._logger.error("Error deactivating plugin %s: %s", plugin_id, e)
            # Still mark as deactivated to prevent further issues
            plugin_info.state = PluginState.ERROR
            return False
    
    # -------------------------------------------------------------------------
    # Plugin Management
    # -------------------------------------------------------------------------
    
    def get_plugin_info(self, plugin_id: str) -> Optional[PluginInfo]:
        """Get plugin information.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            PluginInfo or None if not found
        """
        return self._plugins.get(plugin_id)
    
    def get_all_plugins(self) -> Dict[str, PluginInfo]:
        """Get all plugin information.
        
        Returns:
            Dictionary mapping plugin_id -> PluginInfo
        """
        return self._plugins.copy()
    
    def get_active_plugins(self) -> List[PluginInfo]:
        """Get all active plugins.
        
        Returns:
            List of active PluginInfo objects
        """
        return [info for info in self._plugins.values() if info.is_active()]
    
    def get_loaded_plugins(self) -> List[PluginInfo]:
        """Get all loaded plugins.
        
        Returns:
            List of loaded PluginInfo objects
        """
        return [info for info in self._plugins.values() if info.is_loaded()]
    
    def unload_plugin(self, plugin_id: str) -> bool:
        """Unload a plugin completely.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            True if unloaded successfully
        """
        if plugin_id not in self._plugins:
            return False
        
        plugin_info = self._plugins[plugin_id]
        
        try:
            # Deactivate if active
            if plugin_info.is_active():
                self.deactivate_plugin(plugin_id)
            
            # Call unload lifecycle hook
            if plugin_info.instance:
                plugin_info.instance.on_unload()
                plugin_info.instance._set_state(PluginState.DISCOVERED)
            
            # Clear instance
            plugin_info.instance = None
            plugin_info.state = PluginState.DISCOVERED
            plugin_info.load_error = None
            
            self._logger.info("Plugin unloaded: %s", plugin_id)
            return True
            
        except Exception as e:
            self._logger.error("Error unloading plugin %s: %s", plugin_id, e)
            return False
    
    def get_loader_stats(self) -> Dict[str, Any]:
        """Get plugin loader statistics.
        
        Returns:
            Dictionary with loader statistics
        """
        stats = {
            'total_plugins': len(self._plugins),
            'loaded_plugins': len([p for p in self._plugins.values() if p.is_loaded()]),
            'active_plugins': len([p for p in self._plugins.values() if p.is_active()]),
            'error_plugins': len([p for p in self._plugins.values() if p.state == PluginState.ERROR]),
            'plugins_dir': str(self._plugins_dir)
        }
        
        return stats