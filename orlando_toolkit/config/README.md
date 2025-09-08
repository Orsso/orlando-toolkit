# orlando_toolkit.config

YAML-based settings with user overrides.

Use `ConfigManager()`:
```python
from orlando_toolkit.config import ConfigManager
cfg = ConfigManager()
style_map = cfg.get_style_map()
preview_styles = cfg.get_preview_styles()
image_naming = cfg.get_image_naming()
```

Behavior:
- Loads packaged defaults, then merges user overrides from `%LOCALAPPDATA%\\OrlandoToolkit\\config` (Windows) or `~/.orlando_toolkit/` (Unix).
- Safe fallbacks if PyYAML is missing (built-in empty dicts).
- Many format-specific settings are now owned by plugins; core only exposes the sections below.

Sections:
- `preview_styles` – outputclass → CSS mapping for HTML preview (`preview_styles.yml`).
- `style_map` – Word styles → heading level mapping (`default_style_map.yml`).
- `image_naming` – image filename generation templates (`image_naming.yml`).
- `logging` – logging configuration using Python dictConfig format (`logging.yml`).

User overrides (filenames under `%LOCALAPPDATA%\\OrlandoToolkit\\config` on Windows or `~/.orlando_toolkit/` on Unix):
- `default_style_map.yml`, `preview_styles.yml`, `image_naming.yml`, `logging.yml`

## Configuration Schemas

### image_naming.yml

Controls how extracted images are renamed during export:

```yaml
# Prefix for all image filenames
prefix: "IMG"

# Naming pattern with tokens:
#   {prefix} - The prefix value above
#   {manual_code} - Manual code from metadata
#   {section} - Section number (e.g., "1", "2-1", "3-2-1")
#   {-index} - Image index within section (only added when multiple images)
#   {ext} - Original file extension
pattern: "{prefix}-{manual_code}-{section}{-index}{ext}"

# Starting number for image indices within each section
index_start: 1

# Zero-padding for image indices (0 = no padding, 2 = "01", "02", etc.)
index_zero_pad: 0
```

### preview_styles.yml

Maps DITA outputclass values to CSS for HTML preview rendering. Example:

```yaml
css_styles:
  background-color-yellow: 'background-color:#fff2cc;'
  color-blue: 'color:#0070c0;'
```

Notes:
- These styles affect preview only; they do not change exported DITA.
- Override by placing `preview_styles.yml` in the user config directory.

### logging.yml

Standard Python dictConfig format for logging configuration. See Python documentation for complete schema.

### default_style_map.yml

Maps Word style names to heading levels:

```yaml
# Example entries:
"Heading 1": 1
"Heading 2": 2
"Title": 1
"Chapter": 1
```

Links:
- Architecture: [docs/architecture_overview.md](../../docs/architecture_overview.md)
- Runtime flow: [docs/runtime_flow.md](../../docs/runtime_flow.md)
- Plugin development: [docs/PLUGIN_DEVELOPMENT_GUIDE.md](../../docs/PLUGIN_DEVELOPMENT_GUIDE.md)
- Plugin configuration: see each plugin's `config.yml` and documentation
