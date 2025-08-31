from __future__ import annotations

"""UI Registry for plugin UI component management.

The UI Registry provides a centralized system for plugins to register
UI components such as right panel factories, marker providers, and other
UI extensions. This registry ensures proper lifecycle management and
isolation of plugin UI components.
"""

import logging
from typing import Dict, List, Any, Optional, Callable, Protocol, runtime_checkable
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


@runtime_checkable
class PanelFactory(Protocol):
    """Protocol for plugin-provided panel factories.
    
    Panel factories create UI panels that can be integrated into the
    right panel coordinator system. Each factory is responsible for
    creating and configuring panel instances on demand.
    """
    
    def create_panel(self, parent: Any, context: Any) -> Any:
        """Create and return a panel instance.
        
        Args:
            parent: Parent widget for the panel
            context: Application context for panel initialization
            
        Returns:
            Panel widget instance ready for display
        """
        ...
    
    def get_panel_type(self) -> str:
        """Return unique identifier for this panel type."""
        ...
    
    def get_display_name(self) -> str:
        """Return human-readable display name for this panel."""
        ...
    
    def cleanup_panel(self, panel: Any) -> None:
        """Clean up resources when panel is no longer needed.
        
        Args:
            panel: Panel instance to clean up
        """
        ...


class UIRegistry:
    """Registry for plugin UI components and extensions.
    
    This registry manages the registration and lifecycle of plugin-provided
    UI components including panel factories, marker providers, and other
    UI extension points. It ensures proper isolation and cleanup of plugin
    UI components.
    
    The registry supports:
    - Panel factory registration for right panel extensions
    - Marker provider registration for scrollbar marker extensions
    - Component lifecycle management and cleanup
    - Plugin isolation to prevent UI failures from affecting core app
    """
    
    def __init__(self) -> None:
        """Initialize the UI registry."""
        self._panel_factories: Dict[str, PanelFactory] = {}
        self._marker_providers: Dict[str, 'MarkerProvider'] = {}
        self._plugin_components: Dict[str, Dict[str, Any]] = {}
        self._component_cleanup: Dict[str, List[Callable[[], None]]] = {}
        # Track UI capabilities provided by each plugin
        self._plugin_capabilities: Dict[str, List[str]] = {}
    
    # Panel Factory Management
    
    def register_panel_factory(self, panel_type: str, factory: Any, plugin_id: str) -> None:
        """Register a panel factory for a plugin.
        
        Args:
            panel_type: Panel type identifier (e.g., 'heading_filter')
            factory: Panel factory implementation
            plugin_id: Unique identifier for the plugin
            
        Raises:
            ValueError: If panel type is already registered
        """
        try:
            if panel_type in self._panel_factories:
                existing_plugin = None
                for pid, components in self._plugin_components.items():
                    if 'panels' in components and panel_type in components['panels']:
                        existing_plugin = pid
                        break
                
                raise ValueError(
                    f"Panel type '{panel_type}' already registered by plugin '{existing_plugin}'"
                )
            
            self._panel_factories[panel_type] = factory
            
            # Track plugin components for cleanup
            if plugin_id not in self._plugin_components:
                self._plugin_components[plugin_id] = {}
            if 'panels' not in self._plugin_components[plugin_id]:
                self._plugin_components[plugin_id]['panels'] = {}
            self._plugin_components[plugin_id]['panels'][panel_type] = factory
            
            logger.info(f"Registered panel factory '{panel_type}' for plugin '{plugin_id}'")
            
        except Exception as e:
            logger.error(f"Failed to register panel factory for plugin '{plugin_id}': {e}")
            raise
    
    def unregister_panel_factory(self, panel_type: str, plugin_id: str) -> None:
        """Unregister a panel factory for a plugin.
        
        Args:
            panel_type: Panel type to unregister  
            plugin_id: Plugin identifier
        """
        try:
            if panel_type in self._panel_factories:
                del self._panel_factories[panel_type]
            
            # Clean up plugin component tracking
            if (plugin_id in self._plugin_components and 
                'panels' in self._plugin_components[plugin_id]):
                self._plugin_components[plugin_id]['panels'].pop(panel_type, None)
                
                # Remove empty categories
                if not self._plugin_components[plugin_id]['panels']:
                    del self._plugin_components[plugin_id]['panels']
                if not self._plugin_components[plugin_id]:
                    del self._plugin_components[plugin_id]
            
            logger.info(f"Unregistered panel factory '{panel_type}' for plugin '{plugin_id}'")
            
        except Exception as e:
            logger.error(f"Failed to unregister panel factory '{panel_type}' for plugin '{plugin_id}': {e}")
    
    def get_panel_factory(self, panel_type: str) -> Optional[PanelFactory]:
        """Get panel factory by panel type.
        
        Args:
            panel_type: Type of panel to create
            
        Returns:
            Panel factory if registered, None otherwise
        """
        return self._panel_factories.get(panel_type)
    
    def get_registered_panel_types(self) -> List[str]:
        """Get list of all registered panel types.
        
        Returns:
            List of registered panel type identifiers
        """
        return list(self._panel_factories.keys())
    
    # Marker Provider Management
    
    def register_marker_provider(self, plugin_id: str, provider: 'MarkerProvider') -> None:
        """Register a marker provider for a plugin.
        
        Args:
            plugin_id: Unique identifier for the plugin
            provider: Marker provider implementation
            
        Raises:
            ValueError: If marker type is already registered
        """
        try:
            marker_type = provider.get_marker_type_id()
            
            if marker_type in self._marker_providers:
                existing_plugin = None
                for pid, components in self._plugin_components.items():
                    if 'markers' in components and marker_type in components['markers']:
                        existing_plugin = pid
                        break
                
                raise ValueError(
                    f"Marker type '{marker_type}' already registered by plugin '{existing_plugin}'"
                )
            
            self._marker_providers[marker_type] = provider
            
            # Track plugin components for cleanup
            if plugin_id not in self._plugin_components:
                self._plugin_components[plugin_id] = {}
            if 'markers' not in self._plugin_components[plugin_id]:
                self._plugin_components[plugin_id]['markers'] = {}
            self._plugin_components[plugin_id]['markers'][marker_type] = provider
            
            logger.info(f"Registered marker provider '{marker_type}' for plugin '{plugin_id}'")
            
        except Exception as e:
            logger.error(f"Failed to register marker provider for plugin '{plugin_id}': {e}")
            raise
    
    def unregister_marker_provider(self, plugin_id: str, marker_type: str) -> None:
        """Unregister a marker provider for a plugin.
        
        Args:
            plugin_id: Plugin identifier  
            marker_type: Marker type to unregister
        """
        try:
            if marker_type in self._marker_providers:
                del self._marker_providers[marker_type]
            
            # Clean up plugin component tracking
            if (plugin_id in self._plugin_components and 
                'markers' in self._plugin_components[plugin_id]):
                self._plugin_components[plugin_id]['markers'].pop(marker_type, None)
                
                # Remove empty categories
                if not self._plugin_components[plugin_id]['markers']:
                    del self._plugin_components[plugin_id]['markers']
                if not self._plugin_components[plugin_id]:
                    del self._plugin_components[plugin_id]
            
            logger.info(f"Unregistered marker provider '{marker_type}' for plugin '{plugin_id}'")
            
        except Exception as e:
            logger.error(f"Failed to unregister marker provider '{marker_type}' for plugin '{plugin_id}': {e}")
    
    def get_marker_provider(self, marker_type: str) -> Optional['MarkerProvider']:
        """Get marker provider by marker type.
        
        Args:
            marker_type: Type of marker provider to get
            
        Returns:
            Marker provider if registered, None otherwise
        """
        return self._marker_providers.get(marker_type)
    
    def get_all_marker_providers(self) -> List['MarkerProvider']:
        """Get all registered marker providers.
        
        Returns:
            List of all registered marker providers
        """
        return list(self._marker_providers.values())
    
    def get_registered_marker_types(self) -> List[str]:
        """Get list of all registered marker types.
        
        Returns:
            List of registered marker type identifiers
        """
        return list(self._marker_providers.keys())
    
    # Plugin Capability Management
    
    def register_plugin_capability(self, plugin_id: str, capability: str) -> None:
        """Register a UI capability for a plugin.
        
        Args:
            plugin_id: Plugin identifier
            capability: UI capability name (e.g., "heading_filter", "style_toggle")
        """
        if plugin_id not in self._plugin_capabilities:
            self._plugin_capabilities[plugin_id] = []
        
        if capability not in self._plugin_capabilities[plugin_id]:
            self._plugin_capabilities[plugin_id].append(capability)
            logger.info(f"Registered capability '{capability}' for plugin '{plugin_id}'. All capabilities: {self._plugin_capabilities}")
        else:
            logger.debug(f"Capability '{capability}' already registered for plugin '{plugin_id}'")
    
    def unregister_plugin_capability(self, plugin_id: str, capability: str) -> None:
        """Unregister a UI capability for a plugin.
        
        Args:
            plugin_id: Plugin identifier
            capability: UI capability name to remove
        """
        if plugin_id in self._plugin_capabilities:
            if capability in self._plugin_capabilities[plugin_id]:
                self._plugin_capabilities[plugin_id].remove(capability)
                logger.info(f"Unregistered capability '{capability}' for plugin '{plugin_id}'")
            
            # Remove empty capability lists
            if not self._plugin_capabilities[plugin_id]:
                del self._plugin_capabilities[plugin_id]
    
    def plugin_has_capability(self, plugin_id: str, capability: str) -> bool:
        """Check if a plugin has a specific UI capability.
        
        Args:
            plugin_id: Plugin identifier
            capability: UI capability to check
            
        Returns:
            True if plugin has the capability, False otherwise
        """
        result = capability in self._plugin_capabilities.get(plugin_id, [])
        logger.debug(f"Plugin capability check: plugin='{plugin_id}', capability='{capability}', result={result}, all_capabilities={self._plugin_capabilities}")
        return result
    
    def get_plugin_capabilities(self, plugin_id: str) -> List[str]:
        """Get all UI capabilities for a plugin.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            List of capability names
        """
        return self._plugin_capabilities.get(plugin_id, []).copy()
    
    # Cleanup Management
    
    def add_cleanup_callback(self, plugin_id: str, callback: Callable[[], None]) -> None:
        """Add cleanup callback for plugin components.
        
        Args:
            plugin_id: Plugin identifier
            callback: Cleanup function to call when plugin is deactivated
        """
        if plugin_id not in self._component_cleanup:
            self._component_cleanup[plugin_id] = []
        self._component_cleanup[plugin_id].append(callback)
    
    def cleanup_plugin_components(self, plugin_id: str) -> None:
        """Clean up all components for a plugin.
        
        This method is called when a plugin is deactivated or unloaded.
        It ensures all plugin UI components are properly cleaned up and
        removed from the registry.
        
        Args:
            plugin_id: Plugin identifier to clean up
        """
        try:
            # Execute cleanup callbacks
            if plugin_id in self._component_cleanup:
                for callback in self._component_cleanup[plugin_id]:
                    try:
                        callback()
                    except Exception as e:
                        logger.error(f"Error in cleanup callback for plugin '{plugin_id}': {e}")
                del self._component_cleanup[plugin_id]
            
            # Unregister all plugin components
            if plugin_id in self._plugin_components:
                components = self._plugin_components[plugin_id]
                
                # Clean up panel factories
                if 'panels' in components:
                    for panel_type in list(components['panels'].keys()):
                        self.unregister_panel_factory(panel_type, plugin_id)
                
                # Clean up marker providers
                if 'markers' in components:
                    for marker_type in list(components['markers'].keys()):
                        self.unregister_marker_provider(plugin_id, marker_type)
                
                # Remove plugin from tracking
                if plugin_id in self._plugin_components:
                    del self._plugin_components[plugin_id]
                
                # Clean up plugin capabilities
                if plugin_id in self._plugin_capabilities:
                    del self._plugin_capabilities[plugin_id]
            
            logger.info(f"Cleaned up all UI components for plugin '{plugin_id}'")
            
        except Exception as e:
            logger.error(f"Error cleaning up components for plugin '{plugin_id}': {e}")
    
    def cleanup_all_components(self) -> None:
        """Clean up all registered components.
        
        This method is called during application shutdown to ensure
        proper cleanup of all plugin UI components.
        """
        try:
            plugin_ids = list(self._plugin_components.keys())
            for plugin_id in plugin_ids:
                self.cleanup_plugin_components(plugin_id)
            
            # Clear all registries
            self._panel_factories.clear()
            self._marker_providers.clear()
            self._plugin_components.clear()
            self._component_cleanup.clear()
            self._plugin_capabilities.clear()
            
            logger.info("Cleaned up all UI registry components")
            
        except Exception as e:
            logger.error(f"Error during UI registry cleanup: {e}")
    
    # Information and Debugging
    
    def get_component_info(self) -> Dict[str, Any]:
        """Get information about registered components.
        
        Returns:
            Dictionary with component registration information
        """
        return {
            'panel_factories': {
                panel_type: {
                    'display_name': factory.get_display_name(),
                    'class': factory.__class__.__name__
                }
                for panel_type, factory in self._panel_factories.items()
            },
            'marker_providers': {
                marker_type: {
                    'priority': provider.get_marker_priority(),
                    'class': provider.__class__.__name__
                }
                for marker_type, provider in self._marker_providers.items()
            },
            'plugin_components': dict(self._plugin_components)
        }
    
    def get_plugin_components(self, plugin_id: str) -> Dict[str, Any]:
        """Get components registered by a specific plugin.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            Dictionary of components registered by the plugin
        """
        return self._plugin_components.get(plugin_id, {})


# Import MarkerProvider 
from orlando_toolkit.core.plugins.marker_providers import MarkerProvider