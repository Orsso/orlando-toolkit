from __future__ import annotations

"""Plugin metadata schema and validation.

Defines the plugin.json schema and provides validation functions to ensure
plugin metadata conforms to requirements. Uses JSON Schema for validation
and provides detailed error reporting for invalid metadata.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from .exceptions import PluginValidationError

logger = logging.getLogger(__name__)

# Plugin metadata JSON Schema
PLUGIN_SCHEMA = {
    "type": "object",
    "required": [
        "name",
        "version", 
        "category",
        "orlando_version",
        "plugin_api_version",
        "entry_point"
    ],
    "properties": {
        "name": {
            "type": "string",
            "pattern": "^[a-z0-9][a-z0-9-]*[a-z0-9]$",
            "minLength": 2,
            "maxLength": 50,
            "description": "Plugin identifier (lowercase, hyphens allowed)"
        },
        "version": {
            "type": "string",
            "pattern": "^\\d+\\.\\d+\\.\\d+(-[a-zA-Z0-9]+)?$",
            "description": "Semantic version (e.g., 1.0.0, 1.0.0-beta)"
        },
        "display_name": {
            "type": "string",
            "maxLength": 100,
            "description": "Human-readable plugin name"
        },
        "description": {
            "type": "string", 
            "maxLength": 500,
            "description": "Plugin description"
        },
        "author": {
            "type": "string",
            "maxLength": 100,
            "description": "Plugin author name"
        },
        "homepage": {
            "type": "string",
            "format": "uri",
            "description": "Plugin homepage URL"
        },
        "category": {
            "type": "string",
            "enum": ["pipeline"],
            "description": "Plugin category (only 'pipeline' supported)"
        },
        "orlando_version": {
            "type": "string",
            "pattern": "^>=\\d+\\.\\d+\\.\\d+$",
            "description": "Minimum Orlando Toolkit version (e.g., '>=2.0.0')"
        },
        "plugin_api_version": {
            "type": "string",
            "pattern": "^\\d+\\.\\d+$",
            "description": "Plugin API version (e.g., '1.0')"
        },
        "entry_point": {
            "type": "string",
            "pattern": "^[a-zA-Z_][a-zA-Z0-9_.]*\\.[a-zA-Z_][a-zA-Z0-9_]*$",
            "description": "Python module path to plugin class (e.g., 'src.plugin.MyPlugin')"
        },
        "supported_formats": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["extension", "description"],
                "properties": {
                    "extension": {
                        "type": "string",
                        "pattern": "^\\.[a-z0-9]+$",
                        "description": "File extension (e.g., '.docx')"
                    },
                    "mime_type": {
                        "type": "string",
                        "description": "MIME type"
                    },
                    "description": {
                        "type": "string",
                        "maxLength": 200,
                        "description": "Format description"
                    }
                }
            },
            "description": "Supported file formats"
        },
        "dependencies": {
            "type": "object",
            "properties": {
                "python": {
                    "type": "string",
                    "pattern": "^>=\\d+\\.\\d+(\\.\\d+)?$",
                    "description": "Minimum Python version"
                },
                "packages": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "description": "Python package requirement (pip format)"
                    },
                    "description": "Required Python packages"
                }
            },
            "description": "Plugin dependencies"
        },
        "provides": {
            "type": "object", 
            "properties": {
                "services": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["DocumentHandler", "HeadingAnalysisService"]
                    },
                    "description": "Services provided by plugin"
                },
                "ui_extensions": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "UI extensions provided by plugin"
                },
                "config_schemas": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "Configuration schemas provided by plugin"
                }
            },
            "description": "Services and extensions provided by plugin"
        },
        "creates_archive": {
            "type": "boolean",
            "description": "Whether plugin creates DITA archive packages"
        },
        "ui": {
            "type": "object",
            "properties": {
                "splash_button": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "maxLength": 50,
                            "description": "Button text"
                        },
                        "icon": {
                            "type": "string",
                            "description": "Icon file name"
                        },
                        "tooltip": {
                            "type": "string",
                            "maxLength": 200,
                            "description": "Button tooltip"
                        }
                    },
                    "description": "Splash screen button configuration"
                }
            },
            "description": "UI configuration"
        },
        "permissions": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "file_system_read",
                    "file_system_write", 
                    "network_access",
                    "system_info"
                ]
            },
            "description": "Permissions requested by plugin"
        }
    },
    "additionalProperties": False
}


@dataclass
class PluginMetadata:
    """Structured representation of plugin metadata.
    
    Provides type-safe access to plugin metadata after validation
    and convenient methods for working with plugin information.
    """
    
    name: str
    version: str
    category: str
    orlando_version: str 
    plugin_api_version: str
    entry_point: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    author: Optional[str] = None
    homepage: Optional[str] = None
    supported_formats: List[Dict[str, str]] = None
    dependencies: Optional[Dict[str, Any]] = None
    provides: Optional[Dict[str, List[str]]] = None
    creates_archive: bool = True
    ui: Optional[Dict[str, Any]] = None
    permissions: List[str] = None
    
    def __post_init__(self) -> None:
        if self.supported_formats is None:
            self.supported_formats = []
        if self.permissions is None:
            self.permissions = []
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PluginMetadata':
        """Create PluginMetadata from validated dictionary."""
        return cls(
            name=data["name"],
            version=data["version"],
            category=data["category"],
            orlando_version=data["orlando_version"],
            plugin_api_version=data["plugin_api_version"],
            entry_point=data["entry_point"],
            display_name=data.get("display_name"),
            description=data.get("description"),
            author=data.get("author"),
            homepage=data.get("homepage"),
            supported_formats=data.get("supported_formats", []),
            dependencies=data.get("dependencies"),
            provides=data.get("provides"),
            creates_archive=data.get("creates_archive", True),
            ui=data.get("ui"),
            permissions=data.get("permissions", [])
        )
    
    def get_supported_extensions(self) -> List[str]:
        """Get list of supported file extensions."""
        return [fmt["extension"] for fmt in self.supported_formats]
    
    def get_provided_services(self) -> List[str]:
        """Get list of services provided by this plugin."""
        if self.provides:
            return self.provides.get("services", [])
        return []
    
    def requires_permission(self, permission: str) -> bool:
        """Check if plugin requires a specific permission."""
        return permission in self.permissions
    
    def is_compatible_with_orlando_version(self, orlando_version: str) -> bool:
        """Check if plugin is compatible with given Orlando version."""
        # Simple version comparison for now (assumes >=X.Y.Z format)
        if self.orlando_version.startswith(">="):
            required_version = self.orlando_version[2:]
            return self._compare_versions(orlando_version, required_version) >= 0
        return False
    
    def _compare_versions(self, version1: str, version2: str) -> int:
        """Compare two semantic versions. Returns -1, 0, or 1."""
        v1_parts = [int(x) for x in version1.split(".")]
        v2_parts = [int(x) for x in version2.split(".")]
        
        # Pad shorter version with zeros
        max_len = max(len(v1_parts), len(v2_parts))
        v1_parts.extend([0] * (max_len - len(v1_parts)))
        v2_parts.extend([0] * (max_len - len(v2_parts)))
        
        for v1, v2 in zip(v1_parts, v2_parts):
            if v1 < v2:
                return -1
            elif v1 > v2:
                return 1
        return 0


def validate_plugin_metadata(metadata_path: Path, plugin_dir: Path) -> PluginMetadata:
    """Validate plugin metadata from plugin.json file.
    
    Args:
        metadata_path: Path to plugin.json file
        plugin_dir: Path to plugin directory
        
    Returns:
        PluginMetadata: Validated metadata object
        
    Raises:
        PluginValidationError: If validation fails
    """
    try:
        # Check if metadata file exists
        if not metadata_path.exists():
            raise PluginValidationError(
                f"Plugin metadata file not found: {metadata_path}"
            )
        
        # Load and parse JSON
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise PluginValidationError(
                f"Invalid JSON in plugin metadata: {e}",
                cause=e
            )
        except Exception as e:
            raise PluginValidationError(
                f"Failed to read plugin metadata: {e}",
                cause=e
            )
        
        # Validate against schema
        validation_errors = _validate_against_schema(data, PLUGIN_SCHEMA)
        if validation_errors:
            raise PluginValidationError(
                "Plugin metadata validation failed",
                validation_errors=validation_errors
            )
        
        # Additional structural validation
        _validate_plugin_structure(data, plugin_dir)
        
        # Create and return metadata object
        metadata = PluginMetadata.from_dict(data)
        logger.debug("Plugin metadata validated successfully: %s v%s", 
                    metadata.name, metadata.version)
        
        return metadata
        
    except PluginValidationError:
        raise
    except Exception as e:
        raise PluginValidationError(
            f"Unexpected error during plugin validation: {e}",
            cause=e
        )


def _validate_against_schema(data: Dict[str, Any], schema: Dict[str, Any]) -> List[str]:
    """Validate data against JSON schema.
    
    This is a simplified validation implementation. In production,
    consider using jsonschema library for full JSON Schema support.
    """
    errors: List[str] = []
    
    # Check required fields
    required_fields = schema.get("required", [])
    for field in required_fields:
        if field not in data:
            errors.append(f"Missing required field: {field}")
    
    # Check field types and constraints
    properties = schema.get("properties", {})
    for field, value in data.items():
        if field in properties:
            field_errors = _validate_field(field, value, properties[field])
            errors.extend(field_errors)
    
    return errors


def _validate_field(field_name: str, value: Any, field_schema: Dict[str, Any]) -> List[str]:
    """Validate individual field against its schema."""
    errors: List[str] = []
    
    # Type checking
    expected_type = field_schema.get("type")
    if expected_type == "string" and not isinstance(value, str):
        errors.append(f"Field '{field_name}' must be a string")
    elif expected_type == "array" and not isinstance(value, list):
        errors.append(f"Field '{field_name}' must be an array")
    elif expected_type == "object" and not isinstance(value, dict):
        errors.append(f"Field '{field_name}' must be an object")
    elif expected_type == "boolean" and not isinstance(value, bool):
        errors.append(f"Field '{field_name}' must be a boolean")
    
    # String constraints
    if isinstance(value, str):
        if "minLength" in field_schema and len(value) < field_schema["minLength"]:
            errors.append(f"Field '{field_name}' is too short (minimum {field_schema['minLength']} characters)")
        if "maxLength" in field_schema and len(value) > field_schema["maxLength"]:
            errors.append(f"Field '{field_name}' is too long (maximum {field_schema['maxLength']} characters)")
        
        # Enum validation
        if "enum" in field_schema and value not in field_schema["enum"]:
            valid_values = ", ".join(field_schema["enum"])
            errors.append(f"Field '{field_name}' must be one of: {valid_values}")
    
    return errors


def _validate_plugin_structure(metadata: Dict[str, Any], plugin_dir: Path) -> None:
    """Validate plugin directory structure and files."""
    
    # Check if entry point module exists
    entry_point = metadata.get("entry_point", "")
    if entry_point:
        # Convert module path to file path (e.g., "src.plugin.MyPlugin" -> "src/plugin.py")
        module_parts = entry_point.split(".")
        if len(module_parts) >= 2:
            # Remove class name, keep module path
            module_path_parts = module_parts[:-1]
            
            # Build module file path (e.g., "src.plugin" -> "src/plugin.py")
            module_file = plugin_dir / ("/".join(module_path_parts) + ".py")
            
            if not module_file.exists():
                # Also check __init__.py in module directory
                module_dir = plugin_dir / "/".join(module_path_parts)
                init_file = module_dir / "__init__.py"
                if not init_file.exists():
                    raise PluginValidationError(
                        f"Entry point module not found: {entry_point} "
                        f"(looked for {module_file} or {init_file})"
                    )
    
    # Check for requirements.txt if dependencies are specified
    dependencies = metadata.get("dependencies", {})
    if dependencies.get("packages"):
        requirements_file = plugin_dir / "requirements.txt"
        if not requirements_file.exists():
            raise PluginValidationError(
                "Plugin specifies package dependencies but no requirements.txt found"
            )