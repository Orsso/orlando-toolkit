from __future__ import annotations

"""Base plugin class and lifecycle management.

Defines the abstract BasePlugin class that all plugins must inherit from,
along with plugin lifecycle hooks and state management. Provides a stable
interface for plugin development and ensures consistent behavior across
all plugins.
"""

import logging
import os
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Any, Dict

if TYPE_CHECKING:
    from .metadata import PluginMetadata

logger = logging.getLogger(__name__)


class PluginState(Enum):
    """Plugin lifecycle states.
    
    Plugins transition through these states during their lifecycle:
    DISCOVERED -> LOADING -> LOADED -> ACTIVE
    
    Error states can occur at any transition point.
    """
    
    DISCOVERED = "discovered"  # Plugin found but not loaded
    LOADING = "loading"        # Currently importing plugin modules  
    LOADED = "loaded"          # Plugin instantiated successfully
    ACTIVE = "active"          # Plugin services registered and ready
    ERROR = "error"            # Plugin failed to load or threw exception
    DISABLED = "disabled"      # Plugin explicitly disabled by user


class AppContext:
    """Application context provided to plugins.
    
    Provides plugins with controlled access to application services
    and functionality while maintaining security boundaries.
    """
    
    def __init__(self, service_registry: 'ServiceRegistry') -> None:
        self.service_registry = service_registry
        self._app_config: Dict[str, Any] = {}
        self._shutdown_requested = False
    
    def is_shutdown_requested(self) -> bool:
        """Check if application shutdown has been requested."""
        return self._shutdown_requested
    
    def set_shutdown_requested(self, requested: bool = True) -> None:
        """Set shutdown request flag (for internal use)."""
        self._shutdown_requested = requested
    
    def get_app_config(self, key: str, default: Any = None) -> Any:
        """Get application configuration value."""
        return self._app_config.get(key, default)
    
    def set_app_config(self, key: str, value: Any) -> None:
        """Set application configuration value (restricted access)."""
        # In future versions, this might be restricted to certain plugin types
        self._app_config[key] = value


