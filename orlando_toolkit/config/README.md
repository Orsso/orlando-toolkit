# orlando_toolkit.config

Loading YAML-based settings + user overrides.

Use `ConfigManager()` and call:
```python
cfg = ConfigManager()
style_map = cfg.get_style_map()
```

If PyYAML is not available the code falls back to built-in defaults, ensuring the application still runs.

Sections available:
- `style_map`: map Word style names to heading levels.
- `color_rules`: convert text colours/highlights to DITA `outputclass`.
- `image_naming`: reserved for future image naming templates.
- `logging`: optional dictConfig overrides.