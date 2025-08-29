from __future__ import annotations

"""Plugin system foundation for Orlando Toolkit.

This package provides the core plugin system infrastructure including:
- Plugin discovery and loading
- Service registry and type-safe service resolution  
- Plugin lifecycle management
- Plugin metadata validation
- Error boundaries and exception handling

The plugin system is designed to support pipeline plugins that convert
external document formats to DITA archives while maintaining application
stability and extensibility.
"""

from .base import BasePlugin, AppContext
from .exceptions import (
    PluginError,
    PluginLoadError,
    PluginValidationError,
    UnsupportedFormatError,
    ServiceRegistrationError,
    PluginInstallationError,
    PluginRemovalError,
    PluginDownloadError,
    PluginDependencyError,
    PluginSecurityError,
    PluginStateError,
)
from .loader import PluginLoader, PluginInfo
from .registry import ServiceRegistry, get_all_official_plugins, get_official_plugin_info, is_official_plugin
from .metadata import PluginMetadata, validate_plugin_metadata
from .manager import PluginManager, PluginInstallResult
from .downloader import GitHubPluginDownloader, DownloadResult
from .installer import PluginInstaller
from .interfaces import DocumentHandler, DocumentHandlerBase, UIExtension
from .models import FileFormat, ConversionResult, PluginCapabilities

__all__ = [
    # Core classes
    "BasePlugin",
    "AppContext",
    "PluginLoader",
    "PluginInfo",
    "ServiceRegistry",
    "PluginManager",
    "PluginInstaller",
    "GitHubPluginDownloader",
    
    # Interfaces and base classes
    "DocumentHandler",
    "DocumentHandlerBase", 
    "UIExtension",
    
    # Data models
    "PluginMetadata",
    "FileFormat",
    "ConversionResult",
    "PluginCapabilities",
    "PluginInstallResult",
    "DownloadResult",
    
    # Exceptions
    "PluginError", 
    "PluginLoadError",
    "PluginValidationError",
    "UnsupportedFormatError",
    "ServiceRegistrationError",
    "PluginInstallationError",
    "PluginRemovalError",
    "PluginDownloadError",
    "PluginDependencyError",
    "PluginSecurityError",
    "PluginStateError",
    
    # Utility functions
    "validate_plugin_metadata",
    "get_all_official_plugins",
    "get_official_plugin_info",
    "is_official_plugin",
]