class BasePlugin(ABC):
    """Abstract base class for all Orlando Toolkit plugins.
    
    All plugins must inherit from this class and implement the required
    abstract methods. The base class provides lifecycle management,
    metadata access, and utility methods for plugin development.
    
    Plugin Lifecycle:
    1. Plugin is discovered and metadata is validated
    2. Plugin class is instantiated (constructor called)
    3. on_load() is called with application context
    4. Plugin transitions to LOADED state
    5. on_activate() is called when plugin should register services
    6. Plugin transitions to ACTIVE state
    7. on_deactivate() is called when plugin should cleanup
    8. on_unload() is called before plugin removal
    """
    
    def __init__(self, plugin_id: str, metadata: 'PluginMetadata',
                 plugin_dir: str) -> None:
        """Initialize plugin instance.
        
        Args:
            plugin_id: Unique identifier for this plugin instance
            metadata: Validated plugin metadata
            plugin_dir: Path to plugin directory
        """
        self.plugin_id = plugin_id
        self.metadata = metadata
        self.plugin_dir = Path(plugin_dir)
        self._state = PluginState.DISCOVERED
        self._app_context: Optional[AppContext] = None
        self._logger = logging.getLogger(f"plugin.{plugin_id}")
        self._config: Dict[str, Any] = {}
        self._config_file = self.plugin_dir / "config.yml"
    
    # -------------------------------------------------------------------------
    # Public Properties
    # -------------------------------------------------------------------------
    
    @property
    def state(self) -> PluginState:
        """Current plugin state."""
        return self._state
    
    @property
    def app_context(self) -> Optional[AppContext]:
        """Application context (available after on_load)."""
        return self._app_context
    
    @property
    def logger(self) -> logging.Logger:
        """Plugin-specific logger."""
        return self._logger
    
    @property
    def config(self) -> Dict[str, Any]:
        """Plugin configuration dictionary."""
        return self._config.copy()  # Return copy to prevent modification
    
    # -------------------------------------------------------------------------
    # Lifecycle Hooks (may be overridden by plugins)
    # -------------------------------------------------------------------------
    
    def on_load(self, app_context: AppContext) -> None:
        """Called after plugin instantiation with application context.
        
        Override this method to perform initialization that requires
        access to application services. This is called before the
        plugin transitions to LOADED state.
        
        Args:
            app_context: Application context for accessing services
            
        Raises:
            Exception: Any exception will cause plugin to enter ERROR state
        """
        self._app_context = app_context
        self._logger.debug("Plugin loaded: %s v%s", 
                          self.metadata.name, self.metadata.version)
    
    def on_activate(self) -> None:
        """Called when plugin services should be registered.
        
        Override this method to register services with the application
        service registry. This is where plugins typically register
        DocumentHandlers, UI extensions, and other services.
        
        This is called after on_load() and before the plugin transitions
        to ACTIVE state.
        
        Raises:
            Exception: Any exception will cause plugin to enter ERROR state
        """
        self._logger.debug("Plugin activated: %s", self.plugin_id)
    
    def on_deactivate(self) -> None:
        """Called when plugin should cleanup resources and unregister services.
        
        Override this method to cleanup resources, unregister services,
        and prepare for plugin removal. The plugin will transition to
        LOADED state after this call.
        
        This method should not raise exceptions as it's called during
        cleanup operations.
        """
        self._logger.debug("Plugin deactivated: %s", self.plugin_id)
    
    def on_unload(self) -> None:
        """Called before plugin removal.
        
        Override this method to perform final cleanup before the plugin
        is completely removed from memory. After this call, the plugin
        instance should be ready for garbage collection.
        
        This method should not raise exceptions as it's called during
        cleanup operations.
        """
        self._logger.debug("Plugin unloaded: %s", self.plugin_id)
    
    # -------------------------------------------------------------------------
    # Configuration Management
    # -------------------------------------------------------------------------
    
    def load_config(self) -> Dict[str, Any]:
        """Load plugin configuration from plugin directory.
        
        Loads configuration from config.yml in the plugin directory.
        Creates a default configuration file if it doesn't exist.
        
        Returns:
            Configuration dictionary
            
        Raises:
            Exception: If configuration file cannot be read or parsed
        """
        try:
            import yaml
        except ModuleNotFoundError:
            self._logger.warning("PyYAML not available, using empty config")
            self._config = {}
            return self._config.copy()
        
        try:
            if self._config_file.exists():
                with open(self._config_file, 'r', encoding='utf-8') as f:
                    config_data = yaml.safe_load(f) or {}
                self._config = config_data
                self._logger.debug("Configuration loaded from %s", self._config_file)
            else:
                # Create default configuration file
                default_config = self._get_default_config()
                self.save_config(default_config)
                self._config = default_config
                self._logger.info("Created default configuration: %s", self._config_file)
                
        except Exception as e:
            self._logger.error("Failed to load configuration from %s: %s", self._config_file, e)
            self._config = {}
            raise
        
        return self._config.copy()
    
    def save_config(self, config: Dict[str, Any]) -> None:
        """Save plugin configuration to plugin directory.
        
        Saves configuration to config.yml in the plugin directory.
        Creates the plugin directory if it doesn't exist.
        
        Args:
            config: Configuration dictionary to save
            
        Raises:
            Exception: If configuration cannot be saved
        """
        try:
            import yaml
        except ModuleNotFoundError:
            self._logger.error("PyYAML not available, cannot save config")
            return
        
        try:
            # Ensure plugin directory exists
            self.plugin_dir.mkdir(parents=True, exist_ok=True)
            
            # Save configuration
            with open(self._config_file, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, indent=2)
            
            self._config = config.copy()
            self._logger.debug("Configuration saved to %s", self._config_file)
            
        except Exception as e:
            self._logger.error("Failed to save configuration to %s: %s", self._config_file, e)
            raise
    
    def get_config_value(self, key: str, default: Any = None) -> Any:
        """Get specific configuration value.
        
        Args:
            key: Configuration key (supports dot notation, e.g., 'section.key')
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set_config_value(self, key: str, value: Any) -> None:
        """Set specific configuration value.
        
        Args:
            key: Configuration key (supports dot notation, e.g., 'section.key')
            value: Value to set
        """
        keys = key.split('.')
        config = self._config
        
        # Navigate to the parent dictionary
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            elif not isinstance(config[k], dict):
                config[k] = {}
            config = config[k]
        
        # Set the value
        config[keys[-1]] = value
        self._logger.debug("Configuration value set: %s = %s", key, value)
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration for this plugin.
        
        Override this method in plugin subclasses to provide
        plugin-specific default configuration.
        
        Returns:
            Default configuration dictionary
        """
        return {}
    
    # -------------------------------------------------------------------------
    # State Management (Internal Use)
    # -------------------------------------------------------------------------
    
    def _set_state(self, state: PluginState) -> None:
        """Set plugin state (internal use only)."""
        old_state = self._state
        self._state = state
        self._logger.debug("Plugin state changed: %s -> %s", 
                          old_state.value, state.value)
    
    def _is_state(self, *states: PluginState) -> bool:
        """Check if plugin is in one of the specified states."""
        return self._state in states
    
    # -------------------------------------------------------------------------
    # Abstract Methods (must be implemented by plugins)
    # -------------------------------------------------------------------------
    
    @abstractmethod
    def get_name(self) -> str:
        """Get human-readable plugin name.
        
        Returns:
            Plugin display name
        """
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        """Get plugin description.
        
        Returns:
            Brief description of plugin functionality
        """
        pass
    
    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------
    
    def log_info(self, message: str, *args: Any) -> None:
        """Log info message with plugin context."""
        self._logger.info(f"[{self.plugin_id}] {message}", *args)
    
    def log_warning(self, message: str, *args: Any) -> None:
        """Log warning message with plugin context."""
        self._logger.warning(f"[{self.plugin_id}] {message}", *args)
    
    def log_error(self, message: str, *args: Any) -> None:
        """Log error message with plugin context."""
        self._logger.error(f"[{self.plugin_id}] {message}", *args)
    
    def log_debug(self, message: str, *args: Any) -> None:
        """Log debug message with plugin context."""
        self._logger.debug(f"[{self.plugin_id}] {message}", *args)
    
    def __str__(self) -> str:
        """String representation of plugin."""
        return f"{self.metadata.name} v{self.metadata.version} ({self._state.value})"
    
    def __repr__(self) -> str:
        """Developer representation of plugin."""
        return (f"BasePlugin(plugin_id='{self.plugin_id}', "
                f"name='{self.metadata.name}', "
                f"version='{self.metadata.version}', "
                f"state='{self._state.value}')")