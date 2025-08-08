# Project Structure & Organization

## Root Directory Layout
```
orlando_toolkit/
├── assets/                 # Application icons and visual resources
├── docs/                   # Architecture and design documentation
├── orlando_toolkit/        # Main Python package
├── tests/                  # Unit and integration tests
├── build.bat              # Windows build automation script
├── build_exe.py           # PyInstaller build configuration
├── run.py                 # Application entry point
├── requirements.txt       # Python dependencies
└── README.md              # Project documentation
```

## Core Package Structure
```
orlando_toolkit/
├── app.py                 # Main Tkinter GUI application
├── logging_config.py      # Centralized logging setup
├── core/                  # Business logic (GUI-agnostic)
│   ├── models/           # Data structures (DitaContext, etc.)
│   ├── parser/           # Word document parsing utilities
│   ├── converter/        # DOCX to DITA conversion logic
│   ├── generators/       # XML builders and DITA generators
│   ├── services/         # High-level business services
│   ├── preview/          # Document preview functionality
│   ├── merge.py          # Topic merging utilities
│   └── utils.py          # Common helper functions
├── config/               # Configuration management
│   ├── manager.py        # YAML configuration loader
│   └── *.yml            # Default configuration files
├── ui/                   # Tkinter GUI components
│   ├── controllers/      # UI event handlers
│   ├── dialogs/          # Modal dialogs
│   ├── widgets/          # Custom UI components
│   ├── *_tab.py         # Main application tabs
│   └── custom_widgets.py # Reusable UI elements
└── (no bundled DTDs)     # Packages reference PUBLIC IDs; no embedded DTDs
```

## Architecture Principles

### Layered Dependencies
- **GUI Layer** (`app.py`, `ui/`) → **Service Layer** (`core/services/`) → **Core Logic** (`core/converter/`, `core/parser/`)
- **Import-only downward** - upper layers depend on lower layers, never vice versa
- **No circular dependencies** between modules

### Module Responsibilities
- **`core/models/`** - Immutable data structures, no business logic
- **`core/parser/`** - Word document analysis and extraction
- **`core/converter/`** - Pure conversion functions (stateless)
- **`core/generators/`** - XML building and DITA output generation
- **`core/services/`** - Orchestration and I/O operations
- **`ui/`** - Tkinter widgets and user interaction

### File Naming Conventions
- **Snake_case** for Python modules and functions
- **PascalCase** for classes
- **Descriptive names** that indicate purpose (e.g., `docx_to_dita.py`, `style_analyzer.py`)
- **Tab suffix** for UI components (e.g., `metadata_tab.py`)

## Testing Structure
```
tests/
├── core/                 # Tests for business logic
│   ├── test_converter.py
│   ├── test_parser.py
│   └── test_services.py
└── ui/                   # Tests for GUI components
    └── test_widgets.py
```

## Configuration Locations
- **Bundled defaults** - `orlando_toolkit/config/*.yml`
- **User overrides** - `~/.orlando_toolkit/`
- **Runtime logs** - `./logs/` (configurable via `ORLANDO_LOG_DIR`)
- **Temp files** - OS temp directory (auto-cleanup)

## Import Patterns
- **Public API** - Import from package root: `from orlando_toolkit import DitaContext`
- **Internal modules** - Use relative imports within package
- **External dependencies** - Import at module level, handle ImportError gracefully
- **GUI imports** - Keep Tkinter imports isolated to UI modules