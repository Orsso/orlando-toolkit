from __future__ import annotations

"""Plugin interface definitions.

Defines abstract interfaces that plugins must implement to provide
functionality to the Orlando Toolkit. These interfaces form the contract
between plugins and the core application.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Any, Protocol, runtime_checkable, Callable, Optional

from orlando_toolkit.core.models import DitaContext


# Type alias for progress callback function
ProgressCallback = Callable[[str], None]


@runtime_checkable
class DocumentHandler(Protocol):
    """Protocol for document conversion handlers.
    
    Plugins implement this protocol to provide document conversion
    functionality from external formats to DITA archives.
    
    The DocumentHandler protocol defines the interface that plugins must
    implement to convert various document formats (DOCX, PDF, Markdown, etc.)
    into DITA archives that can be processed by Orlando Toolkit.
    """
    
    def can_handle(self, file_path: Path) -> bool:
        """Return True if this handler can process the file.
        
        This method should examine the file (typically by extension,
        but potentially by content inspection) and determine if this
        handler is capable of converting it to DITA format.
        
        Args:
            file_path: Path to the file to be checked
            
        Returns:
            True if this handler can convert the file, False otherwise
            
        Note:
            This method should be fast and should not perform the actual
            conversion. It's used for handler selection and format detection.
        """
        ...
    
    def convert_to_dita(self, file_path: Path, metadata: Dict[str, Any], 
                       progress_callback: Optional[ProgressCallback] = None) -> DitaContext:
        """Convert file to DitaContext and return complete DITA archive data.
        
        This is the main conversion method that transforms the source document
        into a complete DITA archive representation. The returned DitaContext
        should contain all topics, images, and metadata needed for the DITA package.
        
        Args:
            file_path: Path to the source document
            metadata: Conversion metadata and configuration options
            progress_callback: Optional callback function for progress updates.
                             Call with string messages to update UI status during conversion.
            
        Returns:
            DitaContext containing the complete DITA archive data
            
        Raises:
            Exception: If conversion fails, handler should raise an appropriate
                      exception with descriptive error message
                      
        Note:
            If progress_callback is provided, plugins should call it with descriptive
            status messages during conversion (e.g., "Loading DOCX file...", 
            "Extracting images...", "Analyzing document structure...").
        """
        ...
    
    def get_supported_extensions(self) -> List[str]:
        """Return list of supported file extensions.
        
        Returns file extensions (including the dot) that this handler
        can process. Used for file dialog filters and format detection.
        
        Returns:
            List of file extensions, e.g., ['.docx', '.doc']
            
        Note:
            Extensions should include the leading dot and be lowercase.
        """
        ...
    
    def get_conversion_metadata_schema(self) -> Dict[str, Any]:
        """Return JSON schema for conversion-specific metadata fields.
        
        Defines the schema for metadata fields that this handler expects
        or supports during conversion. This can be used by the UI to
        provide appropriate configuration options.
        
        Returns:
            JSON schema dictionary describing supported metadata fields
            
        Note:
            Should follow JSON Schema specification for validation and
            UI generation purposes.
        """
        ...


class DocumentHandlerBase(ABC):
    """Abstract base class for DocumentHandler implementations.
    
    Provides a concrete base class that plugins can inherit from instead
    of implementing the Protocol directly. This base class provides common
    functionality and ensures proper interface implementation.
    
    Plugin developers should inherit from this class and implement the
    abstract methods to create DocumentHandler implementations.
    """
    
    @abstractmethod
    def can_handle(self, file_path: Path) -> bool:
        """Return True if this handler can process the file."""
        pass
    
    @abstractmethod
    def convert_to_dita(self, file_path: Path, metadata: Dict[str, Any], 
                       progress_callback: Optional[ProgressCallback] = None) -> DitaContext:
        """Convert file to DitaContext and return complete DITA archive data."""
        pass
    
    @abstractmethod
    def get_supported_extensions(self) -> List[str]:
        """Return list of supported file extensions."""
        pass
    
    @abstractmethod
    def get_conversion_metadata_schema(self) -> Dict[str, Any]:
        """Return JSON schema for conversion-specific metadata fields."""
        pass
    
    # Common utility methods can be added here in future versions
    
    def validate_file_exists(self, file_path: Path) -> None:
        """Validate that the input file exists and is readable.
        
        Args:
            file_path: Path to validate
            
        Raises:
            FileNotFoundError: If file doesn't exist
            PermissionError: If file isn't readable
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Input file not found: {file_path}")
        
        if not file_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")
        
        # Test readability
        try:
            file_path.open('rb').close()
        except PermissionError as e:
            raise PermissionError(f"Cannot read input file: {file_path}") from e
    
    def get_handler_info(self) -> Dict[str, Any]:
        """Get information about this handler.
        
        Returns:
            Dictionary with handler information including supported formats
        """
        return {
            'class': self.__class__.__name__,
            'supported_extensions': self.get_supported_extensions(),
            'schema': self.get_conversion_metadata_schema()
        }


