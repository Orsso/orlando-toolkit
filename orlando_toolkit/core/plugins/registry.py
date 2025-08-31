from __future__ import annotations

"""Service registry for plugin system.

Provides type-safe service registration and resolution for plugins.
The ServiceRegistry manages DocumentHandler registration and other
plugin services while maintaining isolation between plugins.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Type, TypeVar, Generic, Any, Protocol
from threading import RLock

from .exceptions import ServiceRegistrationError, UnsupportedFormatError
from .interfaces import DocumentHandler

logger = logging.getLogger(__name__)

T = TypeVar('T')


# -------------------------------------------------------------------------
# Service Registry - Pure Discovery Model
# -------------------------------------------------------------------------




class ServiceRegistry:
    """Type-safe service registry for plugin system.
    
    Manages registration and resolution of plugin services including
    DocumentHandlers, UI extensions, and other plugin-provided services.
    Provides thread-safe operations and plugin isolation.
    """
    
    def __init__(self) -> None:
        self._document_handlers: Dict[str, DocumentHandler] = {}
        self._handler_plugins: Dict[DocumentHandler, str] = {}  # handler -> plugin_id
        self._plugin_services: Dict[str, Dict[str, Any]] = {}
        self._service_plugins: Dict[str, str] = {}  # service_id -> plugin_id
        self._lock = RLock()
        self._logger = logging.getLogger(f"{__name__}.ServiceRegistry")
    
    # -------------------------------------------------------------------------
    # DocumentHandler Registration
    # -------------------------------------------------------------------------
    
    def register_document_handler(self, handler: DocumentHandler, plugin_id: str) -> None:
        """Register a document converter from a pipeline plugin.
        
        Args:
            handler: DocumentHandler implementation
            plugin_id: ID of the plugin providing the handler
            
        Raises:
            ServiceRegistrationError: If registration fails
        """
        with self._lock:
            try:
                # Validate handler implements required methods
                if not self._validate_document_handler(handler):
                    raise ServiceRegistrationError(
                        "DocumentHandler does not implement required methods",
                        plugin_id=plugin_id,
                        service_type="DocumentHandler"
                    )
                
                # Get supported extensions for conflict checking
                try:
                    extensions = handler.get_supported_extensions()
                except Exception as e:
                    raise ServiceRegistrationError(
                        f"Failed to get supported extensions from handler: {e}",
                        plugin_id=plugin_id,
                        service_type="DocumentHandler",
                        cause=e
                    )
                
                # Check for extension conflicts
                conflicts = self._check_extension_conflicts(extensions)
                if conflicts:
                    existing_plugins = [self._service_plugins.get(h_id, "unknown") 
                                      for h_id in conflicts]
                    raise ServiceRegistrationError(
                        f"Extension conflicts with existing handlers: {conflicts} "
                        f"(plugins: {existing_plugins})",
                        plugin_id=plugin_id,
                        service_type="DocumentHandler"
                    )
                
                # Generate unique handler ID
                handler_id = f"{plugin_id}_document_handler"
                
                # Register handler
                self._document_handlers[handler_id] = handler
                self._service_plugins[handler_id] = plugin_id
                
                # Store handler -> plugin mapping for lookup
                self._handler_plugins[handler] = plugin_id
                
                # Register in plugin services dict
                if plugin_id not in self._plugin_services:
                    self._plugin_services[plugin_id] = {}
                self._plugin_services[plugin_id]["DocumentHandler"] = handler_id
                
                self._logger.info("Registered DocumentHandler from plugin %s (extensions: %s)",
                                plugin_id, extensions)
                
            except ServiceRegistrationError:
                raise
            except Exception as e:
                raise ServiceRegistrationError(
                    f"Unexpected error during DocumentHandler registration: {e}",
                    plugin_id=plugin_id,
                    service_type="DocumentHandler",
                    cause=e
                )
    
    def unregister_document_handler(self, plugin_id: str) -> bool:
        """Unregister DocumentHandler from a plugin.
        
        Args:
            plugin_id: ID of the plugin to unregister
            
        Returns:
            True if handler was found and removed, False otherwise
        """
        with self._lock:
            handler_id = f"{plugin_id}_document_handler"
            
            removed = False
            if handler_id in self._document_handlers:
                handler = self._document_handlers[handler_id]
                
                # Clean up handler -> plugin mapping
                if handler in self._handler_plugins:
                    del self._handler_plugins[handler]
                
                del self._document_handlers[handler_id]
                del self._service_plugins[handler_id]
                removed = True
            
            if plugin_id in self._plugin_services:
                self._plugin_services[plugin_id].pop("DocumentHandler", None)
                if not self._plugin_services[plugin_id]:
                    del self._plugin_services[plugin_id]
            
            if removed:
                self._logger.info("Unregistered DocumentHandler from plugin %s", plugin_id)
            
            return removed
    
    def get_document_handlers(self) -> List[DocumentHandler]:
        """Get all registered document handlers.
        
        Returns:
            List of all registered DocumentHandler instances
        """
        with self._lock:
            return list(self._document_handlers.values())
    
    def get_plugin_for_handler(self, handler: DocumentHandler) -> Optional[str]:
        """Get the plugin ID that registered a specific handler.
        
        Args:
            handler: DocumentHandler instance to look up
            
        Returns:
            Plugin ID that registered the handler, or None if not found
        """
        with self._lock:
            return self._handler_plugins.get(handler)
    
    def find_handler_for_file(self, file_path: Path) -> Optional[DocumentHandler]:
        """Find compatible handler for a specific file.
        
        Args:
            file_path: Path to file that needs handling
            
        Returns:
            Compatible DocumentHandler or None if no handler found
        """
        with self._lock:
            for handler in self._document_handlers.values():
                try:
                    if handler.can_handle(file_path):
                        return handler
                except Exception as e:
                    # Log error but continue trying other handlers
                    plugin_id = self._get_plugin_for_handler(handler)
                    self._logger.warning(
                        "Handler from plugin %s failed can_handle() check: %s",
                        plugin_id, e
                    )
                    continue
            
            return None
    
    def get_supported_formats(self) -> List[Dict[str, str]]:
        """Get all supported file formats from registered handlers.
        
        Returns:
            List of format dictionaries with 'extension' and 'description' keys
        """
        with self._lock:
            formats = []
            
            for handler in self._document_handlers.values():
                try:
                    extensions = handler.get_supported_extensions()
                    for ext in extensions:
                        # Try to get format description from plugin metadata
                        plugin_id = self._get_plugin_for_handler(handler)
                        description = f"Handled by {plugin_id}"
                        
                        formats.append({
                            'extension': ext,
                            'description': description,
                            'plugin_id': plugin_id
                        })
                except Exception as e:
                    plugin_id = self._get_plugin_for_handler(handler)
                    self._logger.warning(
                        "Failed to get formats from plugin %s: %s",
                        plugin_id, e
                    )
                    continue
            
            return formats
    
    # -------------------------------------------------------------------------
    # General Service Registration
    # -------------------------------------------------------------------------
    
    def register_service(self, service_type: str, service_instance: Any, 
                        plugin_id: str) -> None:
        """Register a general service from a plugin.
        
        Args:
            service_type: Type/category of service
            service_instance: Service instance
            plugin_id: ID of the plugin providing the service
            
        Raises:
            ServiceRegistrationError: If registration fails
        """
        # Route DocumentHandler to specialized registration method
        if service_type == "DocumentHandler":
            self.register_document_handler(service_instance, plugin_id)
            return
            
        with self._lock:
            try:
                service_id = f"{plugin_id}_{service_type.lower()}"
                
                # Check for conflicts
                if service_id in self._service_plugins:
                    existing_plugin = self._service_plugins[service_id]
                    raise ServiceRegistrationError(
                        f"Service {service_type} already registered by plugin {existing_plugin}",
                        plugin_id=plugin_id,
                        service_type=service_type
                    )
                
                # Register service
                if plugin_id not in self._plugin_services:
                    self._plugin_services[plugin_id] = {}
                
                self._plugin_services[plugin_id][service_type] = service_instance
                self._service_plugins[service_id] = plugin_id
                
                self._logger.debug("Registered %s service from plugin %s",
                                 service_type, plugin_id)
                
            except ServiceRegistrationError:
                raise
            except Exception as e:
                raise ServiceRegistrationError(
                    f"Unexpected error during service registration: {e}",
                    plugin_id=plugin_id,
                    service_type=service_type,
                    cause=e
                )
    
    def unregister_service(self, service_type: str, plugin_id: str) -> bool:
        """Unregister a specific service from a plugin.
        
        Args:
            service_type: Type of service to unregister
            plugin_id: Plugin ID
            
        Returns:
            True if service was found and removed
        """
        if service_type == "DocumentHandler":
            return self.unregister_document_handler(plugin_id)
        return False
    
    def unregister_plugin_services(self, plugin_id: str) -> None:
        """Unregister all services from a plugin.
        
        Args:
            plugin_id: ID of the plugin to unregister
        """
        with self._lock:
            # Remove from plugin services
            if plugin_id in self._plugin_services:
                services = self._plugin_services[plugin_id]
                del self._plugin_services[plugin_id]
                
                # Remove from service -> plugin mapping
                to_remove = []
                for service_id, p_id in self._service_plugins.items():
                    if p_id == plugin_id:
                        to_remove.append(service_id)
                
                for service_id in to_remove:
                    del self._service_plugins[service_id]
                
                # Remove document handlers
                handler_id = f"{plugin_id}_document_handler"
                self._document_handlers.pop(handler_id, None)
                
                self._logger.info("Unregistered all services from plugin %s: %s",
                                plugin_id, list(services.keys()))
    
    def get_service(self, service_type: str, plugin_id: Optional[str] = None) -> Optional[Any]:
        """Get a registered service instance.
        
        Args:
            service_type: Type of service to retrieve
            plugin_id: Specific plugin ID, or None for any plugin
            
        Returns:
            Service instance or None if not found
        """
        with self._lock:
            if plugin_id:
                # Get service from specific plugin
                plugin_services = self._plugin_services.get(plugin_id, {})
                return plugin_services.get(service_type)
            else:
                # Get service from any plugin (first match)
                for plugin_services in self._plugin_services.values():
                    if service_type in plugin_services:
                        return plugin_services[service_type]
                return None
    
    def get_services_by_type(self, service_type: Type[T]) -> List[T]:
        """Get all services of a specific type.
        
        Args:
            service_type: Type of service to retrieve
            
        Returns:
            List of matching service instances
        """
        with self._lock:
            services = []
            type_name = service_type.__name__
            
            for plugin_services in self._plugin_services.values():
                for s_type, service_instance in plugin_services.items():
                    if s_type == type_name or isinstance(service_instance, service_type):
                        services.append(service_instance)
            
            return services
    
    # -------------------------------------------------------------------------
    # Plugin Management
    # -------------------------------------------------------------------------
    
    def get_plugin_services(self, plugin_id: str) -> Dict[str, Any]:
        """Get all services registered by a plugin.
        
        Args:
            plugin_id: Plugin ID
            
        Returns:
            Dictionary of service_type -> service_instance
        """
        with self._lock:
            return self._plugin_services.get(plugin_id, {}).copy()
    
    def is_plugin_registered(self, plugin_id: str) -> bool:
        """Check if a plugin has registered any services.
        
        Args:
            plugin_id: Plugin ID
            
        Returns:
            True if plugin has registered services
        """
        with self._lock:
            return plugin_id in self._plugin_services
    
    def get_registered_plugins(self) -> List[str]:
        """Get list of all plugins that have registered services.
        
        Returns:
            List of plugin IDs
        """
        with self._lock:
            return list(self._plugin_services.keys())
    
    # -------------------------------------------------------------------------
    # Internal Helper Methods
    # -------------------------------------------------------------------------
    
    def _validate_document_handler(self, handler: DocumentHandler) -> bool:
        """Validate that handler implements required methods."""
        required_methods = ['can_handle', 'convert_to_dita', 
                           'get_supported_extensions', 'get_conversion_metadata_schema']
        
        for method_name in required_methods:
            if not hasattr(handler, method_name):
                return False
            method = getattr(handler, method_name)
            if not callable(method):
                return False
        
        return True
    
    def _check_extension_conflicts(self, extensions: List[str]) -> List[str]:
        """Check for extension conflicts with existing handlers."""
        conflicts = []
        
        for handler_id, handler in self._document_handlers.items():
            try:
                existing_extensions = handler.get_supported_extensions()
                for ext in extensions:
                    if ext in existing_extensions:
                        conflicts.append(handler_id)
                        break
            except Exception:
                # Ignore errors in existing handlers
                continue
        
        return conflicts
    
    def _get_plugin_for_handler(self, handler: DocumentHandler) -> str:
        """Get plugin ID for a given handler instance."""
        for handler_id, h in self._document_handlers.items():
            if h is handler:
                return self._service_plugins.get(handler_id, "unknown")
        return "unknown"
    
    # -------------------------------------------------------------------------
    # Statistics and Debugging
    # -------------------------------------------------------------------------
    
    def get_registry_stats(self) -> Dict[str, Any]:
        """Get registry statistics for debugging.
        
        Returns:
            Dictionary with registry statistics
        """
        with self._lock:
            return {
                'document_handlers': len(self._document_handlers),
                'registered_plugins': len(self._plugin_services),
                'total_services': sum(len(services) for services in self._plugin_services.values()),
                'plugin_service_counts': {
                    plugin_id: len(services) 
                    for plugin_id, services in self._plugin_services.items()
                }
            }
    
    def clear_registry(self) -> None:
        """Clear all registered services (for testing/cleanup).
        
        WARNING: This removes all registered services and should only
        be used during testing or application shutdown.
        """
        with self._lock:
            self._document_handlers.clear()
            self._plugin_services.clear()
            self._service_plugins.clear()
            self._logger.info("Service registry cleared")