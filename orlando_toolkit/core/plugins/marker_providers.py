from __future__ import annotations

"""Marker Provider interface and registry system.

This module defines the MarkerProvider interface that plugins can implement
to provide custom marker types for the scrollbar marker system in the
StructureTreeWidget. It also includes a registry for managing multiple
marker providers and coordinating their interactions.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class MarkerProvider(Protocol):
    """Protocol for plugin-provided marker types.
    
    Plugins implement this protocol to provide custom marker types that
    can be displayed in the scrollbar marker zone of the StructureTreeWidget.
    Each marker provider is responsible for determining which items should
    show markers and what visual properties those markers should have.
    """
    
    def get_marker_type_id(self) -> str:
        """Return unique identifier for this marker type.
        
        Returns:
            Unique string identifier for this marker type
            
        Note:
            This ID must be unique across all marker providers and should
            be descriptive of the marker's purpose (e.g., "docx_style",
            "validation_error", "custom_annotation").
        """
        ...
    
    def should_show_marker(self, item_data: Dict[str, Any]) -> bool:
        """Return True if marker should be shown for this item.
        
        Args:
            item_data: Dictionary containing item information including:
                - 'topic_ref': Reference to the topic/item
                - 'style': Style information if available  
                - 'data': Additional data context
                - Other provider-specific fields
        
        Returns:
            True if this provider should show a marker for the item
            
        Note:
            This method should be fast as it may be called frequently
            during tree updates and scrolling operations.
        """
        ...
    
    def get_marker_color(self, item_data: Dict[str, Any]) -> str:
        """Return hex color for this item's marker.
        
        Args:
            item_data: Dictionary containing item information
            
        Returns:
            Hex color string (e.g., "#FF0000") for the marker
            
        Note:
            This method is only called if should_show_marker returns True.
            The color should be a valid CSS hex color string.
        """
        ...
    
    def get_marker_priority(self) -> int:
        """Return priority for marker layering.
        
        Returns:
            Integer priority value (higher = more visible)
            
        Note:
            When multiple markers apply to the same item, they are layered
            based on priority. Higher priority markers are rendered on top
            or given visual precedence. Standard priorities:
            - Core markers (search, filter): 100-199
            - Style markers: 200-299  
            - Plugin markers: 300+
        """
        ...
    
    def get_display_name(self) -> str:
        """Return human-readable display name for this marker type.
        
        Returns:
            Display name for UI elements (tooltips, legends, etc.)
        """
        ...
    
    def is_enabled(self) -> bool:
        """Return True if this marker provider is currently enabled.
        
        Returns:
            True if markers should be shown, False to hide all markers
            
        Note:
            This allows marker providers to be temporarily disabled
            without unregistering them from the system.
        """
        ...


class MarkerProviderBase(ABC):
    """Abstract base class for MarkerProvider implementations.
    
    Provides common functionality and ensures proper interface implementation
    for marker providers. Plugin developers should inherit from this class
    to create marker provider implementations.
    """
    
    def __init__(self, marker_type_id: str, display_name: str, priority: int = 300) -> None:
        """Initialize the marker provider.
        
        Args:
            marker_type_id: Unique identifier for this marker type
            display_name: Human-readable name for this marker type
            priority: Marker priority (default 300 for plugin markers)
        """
        self._marker_type_id = marker_type_id
        self._display_name = display_name
        self._priority = priority
        self._enabled = True
    
    def get_marker_type_id(self) -> str:
        """Return unique identifier for this marker type."""
        return self._marker_type_id
    
    def get_display_name(self) -> str:
        """Return human-readable display name for this marker type."""
        return self._display_name
    
    def get_marker_priority(self) -> int:
        """Return priority for marker layering."""
        return self._priority
    
    def is_enabled(self) -> bool:
        """Return True if this marker provider is currently enabled."""
        return self._enabled
    
    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable this marker provider.
        
        Args:
            enabled: True to enable, False to disable
        """
        self._enabled = enabled
    
    @abstractmethod
    def should_show_marker(self, item_data: Dict[str, Any]) -> bool:
        """Return True if marker should be shown for this item."""
        pass
    
    @abstractmethod
    def get_marker_color(self, item_data: Dict[str, Any]) -> str:
        """Return hex color for this item's marker."""
        pass


class StyleMarkerProvider(MarkerProviderBase):
    """Built-in marker provider for style-based markers.
    
    This marker provider creates markers based on style information
    in the item data. It supports style visibility settings and 
    color configuration for different styles.
    """
    
    def __init__(self) -> None:
        """Initialize the style marker provider."""
        super().__init__(
            marker_type_id="style_marker",
            display_name="Style Markers", 
            priority=250  # Between core and plugin markers
        )
        self._style_visibility: Dict[str, bool] = {}
        self._style_colors: Dict[str, str] = {}
    
    def should_show_marker(self, item_data: Dict[str, Any]) -> bool:
        """Return True if marker should be shown for this item."""
        if not self._enabled:
            return False
        
        style = item_data.get('style')
        if not style or not isinstance(style, str):
            return False
        
        # Check if this style should be visible
        return self._style_visibility.get(style, False)
    
    def get_marker_color(self, item_data: Dict[str, Any]) -> str:
        """Return hex color for this item's marker."""
        style = item_data.get('style', '')
        return self._style_colors.get(style, '#808080')  # Default gray
    
    def set_style_visibility(self, style_visibility: Dict[str, bool]) -> None:
        """Set which styles should show markers.
        
        Args:
            style_visibility: Dict mapping style names to visibility flags
        """
        self._style_visibility = dict(style_visibility or {})
    
    def set_style_colors(self, style_colors: Dict[str, str]) -> None:
        """Set colors for different styles.
        
        Args:
            style_colors: Dict mapping style names to hex colors
        """
        self._style_colors = dict(style_colors or {})
    
    def get_style_visibility(self) -> Dict[str, bool]:
        """Get current style visibility settings."""
        return dict(self._style_visibility)
    
    def get_style_colors(self) -> Dict[str, str]:
        """Get current style color settings."""
        return dict(self._style_colors)