@runtime_checkable
class UIExtension(Protocol):
    """Protocol for UI extension components.
    
    Plugins can implement this protocol to provide UI extensions
    such as right panel components, custom dialogs, or toolbar items.
    
    Note: This interface is defined for future use and is not yet
    implemented in the core application.
    """
    
    def get_extension_info(self) -> Dict[str, Any]:
        """Get information about this UI extension.
        
        Returns:
            Dictionary describing the extension capabilities including:
            - supported_components: List of component types this extension provides
            - display_name: Human-readable name for the extension
            - description: Description of extension functionality
        """
        ...
    
    def register_ui_components(self, ui_registry: Any) -> None:
        """Register UI components with the UI registry.
        
        Args:
            ui_registry: UIRegistry instance for component registration
            
        Note:
            This method should register panel factories, marker providers,
            and other UI components that the plugin provides.
        """
        ...
    
    def unregister_ui_components(self, ui_registry: Any) -> None:
        """Unregister UI components from the UI registry.
        
        Args:
            ui_registry: UIRegistry instance for component cleanup
            
        Note:
            This method should clean up all UI components registered
            by this extension. It's called when the plugin is deactivated.
        """
        ...
    
    def get_panel_factories(self) -> Dict[str, Any]:
        """Get panel factories provided by this extension.
        
        Returns:
            Dictionary mapping panel type names to PanelFactory instances
        """
        ...
    
    def get_marker_providers(self) -> Dict[str, Any]:
        """Get marker providers provided by this extension.
        
        Returns:
            Dictionary mapping marker type names to MarkerProvider instances
        """
        ...


# Type aliases for better code readability
AnyDocumentHandler = DocumentHandler  # For type hints that accept any DocumentHandler


@runtime_checkable
class FilterProvider(Protocol):
    """Protocol for plugin-provided structure filtering services.

    A FilterProvider supplies counts, occurrences, grouping, and exclusion mapping
    for a document source, and assists estimation prior to applying filters.
    The core UI delegates to this provider instead of embedding source-specific logic.
    """

    def get_counts(self, context: DitaContext) -> Dict[str, int]:
        """Return mapping group_key -> count for the source (plugin-defined keys)."""
        ...

    def get_occurrences(self, context: DitaContext) -> Dict[str, List[Dict[str, str]]]:
        """Return mapping group_key -> list of occurrence dicts for full/original structure."""
        ...

    def get_occurrences_current(self, context: DitaContext) -> Dict[str, List[Dict[str, str]]]:
        """Return mapping group_key -> occurrences for the current (filtered) structure."""
        ...

    def get_levels(self, context: DitaContext) -> Dict[str, Optional[int]]:
        """Return mapping group_key -> Optional[level] to support grouping in UI."""
        ...

    def build_exclusion_map(self, exclusions: Dict[str, bool]) -> Dict[int, set[str]]:
        """Convert group_key->excluded flags to per-level exclusion map used by the core."""
        ...

    def estimate_unmergable(self, context: DitaContext, style_excl_map: Dict[int, set[str]]) -> int:
        """Estimate number of items that cannot be merged for a given exclusion map."""
        ...
