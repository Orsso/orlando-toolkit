from __future__ import annotations

"""Plugin system data models.

Defines data structures used by the plugin system for representing
file formats, conversion results, and other plugin-related information.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import mimetypes


class ConversionStatus(Enum):
    """Status of a document conversion operation."""
    
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"  # Conversion succeeded but with warnings/issues
    CANCELLED = "cancelled"


@dataclass
class FileFormat:
    """Represents a supported file format.
    
    Used to describe file formats that plugins can handle, including
    metadata about the format and its capabilities.
    """
    
    extension: str  # File extension including dot, e.g., '.docx'
    mime_type: str  # MIME type, e.g., 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    description: str  # Human-readable description, e.g., 'Microsoft Word Document'
    plugin_id: str  # ID of plugin that handles this format
    
    # Optional metadata
    supports_metadata: bool = True  # Whether format supports metadata extraction
    supports_images: bool = True   # Whether format can contain images
    supports_structure: bool = True  # Whether format has hierarchical structure
    
    def __post_init__(self) -> None:
        """Validate format data after initialization."""
        if not self.extension.startswith('.'):
            raise ValueError(f"Extension must start with dot: {self.extension}")
        
        if not self.extension.islower():
            self.extension = self.extension.lower()
        
        # Auto-detect MIME type if not provided or generic
        if not self.mime_type or self.mime_type == 'application/octet-stream':
            detected_mime, _ = mimetypes.guess_type(f"dummy{self.extension}")
            if detected_mime:
                self.mime_type = detected_mime
    
    @classmethod
    def from_extension(cls, extension: str, plugin_id: str, 
                      description: Optional[str] = None) -> 'FileFormat':
        """Create FileFormat from extension with auto-detection.
        
        Args:
            extension: File extension (with or without leading dot)
            plugin_id: Plugin that handles this format
            description: Optional description (auto-generated if not provided)
            
        Returns:
            FileFormat instance with auto-detected metadata
        """
        if not extension.startswith('.'):
            extension = f'.{extension}'
        
        extension = extension.lower()
        
        # Auto-detect MIME type
        mime_type, _ = mimetypes.guess_type(f"dummy{extension}")
        if not mime_type:
            mime_type = 'application/octet-stream'
        
        # Generate description if not provided
        if not description:
            ext_name = extension[1:].upper()  # Remove dot and capitalize
            description = f"{ext_name} file"
        
        return cls(
            extension=extension,
            mime_type=mime_type,
            description=description,
            plugin_id=plugin_id
        )
    
    def matches_file(self, file_path: Path) -> bool:
        """Check if this format matches a file path.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if file extension matches this format
        """
        return file_path.suffix.lower() == self.extension
    
    def __str__(self) -> str:
        return f"{self.description} ({self.extension})"
    
    def __repr__(self) -> str:
        return (f"FileFormat(extension='{self.extension}', "
                f"mime_type='{self.mime_type}', "
                f"description='{self.description}', "
                f"plugin_id='{self.plugin_id}')")


@dataclass
class ConversionResult:
    """Result of a document conversion operation.
    
    Contains the conversion status, resulting DitaContext (if successful),
    and any warnings or errors that occurred during conversion.
    """
    
    status: ConversionStatus
    context: Optional['DitaContext'] = None  # Import avoided to prevent cycles
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Conversion statistics
    conversion_time_seconds: Optional[float] = None
    topics_created: int = 0
    images_processed: int = 0
    
    @property
    def success(self) -> bool:
        """True if conversion was successful."""
        return self.status == ConversionStatus.SUCCESS
    
    @property
    def failed(self) -> bool:
        """True if conversion failed completely."""
        return self.status == ConversionStatus.FAILED
    
    @property
    def has_warnings(self) -> bool:
        """True if conversion has warnings."""
        return len(self.warnings) > 0
    
    @property
    def has_errors(self) -> bool:
        """True if conversion has errors."""
        return len(self.errors) > 0
    
    def add_warning(self, warning: str) -> None:
        """Add a warning message."""
        self.warnings.append(warning)
    
    def add_error(self, error: str) -> None:
        """Add an error message."""
        self.errors.append(error)
    
    def get_summary(self) -> str:
        """Get a summary of the conversion result.
        
        Returns:
            Human-readable summary string
        """
        if self.success:
            summary = f"Conversion successful: {self.topics_created} topics, {self.images_processed} images"
            if self.has_warnings:
                summary += f" ({len(self.warnings)} warnings)"
            return summary
        elif self.failed:
            return f"Conversion failed: {len(self.errors)} errors"
        elif self.status == ConversionStatus.PARTIAL:
            return f"Conversion partially successful: {len(self.warnings)} warnings, {len(self.errors)} errors"
        else:
            return f"Conversion {self.status.value}"
    
    @classmethod
    def success_result(cls, context: 'DitaContext', 
                      topics_created: int = 0, images_processed: int = 0) -> 'ConversionResult':
        """Create a successful conversion result.
        
        Args:
            context: The resulting DitaContext
            topics_created: Number of topics created
            images_processed: Number of images processed
            
        Returns:
            ConversionResult with success status
        """
        return cls(
            status=ConversionStatus.SUCCESS,
            context=context,
            topics_created=topics_created,
            images_processed=images_processed
        )
    
    @classmethod
    def failure_result(cls, error: str, **metadata: Any) -> 'ConversionResult':
        """Create a failed conversion result.
        
        Args:
            error: Primary error message
            **metadata: Additional metadata
            
        Returns:
            ConversionResult with failure status
        """
        return cls(
            status=ConversionStatus.FAILED,
            errors=[error],
            metadata=metadata
        )
    
    def __str__(self) -> str:
        return self.get_summary()


@dataclass
class PluginCapabilities:
    """Describes the capabilities of a plugin.
    
    Used to communicate what a plugin can do and what features
    it supports to the core application and other plugins.
    """
    
    supported_formats: List[FileFormat] = field(default_factory=list)
    provides_ui_extensions: bool = False
    supports_batch_conversion: bool = False
    requires_network_access: bool = False
    
    # Feature flags
    supports_metadata_schema: bool = True
    supports_progress_reporting: bool = False
    supports_cancellation: bool = False
    
    # Performance characteristics
    average_conversion_time: Optional[str] = None  # e.g., "fast", "medium", "slow"
    memory_usage: Optional[str] = None  # e.g., "low", "medium", "high"
    
    def get_extensions(self) -> Set[str]:
        """Get all supported file extensions.
        
        Returns:
            Set of file extensions supported by this plugin
        """
        return {fmt.extension for fmt in self.supported_formats}
    
    def get_mime_types(self) -> Set[str]:
        """Get all supported MIME types.
        
        Returns:
            Set of MIME types supported by this plugin
        """
        return {fmt.mime_type for fmt in self.supported_formats}
    
    def supports_extension(self, extension: str) -> bool:
        """Check if plugin supports a file extension.
        
        Args:
            extension: File extension to check (with or without dot)
            
        Returns:
            True if extension is supported
        """
        if not extension.startswith('.'):
            extension = f'.{extension}'
        return extension.lower() in self.get_extensions()
    
    def get_format_by_extension(self, extension: str) -> Optional[FileFormat]:
        """Get FileFormat for a specific extension.
        
        Args:
            extension: File extension to find
            
        Returns:
            FileFormat if found, None otherwise
        """
        if not extension.startswith('.'):
            extension = f'.{extension}'
        extension = extension.lower()
        
        for fmt in self.supported_formats:
            if fmt.extension == extension:
                return fmt
        return None
    
    def __str__(self) -> str:
        extensions = ', '.join(sorted(self.get_extensions()))
        return f"PluginCapabilities(formats: {extensions})"


@dataclass 
class HandlerSelectionCriteria:
    """Criteria for selecting document handlers.
    
    Used by the service registry to determine which handler
    should be used for a specific file or conversion task.
    """
    
    file_path: Optional[Path] = None
    file_extension: Optional[str] = None
    mime_type: Optional[str] = None
    preferred_plugin: Optional[str] = None  # Plugin ID preference
    
    # Selection preferences
    prefer_fastest: bool = False
    prefer_most_features: bool = False
    exclude_plugins: Set[str] = field(default_factory=set)
    
    def matches_format(self, file_format: FileFormat) -> bool:
        """Check if criteria matches a file format.
        
        Args:
            file_format: FileFormat to check
            
        Returns:
            True if format matches the criteria
        """
        # Check excluded plugins
        if file_format.plugin_id in self.exclude_plugins:
            return False
        
        # Check preferred plugin
        if self.preferred_plugin and file_format.plugin_id != self.preferred_plugin:
            return False
        
        # Check file path extension
        if self.file_path and not file_format.matches_file(self.file_path):
            return False
        
        # Check explicit extension
        if self.file_extension:
            ext = self.file_extension if self.file_extension.startswith('.') else f'.{self.file_extension}'
            if file_format.extension != ext.lower():
                return False
        
        # Check MIME type
        if self.mime_type and file_format.mime_type != self.mime_type:
            return False
        
        return True
    
    @classmethod
    def for_file(cls, file_path: Path, preferred_plugin: Optional[str] = None) -> 'HandlerSelectionCriteria':
        """Create criteria for a specific file.
        
        Args:
            file_path: File to create criteria for
            preferred_plugin: Optional preferred plugin ID
            
        Returns:
            HandlerSelectionCriteria configured for the file
        """
        return cls(
            file_path=file_path,
            file_extension=file_path.suffix.lower(),
            preferred_plugin=preferred_plugin
        )