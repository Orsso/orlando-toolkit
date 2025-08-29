from __future__ import annotations

"""Plugin system exception classes.

Provides comprehensive error handling for plugin operations including
loading, validation, service registration, and runtime errors.
All plugin exceptions are designed to be caught and handled gracefully
without crashing the main application.
"""

from typing import Optional, Any


class PluginError(Exception):
    """Base exception for all plugin-related errors.
    
    All plugin exceptions inherit from this base class to enable
    comprehensive error handling and logging.
    """
    
    def __init__(self, message: str, plugin_id: Optional[str] = None, 
                 cause: Optional[Exception] = None) -> None:
        super().__init__(message)
        self.plugin_id = plugin_id
        self.cause = cause
    
    def __str__(self) -> str:
        if self.plugin_id:
            return f"[Plugin: {self.plugin_id}] {super().__str__()}"
        return super().__str__()


class PluginLoadError(PluginError):
    """Raised when a plugin fails to load or import.
    
    This includes Python import errors, missing entry points,
    and plugin initialization failures.
    """
    pass


class PluginValidationError(PluginError):
    """Raised when plugin metadata or structure is invalid.
    
    This includes JSON schema validation failures, missing required
    files, and incompatible plugin configurations.
    """
    
    def __init__(self, message: str, plugin_id: Optional[str] = None,
                 validation_errors: Optional[list[str]] = None,
                 cause: Optional[Exception] = None) -> None:
        super().__init__(message, plugin_id, cause)
        self.validation_errors = validation_errors or []


class UnsupportedFormatError(PluginError):
    """Raised when no plugin can handle a specific file format.
    
    This occurs when trying to convert a file type that no
    registered plugin supports.
    """
    
    def __init__(self, file_path: str, available_formats: Optional[list[str]] = None) -> None:
        self.file_path = file_path
        self.available_formats = available_formats or []
        
        if self.available_formats:
            formats_str = ", ".join(self.available_formats)
            message = f"No plugin can handle file '{file_path}'. Supported formats: {formats_str}"
        else:
            message = f"No plugin can handle file '{file_path}'. No plugins are currently loaded."
            
        super().__init__(message)


class ServiceRegistrationError(PluginError):
    """Raised when plugin service registration fails.
    
    This includes duplicate service registrations, invalid service
    implementations, and service registry conflicts.
    """
    
    def __init__(self, message: str, plugin_id: Optional[str] = None,
                 service_type: Optional[str] = None,
                 cause: Optional[Exception] = None) -> None:
        super().__init__(message, plugin_id, cause)
        self.service_type = service_type


class PluginDependencyError(PluginError):
    """Raised when plugin dependencies cannot be resolved.
    
    This includes missing Python packages, version conflicts,
    and Orlando Toolkit compatibility issues.
    """
    
    def __init__(self, message: str, plugin_id: Optional[str] = None,
                 missing_dependencies: Optional[list[str]] = None,
                 cause: Optional[Exception] = None) -> None:
        super().__init__(message, plugin_id, cause)
        self.missing_dependencies = missing_dependencies or []


class PluginSecurityError(PluginError):
    """Raised when a plugin violates security policies.
    
    This includes permission violations, malicious code detection,
    and sandbox escape attempts.
    """
    
    def __init__(self, message: str, plugin_id: Optional[str] = None,
                 violation_type: Optional[str] = None,
                 cause: Optional[Exception] = None) -> None:
        super().__init__(message, plugin_id, cause)
        self.violation_type = violation_type


class PluginStateError(PluginError):
    """Raised when plugin state transitions are invalid.
    
    This includes attempting operations on plugins in wrong states
    (e.g., activating a plugin that failed to load).
    """
    
    def __init__(self, message: str, plugin_id: Optional[str] = None,
                 current_state: Optional[str] = None,
                 expected_state: Optional[str] = None,
                 cause: Optional[Exception] = None) -> None:
        super().__init__(message, plugin_id, cause)
        self.current_state = current_state
        self.expected_state = expected_state


class PluginInstallationError(PluginError):
    """Raised when plugin installation fails.
    
    This includes download failures, dependency installation failures,
    and file copying errors during plugin installation.
    """
    pass


class PluginRemovalError(PluginError):
    """Raised when plugin removal fails.
    
    This includes errors during plugin uninstallation and cleanup
    operations.
    """
    pass


class PluginDownloadError(PluginError):
    """Raised when plugin download from repository fails.
    
    This includes network errors, invalid repository URLs,
    and GitHub API failures.
    """
    
    def __init__(self, message: str, repository_url: Optional[str] = None,
                 cause: Optional[Exception] = None) -> None:
        super().__init__(message, cause=cause)
        self.repository_url = repository_url