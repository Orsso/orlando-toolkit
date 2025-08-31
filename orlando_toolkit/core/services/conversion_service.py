from __future__ import annotations

"""High-level conversion service for document to DITA transformation.

Entry-point for any front-end (GUI, CLI, API) that needs to transform
supported documents into a DITA package. Provides a clean, stable API for
document conversion operations through plugin architecture.
"""

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List

from orlando_toolkit.core.models import DitaContext
from orlando_toolkit.core.utils import slugify
from orlando_toolkit.core.plugins.registry import ServiceRegistry
from orlando_toolkit.core.plugins.interfaces import DocumentHandler
from orlando_toolkit.core.plugins.models import FileFormat
from orlando_toolkit.core.plugins.exceptions import UnsupportedFormatError

# Core package utilities
from orlando_toolkit.core.package_utils import (
    save_dita_package,
    update_image_references_and_names,
    update_topic_references_and_names,
    prune_empty_topics,
)

# DITA import functionality  
from orlando_toolkit.core.importers import DitaPackageImporter

logger = logging.getLogger(__name__)

__all__ = ["ConversionService"]


class ConversionService:
    """Business-logic façade with zero GUI / Tkinter dependencies."""

    def __init__(self, service_registry: Optional[ServiceRegistry] = None) -> None:
        # Service registry for plugin-provided handlers
        self.service_registry = service_registry
        self.logger = logger
        
        # DITA package importer for core DITA-only functionality
        self.dita_importer = DitaPackageImporter()
        
        # Track whether we're in DITA-only mode (no plugins)
        self._dita_only_mode = service_registry is None

    # ---------------------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------------------
    def convert(self, file_path: str | Path, metadata: Dict[str, Any]) -> DitaContext:
        """Convert any supported document to an in-memory DitaContext.
        
        This method finds a compatible DocumentHandler plugin for the file format
        and delegates conversion to that handler. Only DITA package import is
        available in DITA-only mode (no plugins).
        
        Args:
            file_path: Path to the document to convert
            metadata: Conversion metadata and configuration
            
        Returns:
            DitaContext containing the converted DITA archive
            
        Raises:
            UnsupportedFormatError: If no plugin can handle the file format
            Exception: If conversion fails for other reasons
        """
        file_path = Path(file_path)
        self.logger.info("Convert: parsing document")
        self.logger.debug("Converting document -> DITA: %s", file_path)
        
        # Validate file exists
        if not file_path.exists():
            raise FileNotFoundError(f"Input file not found: {file_path}")
        
        if not file_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")
        
        # Check for DITA package import (core functionality, available without plugins)
        if self.dita_importer.can_import(file_path):
            try:
                self.logger.debug("Using DITA package importer for file: %s", file_path)
                context = self.dita_importer.import_package(file_path, metadata)
                self.logger.info("DITA package import successful")
                return context
            except Exception as e:
                self.logger.error("DITA package import failed: %s", e)
                raise RuntimeError(f"DITA package import failed: {e}") from e
        
        # Plugin-aware conversion
        if self.service_registry is not None:
            # Try to find a compatible handler from plugins
            handler = self.service_registry.find_handler_for_file(file_path)
            if handler:
                try:
                    plugin_id = self._get_plugin_id_for_handler(handler)
                    self.logger.debug("Using plugin handler from %s for conversion: %s", 
                                    plugin_id, handler.__class__.__name__)
                    
                    # Call plugin handler with error boundary
                    context = handler.convert_to_dita(file_path, metadata)
                    
                    if not isinstance(context, DitaContext):
                        raise ValueError(f"Plugin handler returned invalid type: {type(context)}")
                    
                    # Add plugin attribution to context for UI capability checks
                    if not hasattr(context, 'plugin_data') or context.plugin_data is None:
                        context.plugin_data = {}
                    context.plugin_data['_source_plugin'] = plugin_id
                    
                    self.logger.info("Conversion successful using plugin: %s", plugin_id)
                    return context
                    
                except Exception as e:
                    plugin_id = self._get_plugin_id_for_handler(handler)
                    self.logger.error("Plugin handler from %s failed: %s", plugin_id, e)
                    # Re-raise with plugin context preserved
                    raise RuntimeError(f"Conversion failed in plugin {plugin_id}: {e}") from e
            
            # No handler found - collect available formats for error
            supported_formats = self.get_supported_formats()
            extensions = [fmt.extension for fmt in supported_formats]
            raise UnsupportedFormatError(str(file_path), extensions)
        
        # No plugin registry configured - only DITA import is supported
        else:
            self.logger.debug("Running in DITA-only mode (no plugin registry)")
            # No plugins available, only DITA import is supported
            supported_formats = [fmt.extension for fmt in self.get_supported_formats()]
            raise UnsupportedFormatError(str(file_path), supported_formats)

    def get_supported_formats(self) -> List[FileFormat]:
        """Get all supported file formats from loaded plugins.
        
        Returns:
            List of FileFormat objects describing supported formats
        """
        formats = []
        
        # Always include DITA packages (core functionality)
        dita_extensions = self.dita_importer.get_supported_extensions()
        for ext in dita_extensions:
            formats.append(FileFormat.from_extension(
                ext, 'built-in', 'Zipped DITA Package Archive'
            ))
        
        if self.service_registry is not None:
            # Get formats from service registry which aggregates from all handlers
            format_dicts = self.service_registry.get_supported_formats()
            
            # Convert dict format to FileFormat objects
            for fmt_dict in format_dicts:
                try:
                    file_format = FileFormat.from_extension(
                        extension=fmt_dict['extension'],
                        plugin_id=fmt_dict['plugin_id'],
                        description=fmt_dict.get('description', f"Handled by {fmt_dict['plugin_id']}")
                    )
                    formats.append(file_format)
                except Exception as e:
                    self.logger.warning("Failed to create FileFormat from registry data %s: %s",
                                      fmt_dict, e)
                    continue
        else:
            # No plugins available - only DITA import is supported
            pass
        
        return formats

    def get_supported_extensions(self) -> List[str]:
        """Get list of supported file extensions.
        
        Returns:
            List of file extensions (with dots) that can be converted
        """
        formats = self.get_supported_formats()
        return [fmt.extension for fmt in formats]

    def can_handle_file(self, file_path: str | Path) -> bool:
        """Check if the service can handle a specific file.
        
        Args:
            file_path: Path to the file to check
            
        Returns:
            True if file can be converted, False otherwise
        """
        file_path = Path(file_path)
        
        # Always check DITA package support first (core functionality)
        if self.dita_importer.can_import(file_path):
            return True
        
        if self.service_registry is not None:
            # Check if any plugin handler can handle this file
            handler = self.service_registry.find_handler_for_file(file_path)
            return handler is not None
        else:
            # No plugins available - only DITA import is supported
            return False

    def _get_plugin_id_for_handler(self, handler: DocumentHandler) -> str:
        """Get plugin ID for a handler instance."""
        if self.service_registry is not None:
            # Try to get plugin ID from service registry internal method
            return getattr(self.service_registry, '_get_plugin_for_handler', lambda x: 'unknown')(handler)
        return 'built-in'

    def prepare_package(self, context: DitaContext) -> DitaContext:
        """Apply final renaming of topics and images inside *context*."""
        self.logger.info("Export: preparing content for packaging")
        # Determine effective depth from metadata, keeping previously applied merge depth if larger
        # so we do not inadvertently reduce the structure compared to the UI state.
        # Determine base depth: prefer metadata; else compute from style analysis
        try:
            if context.metadata.get("topic_depth") is not None:
                md_depth = int(context.metadata.get("topic_depth"))
            else:
                from orlando_toolkit.core.services.heading_analysis_service import compute_max_depth
                md_depth = int(compute_max_depth(context))
        except Exception:
            md_depth = 1
        try:
            merged_depth = int(context.metadata.get("merged_depth")) if context.metadata.get("merged_depth") is not None else None
        except Exception:
            merged_depth = None
        depth_limit = md_depth if merged_depth is None else int(merged_depth)

        # ----------------------------------------------------------------
        # 1) Apply unified merge (depth + style exclusions) in single pass
        # ----------------------------------------------------------------

        # Build style exclusion map from all metadata sources
        style_excl_map: dict[int, set[str]] = {}
        
        # Fine-grain style exclusions per level (primary source)
        for key, val in context.metadata.get("exclude_style_map", {}).items():
            try:
                lvl = int(key)
                style_excl_map.setdefault(lvl, set()).update(val)
            except ValueError:
                continue

        # Heading level exclusions (convert to style map)
        excl_lvls = set(context.metadata.get("exclude_styles", []))
        for lvl in excl_lvls:
            # Default style name for level-based exclusions
            style_excl_map.setdefault(int(lvl), set()).add(f"Heading {lvl}")

        # Apply unified merge if needed
        if (context.metadata.get("merged_depth") != depth_limit or
            style_excl_map and not context.metadata.get("merged_exclude_styles")):
            from orlando_toolkit.core.services.structure_editing_service import StructureEditingService
            _ses = StructureEditingService()
            _res = _ses.apply_depth_limit(context, depth_limit, style_excl_map or None)
            if not _res.success:
                # Log warning but continue with current context instead of returning different type
                self.logger.warning("Failed to apply depth limit: %s", _res.message)
                # Continue with current context - packaging will still succeed

        # Handle legacy title-based exclusions separately (if still needed)
        exclude_titles = set(context.metadata.get("exclude_headings", []))
        if exclude_titles and not context.metadata.get("merged_exclude"):
            from orlando_toolkit.core.merge import merge_topics_by_titles
            merge_topics_by_titles(context, exclude_titles)

        # ---------------------------------------------------------------
        # 2) Prune now-empty topicrefs below depth_limit (structure only)
        # ---------------------------------------------------------------
        if context.ditamap_root is not None:
            from lxml import etree as _ET

            def _prune(node: _ET.Element, level: int = 1):
                for tref in list(node.findall("topicref")):
                    if level > depth_limit:
                        node.remove(tref)
                    else:
                        _prune(tref, level + 1)

            _prune(context.ditamap_root)

            # Remove unreferenced topics (already handled in merge, but safe)
            hrefs = {
                tref.get("href").split("/")[-1]
                for tref in context.ditamap_root.xpath(".//topicref[@href]")
            }
            context.topics = {fn: el for fn, el in context.topics.items() if fn in hrefs}

        # 3) Convert empty topics into structural headings
        context = prune_empty_topics(context)

        # 4) Rename items
        context = update_topic_references_and_names(context)
        context = update_image_references_and_names(context)

        # 5) Strip helper attributes (e.g., data-level) that are not valid DITA
        if context.ditamap_root is not None:
            for el in context.ditamap_root.xpath('.//*[@data-level or @data-style or @data-origin]'):
                el.attrib.pop('data-level', None)
                el.attrib.pop('data-style', None)
                el.attrib.pop('data-origin', None)
        return context

    def write_package(self, context: DitaContext, output_zip: str | Path, *,
                      debug_copy_dir: Optional[str | Path] = None) -> None:
        """Write *context* to *output_zip* (a ``.zip`` path).

        If *debug_copy_dir* is provided, the un-zipped folder is also copied
        there for inspection.
        """
        output_zip = Path(output_zip)
        self.logger.info("Export: writing ZIP package")
        self.logger.debug("Destination: %s", output_zip)

        with tempfile.TemporaryDirectory(prefix="otk_") as tmp_dir:
            save_dita_package(context, tmp_dir)
            if debug_copy_dir:
                debug_dest = Path(debug_copy_dir)
                if debug_dest.exists():
                    shutil.rmtree(debug_dest)
                shutil.copytree(tmp_dir, debug_dest)
                self.logger.info("Debug copy written to %s", debug_dest)
            shutil.make_archive(output_zip.with_suffix(""), "zip", tmp_dir)
            self.logger.info("Export OK: zip_written size_bytes=%s", str(output_zip.stat().st_size) if output_zip.exists() else "unknown")

    # Convenience one-shot -------------------------------------------------
    def convert_and_package(
        self,
        input_path: str | Path,
        metadata: Dict[str, Any],
        output_zip: str | Path,
        *,
        debug_copy_dir: Optional[str | Path] = None,
    ) -> Path:
        """Full pipeline: convert document and immediately write a ZIP archive."""
        context = self.convert(input_path, metadata)
        context = self.prepare_package(context)
        self.write_package(context, output_zip, debug_copy_dir=debug_copy_dir)
        return Path(output_zip)
