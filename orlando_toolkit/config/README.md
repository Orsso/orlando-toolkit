# orlando_toolkit.config

YAML-based settings with user overrides.

Use `ConfigManager()`:
```python
from orlando_toolkit.config import ConfigManager
cfg = ConfigManager()
style_map = cfg.get_style_map()
color_rules = cfg.get_color_rules()
```

Behavior:
- Loads packaged defaults when available, then merges user overrides from `~/.orlando_toolkit/`.
- Safe fallbacks if PyYAML is missing (built-in empty dicts).

Sections:
- `color_rules` – packaged default (`default_color_rules.yml`) used by inline color → `outputclass` mapping.
- `style_map` – Word styles → heading level mapping (`default_style_map.yml`).
- `image_naming` – image filename generation templates (`image_naming.yml`).
- `logging` – logging configuration using Python dictConfig format (`logging.yml`).
- `style_detection` – document structure analysis behavior (`style_detection.yml`).

User overrides (filenames under `~/.orlando_toolkit/`):
- `default_style_map.yml`, `default_color_rules.yml`, `image_naming.yml`, `logging.yml`, `style_detection.yml`

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

### style_detection.yml

Controls document structure analysis behavior:

```yaml
# Enable enhanced style detection algorithm
use_enhanced_style_detection: true

# Use structural analysis to improve heading detection
use_structural_analysis: true

# Minimum number of following paragraphs to consider when analyzing structure
min_following_paragraphs: 3

# Enable generic heading pattern matching (e.g., "HEADING 5 GM")
generic_heading_match: true
```

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