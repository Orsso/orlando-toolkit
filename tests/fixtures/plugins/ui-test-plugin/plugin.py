"""UI test plugin for integration testing."""

from unittest.mock import Mock

from orlando_toolkit.core.plugins.base import BasePlugin


class TestMarkerProvider:
    """Test marker provider for UI integration testing."""
    
    def get_markers(self, dita_context):
        """Generate test markers for the structure tree."""
        if not dita_context:
            return []
            
        return [
            {
                'position': 100,
                'color': '#FF0000',
                'tooltip': 'Test marker 1',
                'type': 'test'
            },
            {
                'position': 250, 
                'color': '#00FF00',
                'tooltip': 'Test marker 2',
                'type': 'test'
            },
            {
                'position': 400,
                'color': '#0000FF', 
                'tooltip': 'Test marker 3',
                'type': 'test'
            }
        ]


class TestPanel:
    """Test panel widget for right panel integration testing."""
    
    def __init__(self):
        self.parent = None
        self.visible = True
        self.title = "Test Panel"
        self.content = "This is a test panel for integration testing."
    
    def setParent(self, parent):
        """Set parent widget (Qt-style)."""
        self.parent = parent
    
    def setVisible(self, visible):
        """Set visibility (Qt-style)."""
        self.visible = visible
    
    def show(self):
        """Show the panel."""
        self.visible = True
    
    def hide(self):
        """Hide the panel."""
        self.visible = False


class UITestPlugin(BasePlugin):
    """UI test plugin implementation."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_panel = None
        self.marker_provider = None
    
    def get_name(self) -> str:
        """Get plugin display name."""
        return "UI Test Plugin"
    
    def get_description(self) -> str:
        """Get plugin description."""
        return "A plugin for testing UI extensions"
    
    def on_activate(self) -> None:
        """Register UI extensions when activated."""
        super().on_activate()
        
        # Create and register test panel factory
        def create_test_panel():
            return TestPanel()
        
        if hasattr(self.app_context, 'ui_registry') and self.app_context.ui_registry:
            self.app_context.ui_registry.register_panel_factory(
                "test-panel", create_test_panel, self.plugin_id
            )
        
        # Create and register marker provider
        self.marker_provider = TestMarkerProvider()
        if hasattr(self.app_context, 'ui_registry') and self.app_context.ui_registry:
            self.app_context.ui_registry.register_marker_provider(
                self.plugin_id, self.marker_provider
            )
        
        self.log_info("UI test plugin activated with UI extensions")
    
    def on_deactivate(self) -> None:
        """Cleanup UI extensions when deactivated."""
        super().on_deactivate()
        
        # Unregister UI extensions
        if hasattr(self.app_context, 'ui_registry') and self.app_context.ui_registry:
            self.app_context.ui_registry.unregister_panel_factory("test-panel", self.plugin_id)
            self.app_context.ui_registry.unregister_marker_provider(self.plugin_id, "test")
        
        self.log_info("UI test plugin deactivated, UI extensions cleaned up")