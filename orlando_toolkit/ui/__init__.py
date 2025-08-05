"""Orlando Toolkit UI package.

Tkinter-based widgets for document conversion workflow,
metadata configuration, and image management.

Expanded public API to expose controller and widgets for structure editing,
search, toolbar, and contextual dialogs.
"""

# Ensure subpackages are imported so relative imports have resolvable parents
from . import widgets as _widgets  # noqa: F401
from . import controllers as _controllers  # noqa: F401

from .metadata_tab import MetadataTab  # noqa: F401
from .image_tab import ImageTab  # noqa: F401
from .structure_tab import StructureTab  # noqa: F401

# Controllers
from .controllers.structure_controller import StructureController  # noqa: F401

# Widgets
from .widgets.structure_tree import StructureTreeWidget  # noqa: F401
from .widgets.search_widget import SearchWidget  # noqa: F401
from .widgets.toolbar_widget import ToolbarWidget  # noqa: F401

# Dialogs / Handlers
from .dialogs.heading_filter_dialog import HeadingFilterDialog  # noqa: F401
from .dialogs.context_menu import ContextMenuHandler  # noqa: F401

__all__: list[str] = [
    "MetadataTab",
    "ImageTab",
    "StructureTab",
    "StructureController",
    "StructureTreeWidget",
    "SearchWidget",
    "ToolbarWidget",
    "HeadingFilterDialog",
    "ContextMenuHandler",
]