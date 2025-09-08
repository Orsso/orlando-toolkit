from __future__ import annotations

"""DITA package importer for zipped DITA archives.

Handles importing zipped DITA packages (.zip files) and converting them
into DitaContext objects that can be edited and manipulated by the
Orlando Toolkit core functionality.
"""

import logging
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from lxml import etree as ET

from orlando_toolkit.core.models import DitaContext
from orlando_toolkit.core.utils import slugify

logger = logging.getLogger(__name__)

__all__ = ["DitaPackageImporter"]


class DitaImportError(Exception):
    """Exception raised when DITA package import fails."""
    
    def __init__(self, message: str, file_path: Optional[Path] = None, cause: Optional[Exception] = None):
        self.file_path = file_path
        self.cause = cause
        super().__init__(message)


class DitaPackageImporter:
    """Importer for zipped DITA archive packages.
    
    This class handles the extraction and parsing of zipped DITA archives,
    converting them into DitaContext objects that can be processed by
    Orlando Toolkit's editing and export functionality.
    
    The importer supports various DITA package structures:
    - Standard DITA packages with DATA/ folder structure
    - Flat DITA packages with ditamap and topics in root
    - DITA packages with custom folder hierarchies
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.DitaPackageImporter")
    
    def can_import(self, file_path: Path) -> bool:
        """Check if this importer can handle the given file.
        
        Args:
            file_path: Path to the file to check
            
        Returns:
            True if file appears to be a DITA package, False otherwise
        """
        if not file_path.exists() or not file_path.is_file():
            return False
        
        # Check file extension
        if file_path.suffix.lower() != '.zip':
            return False
        
        try:
            # Quick validation: check if ZIP contains DITA files
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                file_list = zip_ref.namelist()
                
                # Look for .ditamap files
                has_ditamap = any(f.endswith('.ditamap') for f in file_list)
                
                # Look for .dita files
                has_dita_topics = any(f.endswith('.dita') for f in file_list)
                
                return has_ditamap or has_dita_topics
                
        except (zipfile.BadZipFile, OSError):
            return False
    
    def import_package(self, file_path: Path, metadata: Optional[Dict[str, Any]] = None,
                       progress_callback: Optional[Callable[[str], None]] = None) -> DitaContext:
        """Import a zipped DITA package into a DitaContext.
        
        Args:
            file_path: Path to the ZIP file containing the DITA package
            metadata: Optional metadata to merge with imported data
            progress_callback: Optional callback for progress updates
            
        Returns:
            DitaContext containing the imported DITA archive
            
        Raises:
            DitaImportError: If import fails for any reason
        """
        if not self.can_import(file_path):
            raise DitaImportError(f"File is not a valid DITA package: {file_path}", file_path)
        
        if progress_callback:
            progress_callback(f"Importing DITA package: {file_path.name}")
        self.logger.debug("Importing DITA package: %s", file_path)
        
        try:
            with tempfile.TemporaryDirectory(prefix="otk_dita_import_") as temp_dir:
                # Extract ZIP archive
                self._extract_zip(file_path, temp_dir)
                
                # Find and parse the DITA structure
                context = self._parse_dita_structure(Path(temp_dir), metadata or {})
                
                # Set source information in metadata
                context.metadata["source_file"] = str(file_path)
                context.metadata["source_type"] = "dita_package"
                context.metadata["import_timestamp"] = self._get_current_timestamp()
                
                if progress_callback:
                    progress_callback(f"Successfully imported DITA package with {len(context.topics)} topics and {len(context.images)} images")
                self.logger.debug("Successfully imported DITA package with %d topics and %d images",
                               len(context.topics), len(context.images))
                
                return context
                
        except Exception as e:
            if isinstance(e, DitaImportError):
                raise
            raise DitaImportError(f"Failed to import DITA package: {e}", file_path, e)
    
    def _extract_zip(self, zip_path: Path, extract_dir: str) -> None:
        """Extract ZIP archive to temporary directory.
        
        Args:
            zip_path: Path to ZIP file
            extract_dir: Directory to extract to
            
        Raises:
            DitaImportError: If extraction fails
        """
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Security check: validate paths before extraction
                for member in zip_ref.namelist():
                    if os.path.isabs(member) or ".." in member:
                        raise DitaImportError(f"Unsafe path in ZIP: {member}", zip_path)
                
                zip_ref.extractall(extract_dir)
                self.logger.debug("Extracted ZIP to: %s", extract_dir)
                
        except zipfile.BadZipFile as e:
            raise DitaImportError(f"Invalid ZIP file: {e}", zip_path, e)
        except OSError as e:
            raise DitaImportError(f"Failed to extract ZIP: {e}", zip_path, e)
    
    def _parse_dita_structure(self, root_dir: Path, base_metadata: Dict[str, Any]) -> DitaContext:
        """Parse extracted DITA structure and build DitaContext.
        
        Args:
            root_dir: Root directory of extracted DITA package
            base_metadata: Base metadata to include in context
            
        Returns:
            DitaContext with parsed structure
            
        Raises:
            DitaImportError: If parsing fails
        """
        # Find ditamap file
        ditamap_path = self._find_ditamap(root_dir)
        if not ditamap_path:
            raise DitaImportError("No .ditamap file found in package", root_dir)
        
        self.logger.debug("Found ditamap: %s", ditamap_path)
        
        # Parse ditamap
        try:
            ditamap_root = self._parse_xml_file(ditamap_path)
        except Exception as e:
            raise DitaImportError(f"Failed to parse ditamap: {e}", ditamap_path, e)
        
        # Extract metadata from ditamap
        extracted_metadata = self._extract_metadata_from_ditamap(ditamap_root)
        
        # Merge metadata (base takes precedence)
        merged_metadata = {**extracted_metadata, **base_metadata}
        
        # Find topics directory
        topics_dir = self._find_topics_directory(root_dir, ditamap_path)
        
        # Load all referenced topics
        topics = self._load_topics(ditamap_root, topics_dir)
        
        # Find media directory and load images/videos
        media_dir = self._find_media_directory(root_dir, ditamap_path)
        images = self._load_images(media_dir)
        videos = self._load_videos(media_dir)
        
        # Build and return DitaContext
        context = DitaContext(
            ditamap_root=ditamap_root,
            topics=topics,
            images=images,
            videos=videos,
            metadata=merged_metadata
        )
        
        return context
    
    def _find_ditamap(self, root_dir: Path) -> Optional[Path]:
        """Find the primary .ditamap file in the package.
        
        Args:
            root_dir: Root directory to search
            
        Returns:
            Path to ditamap file or None if not found
        """
        # Search patterns in order of preference:
        # 1. Look in DATA subdirectory first (Orlando standard)
        # 2. Look in root directory
        # 3. Look recursively (up to 3 levels deep)
        
        search_paths = [
            root_dir / "DATA",
            root_dir,
        ]
        
        # Add subdirectories up to 2 levels deep
        for path in list(root_dir.rglob("*/")):
            relative_depth = len(path.relative_to(root_dir).parts)
            if relative_depth <= 2:
                search_paths.append(path)
        
        for search_dir in search_paths:
            if not search_dir.exists():
                continue
            
            ditamap_files = list(search_dir.glob("*.ditamap"))
            if ditamap_files:
                # Return the first ditamap found
                # Could be enhanced to choose based on naming patterns
                return ditamap_files[0]
        
        return None
    
    def _find_topics_directory(self, root_dir: Path, ditamap_path: Path) -> Path:
        """Find the topics directory relative to the ditamap.
        
        Args:
            root_dir: Root directory of package
            ditamap_path: Path to the ditamap file
            
        Returns:
            Path to topics directory
        """
        ditamap_dir = ditamap_path.parent
        
        # Common topic directory patterns
        candidates = [
            ditamap_dir / "topics",
            ditamap_dir,  # Topics in same directory as ditamap
            root_dir / "DATA" / "topics",
            root_dir / "topics",
        ]
        
        for candidate in candidates:
            if candidate.exists() and any(candidate.glob("*.dita")):
                self.logger.debug("Found topics directory: %s", candidate)
                return candidate
        
        # Default to ditamap directory
        self.logger.warning("No dedicated topics directory found, using ditamap directory: %s", 
                           ditamap_dir)
        return ditamap_dir
    
    def _find_media_directory(self, root_dir: Path, ditamap_path: Path) -> Optional[Path]:
        """Find the media/images directory.
        
        Args:
            root_dir: Root directory of package
            ditamap_path: Path to the ditamap file
            
        Returns:
            Path to media directory or None if not found
        """
        ditamap_dir = ditamap_path.parent
        
        candidates = [
            ditamap_dir / "media",
            ditamap_dir / "images",
            root_dir / "DATA" / "media",
            root_dir / "DATA" / "images",
            root_dir / "media",
            root_dir / "images",
        ]
        
        for candidate in candidates:
            if candidate.exists() and candidate.is_dir():
                # Check if it contains image or video files
                image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.tiff', '.webp'}
                video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v', '.wmv'}
                has_media = any(
                    f.is_file() and (f.suffix.lower() in image_extensions or f.suffix.lower() in video_extensions)
                    for f in candidate.iterdir()
                )
                if has_media:
                    self.logger.debug("Found media directory: %s", candidate)
                    return candidate
        
        return None
    
    def _parse_xml_file(self, xml_path: Path) -> ET.Element:
        """Parse an XML file and return the root element.
        
        Args:
            xml_path: Path to XML file
            
        Returns:
            Root element of parsed XML
            
        Raises:
            Exception: If parsing fails
        """
        try:
            parser = ET.XMLParser(resolve_entities=False)  # Security: disable entity resolution
            tree = ET.parse(str(xml_path), parser)
            return tree.getroot()
        except ET.XMLSyntaxError as e:
            raise Exception(f"XML syntax error in {xml_path}: {e}")
        except OSError as e:
            raise Exception(f"Failed to read {xml_path}: {e}")
    
    def _extract_metadata_from_ditamap(self, ditamap_root: ET.Element) -> Dict[str, Any]:
        """Extract metadata from ditamap element.
        
        Args:
            ditamap_root: Root element of ditamap
            
        Returns:
            Dictionary of extracted metadata
        """
        metadata = {}
        
        # Extract title from topicmeta/navtitle or title attribute
        title_element = ditamap_root.find(".//topicmeta/navtitle")
        if title_element is not None and title_element.text:
            metadata["manual_title"] = title_element.text.strip()
        elif ditamap_root.get("title"):
            metadata["manual_title"] = ditamap_root.get("title").strip()
        
        # Extract other metadata from topicmeta
        topicmeta = ditamap_root.find("topicmeta")
        if topicmeta is not None:
            # Look for author information
            author_elem = topicmeta.find("author")
            if author_elem is not None and author_elem.text:
                metadata["author"] = author_elem.text.strip()
            
            # Look for keywords/metadata elements
            keywords_elem = topicmeta.find("keywords")
            if keywords_elem is not None:
                keyword_list = [kw.text.strip() for kw in keywords_elem.findall("keyword") 
                               if kw.text and kw.text.strip()]
                if keyword_list:
                    metadata["keywords"] = keyword_list
        
        # Generate manual_code from title if not present
        if "manual_title" in metadata and "manual_code" not in metadata:
            metadata["manual_code"] = slugify(metadata["manual_title"])
        
        return metadata
    
    def _load_topics(self, ditamap_root: ET.Element, topics_dir: Path) -> Dict[str, ET.Element]:
        """Load all topics referenced in the ditamap.
        
        Args:
            ditamap_root: Root element of ditamap
            topics_dir: Directory containing topic files
            
        Returns:
            Dictionary mapping topic filenames to their root elements
        """
        topics = {}
        
        # Find all topicref elements with href attributes
        for topicref in ditamap_root.xpath(".//topicref[@href]"):
            href = topicref.get("href")
            if not href or not href.endswith(".dita"):
                continue
            
            # Extract filename from href (remove path components)
            topic_filename = href.split("/")[-1]
            
            # Try to find the topic file
            topic_path = topics_dir / topic_filename
            if not topic_path.exists():
                # Try alternative locations
                alt_paths = [
                    topics_dir.parent / topic_filename,
                    topics_dir.parent / "topics" / topic_filename,
                ]
                
                for alt_path in alt_paths:
                    if alt_path.exists():
                        topic_path = alt_path
                        break
                else:
                    self.logger.warning("Topic file not found: %s (referenced from %s)", 
                                      topic_filename, href)
                    continue
            
            try:
                topic_element = self._parse_xml_file(topic_path)
                topics[topic_filename] = topic_element
                self.logger.debug("Loaded topic: %s", topic_filename)
                
            except Exception as e:
                self.logger.error("Failed to parse topic %s: %s", topic_filename, e)
                continue
        
        return topics
    
    def _load_images(self, media_dir: Optional[Path]) -> Dict[str, bytes]:
        """Load all images from the media directory.
        
        Args:
            media_dir: Directory containing media files, or None
            
        Returns:
            Dictionary mapping image filenames to their binary content
        """
        images = {}
        
        if not media_dir or not media_dir.exists():
            return images
        
        # Supported image extensions
        image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.tiff', '.webp'}
        
        for image_path in media_dir.iterdir():
            if not image_path.is_file():
                continue
            
            if image_path.suffix.lower() not in image_extensions:
                continue
            
            try:
                with open(image_path, 'rb') as f:
                    images[image_path.name] = f.read()
                self.logger.debug("Loaded image: %s (%d bytes)", 
                                image_path.name, len(images[image_path.name]))
                
            except OSError as e:
                self.logger.error("Failed to read image %s: %s", image_path.name, e)
                continue
        
        return images

    def _load_videos(self, media_dir: Optional[Path]) -> Dict[str, bytes]:
        """Load all videos from the media directory.
        
        Args:
            media_dir: Directory containing media files, or None
            
        Returns:
            Dictionary mapping video filenames to their binary content
        """
        videos: Dict[str, bytes] = {}
        
        if not media_dir or not media_dir.exists():
            return videos
        
        # Supported video extensions (common set)
        video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v', '.wmv'}
        
        for video_path in media_dir.iterdir():
            if not video_path.is_file():
                continue
            
            if video_path.suffix.lower() not in video_extensions:
                continue
            
            try:
                with open(video_path, 'rb') as f:
                    videos[video_path.name] = f.read()
                self.logger.debug("Loaded video: %s (%d bytes)", 
                                video_path.name, len(videos[video_path.name]))
                
            except OSError as e:
                self.logger.error("Failed to read video %s: %s", video_path.name, e)
                continue
        
        return videos
    
    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format.
        
        Returns:
            ISO formatted timestamp string
        """
        from datetime import datetime
        return datetime.now().isoformat()
    
    def get_supported_extensions(self) -> List[str]:
        """Get list of supported file extensions.
        
        Returns:
            List of supported extensions
        """
        return ['.zip']
    
    def get_format_description(self) -> str:
        """Get human-readable description of supported format.
        
        Returns:
            Format description string
        """
        return "Zipped DITA Package Archives"