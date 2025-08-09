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

Sections today:
- `color_rules` – packaged default (`default_color_rules.yml`) used by inline color → `outputclass` mapping.
- `style_map` – optional user mapping of Word styles → heading level (override file name: `default_style_map.yml`).
- `image_naming` – reserved for future image naming templates (`image_naming.yml`).
- `logging` – optional dictConfig (`logging.yml`).

User overrides (filenames under `~/.orlando_toolkit/`):
- `default_style_map.yml`, `default_color_rules.yml`, `image_naming.yml`, `logging.yml`

Links:
- Architecture: [docs/architecture_overview.md](../../docs/architecture_overview.md)
- Runtime flow: [docs/runtime_flow.md](../../docs/runtime_flow.md)