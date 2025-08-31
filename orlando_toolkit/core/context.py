from __future__ import annotations

"""Application context for plugin integration.

The AppContext class provides plugins with safe access to core application
services while maintaining proper isolation and error boundaries. This follows
the design specifications for Task 6 of the plugin architecture implementation.
"""

import logging
from typing import Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .plugins.registry import ServiceRegistry
    from .plugins.manager import PluginManager
    from .services import ConversionService, StructureEditingService, UndoService, PreviewService
    from .models import DitaContext

logger = logging.getLogger(__name__)

__all__ = ["AppContext", "get_app_context", "set_app_context"]


class AppContext:
    """Application context providing plugins safe access to core services.
    
    The AppContext acts as a controlled gateway for plugins to access core
    application functionality while maintaining proper isolation and error
    boundaries. This enables plugin integration without exposing internal
    implementation details.
    
    Design Principles:
    - Safe service access with error boundaries
    - Plugin isolation and lifecycle management
    - Backward compatibility with existing services
    - Type-safe service resolution
    """
    
    def __init__(
        self,
        service_registry: ServiceRegistry,
        plugin_manager: Optional[PluginManager] = None,
        conversion_service: Optional[ConversionService] = None,
        structure_editing_service: Optional[StructureEditingService] = None,
        undo_service: Optional[UndoService] = None,
        preview_service: Optional[PreviewService] = None,
        ui_registry: Optional[Any] = None,
        app_instance: Optional[Any] = None
    ) -> None:
        """Initialize application context with core services.
        
        Args:
            service_registry: Plugin service registry
            plugin_manager: Plugin lifecycle manager
            conversion_service: Document conversion service
            structure_editing_service: DITA structure editing service
            undo_service: Undo/redo service
            preview_service: Preview generation service
        """
        self._service_registry = service_registry
        self._plugin_manager = plugin_manager
        self._conversion_service = conversion_service
        self._structure_editing_service = structure_editing_service
        self._undo_service = undo_service
        self._preview_service = preview_service
        self.ui_registry = ui_registry
        self._app_instance = app_instance
        
        # Plugin-accessible context data (namespaced by plugin ID)
        self._plugin_data: Dict[str, Dict[str, Any]] = {}
        
        # Current document context (read-only for plugins)
        self._current_dita_context: Optional[DitaContext] = None
        
        self._logger = logging.getLogger(f"{__name__}.AppContext")
        self._logger.info("AppContext initialized with ui_registry: %s", ui_registry is not None)
    
    # -------------------------------------------------------------------------
    # Service Registry Access
    # -------------------------------------------------------------------------
    
    @property
    def service_registry(self) -> ServiceRegistry:
        """Get the service registry for plugin service management.
        
        Returns:
            ServiceRegistry instance for plugin service registration/resolution
        """
        return self._service_registry
    
    # -------------------------------------------------------------------------
    # Plugin Manager Access
    # -------------------------------------------------------------------------
    
    @property
    def plugin_manager(self) -> Optional[PluginManager]:
        """Get the plugin manager for plugin lifecycle operations.
        
        Returns:
            PluginManager instance or None if not available
        """
        return self._plugin_manager
    
    # -------------------------------------------------------------------------
    # Core Service Access (Plugin-Safe)
    # -------------------------------------------------------------------------
    
    def get_conversion_service(self) -> Optional[ConversionService]:
        """Get the document conversion service.
        
        Returns:
            ConversionService instance or None if not available
        """
        return self._conversion_service
    
    def get_structure_editing_service(self) -> Optional[StructureEditingService]:
        """Get the structure editing service.
        
        Returns:
            StructureEditingService instance or None if not available
        """
        return self._structure_editing_service
    
    def get_undo_service(self) -> Optional[UndoService]:
        """Get the undo/redo service.
        
        Returns:
            UndoService instance or None if not available
        """
        return self._undo_service
    
    def get_preview_service(self) -> Optional[PreviewService]:
        """Get the preview generation service.
        
        Returns:
            PreviewService instance or None if not available
        """
        return self._preview_service
    
    # -------------------------------------------------------------------------
    # Plugin Data Management
    # -------------------------------------------------------------------------
    
    def set_plugin_data(self, plugin_id: str, key: str, value: Any) -> None:
        """Store plugin-specific data in the application context.
        
        Args:
            plugin_id: Plugin identifier
            key: Data key
            value: Data value to store
        """
        if plugin_id not in self._plugin_data:
            self._plugin_data[plugin_id] = {}
        
        self._plugin_data[plugin_id][key] = value
        self._logger.debug("Set plugin data: %s.%s", plugin_id, key)
    
    def get_plugin_data(self, plugin_id: str, key: str, default: Any = None) -> Any:
        """Retrieve plugin-specific data from the application context.
        
        Args:
            plugin_id: Plugin identifier
            key: Data key
            default: Default value if key not found
            
        Returns:
            Stored data value or default
        """
        plugin_data = self._plugin_data.get(plugin_id, {})
        return plugin_data.get(key, default)
    
    def clear_plugin_data(self, plugin_id: str) -> None:
        """Clear all data for a specific plugin.
        
        Args:
            plugin_id: Plugin identifier
        """
        if plugin_id in self._plugin_data:
            del self._plugin_data[plugin_id]
            self._logger.debug("Cleared plugin data for: %s", plugin_id)
    
    # -------------------------------------------------------------------------
    # Document Context Access (Read-Only for Plugins)
    # -------------------------------------------------------------------------
    
    def get_current_dita_context(self) -> Optional[DitaContext]:
        """Get the current DITA document context (read-only).
        
        Returns:
            Current DitaContext or None if no document is loaded
        """
        return self._current_dita_context
    
    def _set_current_dita_context(self, context: Optional[DitaContext]) -> None:
        """Set the current DITA context (internal use only).
        
        Args:
            context: DitaContext to set as current
        """
        self._current_dita_context = context
        if context:
            plugin_data = getattr(context, 'plugin_data', {}) if hasattr(context, 'plugin_data') else {}
            source_plugin = plugin_data.get('_source_plugin', 'None')
            self._logger.info("Updated current DitaContext with source plugin: %s", source_plugin)
        else:
            self._logger.info("Cleared current DitaContext")
    
    def document_source_plugin_has_capability(self, capability: str) -> bool:
        """Check if the document source plugin has a specific UI capability.
        
        Args:
            capability: UI capability to check (e.g., "heading_filter", "style_toggle")
            
        Returns:
            True if source plugin has the capability, False otherwise
        """
        try:
            # Get source plugin ID from current document
            if (self._current_dita_context and 
                hasattr(self._current_dita_context, 'plugin_data') and 
                self._current_dita_context.plugin_data):
                source_plugin = self._current_dita_context.plugin_data.get('_source_plugin')
                
                if source_plugin and hasattr(self, 'ui_registry'):
                    result = self.ui_registry.plugin_has_capability(source_plugin, capability)
                    self._logger.debug(f"Capability check: plugin='{source_plugin}', capability='{capability}', result={result}")
                    return result
                else:
                    self._logger.debug(f"Capability check: no source plugin or ui_registry, capability='{capability}', result=False")
            else:
                self._logger.debug(f"Capability check: no dita_context or plugin_data, capability='{capability}', result=False")
            
            return False
        except Exception as e:
            self._logger.debug(f"Capability check error: capability='{capability}', error={e}")
            return False
    
    # -------------------------------------------------------------------------
    # Service Lifecycle Management
    # -------------------------------------------------------------------------
    
    def update_services(
        self,
        conversion_service: Optional[ConversionService] = None,
        structure_editing_service: Optional[StructureEditingService] = None,
        undo_service: Optional[UndoService] = None,
        preview_service: Optional[PreviewService] = None
    ) -> None:
        """Update core services (for service factories).
        
        Args:
            conversion_service: Updated conversion service
            structure_editing_service: Updated structure editing service
            undo_service: Updated undo service
            preview_service: Updated preview service
        """
        if conversion_service is not None:
            self._conversion_service = conversion_service
            self._logger.debug("Updated conversion service")
        
        if structure_editing_service is not None:
            self._structure_editing_service = structure_editing_service
            self._logger.debug("Updated structure editing service")
        
        if undo_service is not None:
            self._undo_service = undo_service
            self._logger.debug("Updated undo service")
        
        if preview_service is not None:
            self._preview_service = preview_service
            self._logger.debug("Updated preview service")
    
    # -------------------------------------------------------------------------
    # Plugin Integration Helpers
    # -------------------------------------------------------------------------
    
    def is_plugin_active(self, plugin_id: str) -> bool:
        """Check if a plugin is currently active.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            True if plugin is active, False otherwise
        """
        if self._plugin_manager is None:
            return False
        
        try:
            # Use plugin manager's is_plugin_active which now correctly checks both state and instance
            return self._plugin_manager.is_plugin_active(plugin_id)
        except Exception as e:
            self._logger.warning("Error checking plugin status %s: %s", plugin_id, e)
            return False
    
    def get_active_plugins(self) -> list[str]:
        """Get list of currently active plugin IDs.
        
        Returns:
            List of active plugin identifiers
        """
        if self._plugin_manager is None:
            return []
        
        try:
            return self._plugin_manager.get_active_plugin_ids()
        except Exception as e:
            self._logger.warning("Error getting active plugins: %s", e)
            return []
    
    # -------------------------------------------------------------------------
    # Error Handling and Logging
    # -------------------------------------------------------------------------
    
    def log_plugin_error(self, plugin_id: str, error: Exception, context: str = "") -> None:
        """Log plugin errors with proper context.
        
        Args:
            plugin_id: Plugin identifier
            error: Exception that occurred
            context: Additional context information
        """
        context_msg = f" ({context})" if context else ""
        self._logger.error("Plugin %s error%s: %s", plugin_id, context_msg, error)
    
    def log_plugin_warning(self, plugin_id: str, message: str) -> None:
        """Log plugin warnings.
        
        Args:
            plugin_id: Plugin identifier
            message: Warning message
        """
        self._logger.warning("Plugin %s: %s", plugin_id, message)
    
    def log_plugin_info(self, plugin_id: str, message: str) -> None:
        """Log plugin information.
        
        Args:
            plugin_id: Plugin identifier
            message: Information message
        """
        self._logger.info("Plugin %s: %s", plugin_id, message)
    
    # -------------------------------------------------------------------------
    # Context Statistics and Debugging
    # -------------------------------------------------------------------------
    
    def get_context_stats(self) -> Dict[str, Any]:
        """Get context statistics for debugging.
        
        Returns:
            Dictionary with context statistics
        """
        return {
            'has_conversion_service': self._conversion_service is not None,
            'has_structure_editing_service': self._structure_editing_service is not None,
            'has_undo_service': self._undo_service is not None,
            'has_preview_service': self._preview_service is not None,
            'has_plugin_manager': self._plugin_manager is not None,
            'plugin_data_count': len(self._plugin_data),
            'plugins_with_data': list(self._plugin_data.keys()),
            'has_current_context': self._current_dita_context is not None,
            'service_registry_stats': self._service_registry.get_registry_stats() if self._service_registry else {}
        }


# -------------------------------------------------------------------------
# Global Context Accessor (Context Bridge Pattern)
# -------------------------------------------------------------------------

# Global context accessor (temporary fix for UI integration)
_global_app_context: Optional[AppContext] = None

def set_app_context(context: AppContext) -> None:
    """Set the global application context (internal use only)."""
    global _global_app_context
    _global_app_context = context
    logger.info("Global AppContext set successfully")

def get_app_context() -> Optional[AppContext]:
    """Get the global application context."""
    return _global_app_context