class MarkerProviderRegistry:
    """Registry for managing multiple marker providers.
    
    This registry coordinates multiple marker providers and handles
    priority-based layering of markers when multiple providers apply
    to the same item.
    """
    
    def __init__(self) -> None:
        """Initialize the marker provider registry."""
        self._providers: Dict[str, MarkerProvider] = {}
        self._style_provider: Optional[StyleMarkerProvider] = None
        self._setup_built_in_providers()
    
    def _setup_built_in_providers(self) -> None:
        """Set up built-in marker providers."""
        # Register the built-in style marker provider
        self._style_provider = StyleMarkerProvider()
        self._providers[self._style_provider.get_marker_type_id()] = self._style_provider
    
    def register_provider(self, provider: MarkerProvider) -> None:
        """Register a marker provider.
        
        Args:
            provider: Marker provider to register
            
        Raises:
            ValueError: If marker type ID is already registered
        """
        try:
            marker_type = provider.get_marker_type_id()
            
            if marker_type in self._providers:
                raise ValueError(f"Marker type '{marker_type}' is already registered")
            
            self._providers[marker_type] = provider
            logger.info(f"Registered marker provider '{marker_type}'")
            
        except Exception as e:
            logger.error(f"Failed to register marker provider: {e}")
            raise
    
    def unregister_provider(self, marker_type: str) -> None:
        """Unregister a marker provider by type ID.
        
        Args:
            marker_type: Marker type ID to unregister
        """
        try:
            if marker_type in self._providers:
                del self._providers[marker_type]
                logger.info(f"Unregistered marker provider '{marker_type}'")
            
        except Exception as e:
            logger.error(f"Failed to unregister marker provider '{marker_type}': {e}")
    
    def get_provider(self, marker_type: str) -> Optional[MarkerProvider]:
        """Get marker provider by type ID.
        
        Args:
            marker_type: Marker type ID to get
            
        Returns:
            Marker provider if registered, None otherwise
        """
        return self._providers.get(marker_type)
    
    def get_all_providers(self) -> List[MarkerProvider]:
        """Get all registered marker providers.
        
        Returns:
            List of all registered marker providers sorted by priority
        """
        return sorted(self._providers.values(), key=lambda p: p.get_marker_priority())
    
    def get_enabled_providers(self) -> List[MarkerProvider]:
        """Get all enabled marker providers.
        
        Returns:
            List of enabled marker providers sorted by priority
        """
        return [p for p in self.get_all_providers() if p.is_enabled()]
    
    def get_markers_for_item(self, item_data: Dict[str, Any]) -> List[tuple[MarkerProvider, str]]:
        """Get all applicable markers for an item.
        
        Args:
            item_data: Dictionary containing item information
            
        Returns:
            List of (provider, color) tuples for markers that should be shown
        """
        markers = []
        
        try:
            for provider in self.get_enabled_providers():
                try:
                    if provider.should_show_marker(item_data):
                        color = provider.get_marker_color(item_data)
                        markers.append((provider, color))
                except Exception as e:
                    logger.error(f"Error checking marker for provider '{provider.get_marker_type_id()}': {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Error getting markers for item: {e}")
        
        return markers
    
    def get_style_provider(self) -> Optional[StyleMarkerProvider]:
        """Get the built-in style marker provider.
        
        Returns:
            Style marker provider instance
        """
        return self._style_provider
    
    def clear_all_providers(self) -> None:
        """Clear all registered providers."""
        try:
            self._providers.clear()
            self._style_provider = None
            self._setup_built_in_providers()
            logger.info("Cleared all marker providers")
            
        except Exception as e:
            logger.error(f"Error clearing marker providers: {e}")
    
    def get_registry_info(self) -> Dict[str, Any]:
        """Get information about registered providers.
        
        Returns:
            Dictionary with provider registration information
        """
        return {
            'providers': {
                marker_type: {
                    'display_name': provider.get_display_name(),
                    'priority': provider.get_marker_priority(),
                    'enabled': provider.is_enabled(),
                    'class': provider.__class__.__name__
                }
                for marker_type, provider in self._providers.items()
            },
            'total_providers': len(self._providers),
            'enabled_providers': len(self.get_enabled_providers())
        }


# Global registry instance
_marker_registry = MarkerProviderRegistry()


def get_marker_registry() -> MarkerProviderRegistry:
    """Get the global marker provider registry.
    
    Returns:
        Global MarkerProviderRegistry instance
    """
    return _marker_registry