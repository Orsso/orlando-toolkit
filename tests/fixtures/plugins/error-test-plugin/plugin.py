"""Error test plugin for integration testing."""

from orlando_toolkit.core.plugins.base import BasePlugin


class ErrorTestPlugin(BasePlugin):
    """Error test plugin that always fails on activation."""
    
    def get_name(self) -> str:
        """Get plugin display name."""
        return "Error Test Plugin"
    
    def get_description(self) -> str:
        """Get plugin description."""
        return "A plugin for testing error handling"
    
    def on_activate(self) -> None:
        """Fail activation to test error handling."""
        super().on_activate()
        
        # This will cause the plugin to enter ERROR state
        raise RuntimeError("Error test plugin intentionally fails on activation")