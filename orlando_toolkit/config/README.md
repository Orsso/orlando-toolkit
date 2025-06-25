# orlando_toolkit.config

Loading YAML-based settings + user overrides.

Use `ConfigManager()` and call:
```python
cfg = ConfigManager()
style_map = cfg.get_style_map()
```

If PyYAML is not available the code falls back to built-in defaults, ensuring the application still runs. 