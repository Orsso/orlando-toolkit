"""UI configuration models for button and layout management.

Data structures for managing UI configurations including splash screen
button configurations, plugin UI integration, and layout specifications.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Callable
from pathlib import Path


@dataclass
class ButtonConfig:
    """Configuration for a squared button in the splash screen."""
    
    text: str
    icon: Optional[str] = None
    tooltip: Optional[str] = None
    command: Optional[Callable] = None
    plugin_id: Optional[str] = None
    enabled: bool = True
    
    def __post_init__(self):
        """Validate button configuration after initialization."""
        if not self.text:
            raise ValueError("Button text cannot be empty")
        
        # Clean up text formatting for display
        self.text = self.text.replace("\\n", "\n")


@dataclass
class SplashButtonConfig:
    """Extended button configuration specifically for splash screen plugin buttons."""
    
    text: str
    icon: str
    tooltip: str
    command: Optional[Callable] = None
    plugin_id: str = ""
    button_text: Optional[str] = None  # Alternative display text
    
    @classmethod
    def from_plugin_metadata(cls, plugin_id: str, metadata: Dict[str, Any], 
                           command: Optional[Callable] = None) -> 'SplashButtonConfig':
        """Create button configuration from plugin metadata.
        
        Args:
            plugin_id: Plugin identifier
            metadata: Plugin metadata dictionary
            command: Command to execute when button is clicked
            
        Returns:
            SplashButtonConfig instance
        """
        ui_config = metadata.get("ui", {})
        splash_button = ui_config.get("splash_button", {})
        
        return cls(
            text=splash_button.get("text", "Import"),
            icon=splash_button.get("icon", "plugin-icon.png"),
            tooltip=splash_button.get("tooltip", f"Import content using {plugin_id}"),
            command=command,
            plugin_id=plugin_id,
            button_text=splash_button.get("button_text")
        )
    


@dataclass
class IconConfig:
    """Configuration for icon loading and management."""
    
    name: str
    path: Optional[Path] = None
    size: tuple[int, int] = (48, 48)
    fallback_text: Optional[str] = None
    
    def get_display_path(self, assets_dir: Path) -> Path:
        """Get the full path to the icon file.
        
        Args:
            assets_dir: Base assets directory
            
        Returns:
            Full path to icon file
        """
        if self.path and self.path.is_absolute():
            return self.path
        
        return assets_dir / "icons" / self.name


@dataclass 
class SplashLayoutConfig:
    """Configuration for splash screen layout and sizing."""
    
    window_size: tuple[int, int] = (900, 650)
    logo_max_height: int = 100  # Smaller logo for cleaner look
    
    # Main button (Open DITA) styling - Google search box inspired
    main_button_width: int = 300
    main_button_height: int = 60
    main_button_font_size: int = 14
    
    # Plugin buttons under main button
    plugin_buttons_per_row: int = 4
    plugin_button_size: int = 100
    plugin_button_padding: tuple[int, int] = (8, 8)
    
    # Plugin management button in top-right
    management_button_size: int = 80
    management_button_padding: int = 15
    
    # Spacing configuration
    logo_to_main_spacing: int = 40
    main_to_plugin_spacing: int = 35
    plugin_rows_spacing: int = 15
    
    # Core buttons that are always present
    core_buttons: Dict[str, ButtonConfig] = field(default_factory=lambda: {
        "open_dita": ButtonConfig(
            text="Open DITA Project",
            icon="dita-icon.png",
            tooltip="Open existing DITA project archive"
        ),
        "manage_plugins": ButtonConfig(
            text="Manage\nPlugins",
            icon="plugin-icon.png",
            tooltip="Install and manage plugins"
        )
    })


# Default configurations
DEFAULT_SPLASH_LAYOUT = SplashLayoutConfig()

# Default icon configurations for built-in UI elements
DEFAULT_ICONS = {
    "dita-icon.png": IconConfig("dita-icon.png", fallback_text="📄"),
    "plugin-icon.png": IconConfig("plugin-icon.png", fallback_text="🔧"),
    "default-plugin-icon.png": IconConfig("default-plugin-icon.png", fallback_text="📦"),
    "docx-icon.png": IconConfig("docx-icon.png", fallback_text="📝"),
    "pdf-icon.png": IconConfig("pdf-icon.png", fallback_text="📋"),
    "markdown-icon.png": IconConfig("markdown-icon.png", fallback_text="📖"),
    "html-icon.png": IconConfig("html-icon.png", fallback_text="🌐")
}