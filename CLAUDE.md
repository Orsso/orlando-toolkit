# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Application
```bash
# Run from source
python run.py

# Build Windows executable
build.bat
```

### Testing
```bash
# Run tests from repository root
python -m pytest tests/

# Run specific test file
python -m pytest tests/core/services/test_structure_editing_service.py

# Run with verbose output
python -m pytest -v tests/
```

### Dependencies
```bash
# Install requirements
python -m pip install -r requirements.txt

# Core dependencies: lxml, python-docx, Pillow, sv-ttk, pyyaml
# HTML preview engine: tkinterweb (used by Structure tab preview)
```

## Architecture Overview

Orlando Toolkit follows a layered architecture converting Word documents (.docx) to DITA XML packages:

### Core Components
- **`orlando_toolkit/app.py`** - Main Tkinter GUI application entry point
- **`orlando_toolkit/core/services/conversion_service.py`** - Business logic facade with no GUI dependencies
- **`orlando_toolkit/core/converter/`** - Pure DOCX→DITA transformation functions
- **`orlando_toolkit/core/parser/`** - Word document parsing and analysis utilities
- **`orlando_toolkit/core/generators/`** - DITA XML builders for tables and structures
- **`orlando_toolkit/core/models/`** - Immutable data structures (`DitaContext`, `EditJournal`)
- **`orlando_toolkit/ui/`** - Tkinter UI components organized by tabs and widgets

### Key Data Flow
1. User selects `.docx` file via GUI
2. `ConversionService.convert()` delegates to `core.converter.convert_docx_to_dita()`
3. Parser extracts images, headings, and structure via `core.parser.*`
4. Generators emit DITA topics/maps and populate `DitaContext`
5. Service handles packaging, file naming, and ZIP archive creation

### Services Architecture
- **`StructureEditingService`** - Handles topic manipulation, depth merging, and structural changes
- **`UndoService`** - Manages undo/redo operations for structure editing
- **`PreviewService`** - Handles XML preview generation and compilation

### Preview System Architecture

The Structure tab preview panel supports multiple rendering modes:

**Core Components:**
- **`PreviewPanel`** (`ui/widgets/preview_panel.py`) - UI widget with HTML/XML mode toggle
- **`PreviewService`** (`core/services/preview_service.py`) - Business logic for preview generation
- **`xml_compiler`** (`core/preview/xml_compiler.py`) - XSLT transformation and HTML generation

**Rendering Pipeline:**
1. Topic selection triggers `PreviewService.render_html_preview()`
2. `xml_compiler.render_html_preview()` applies XSLT transformation to DITA XML
3. HTML post-processing adds inline styles compatible with `tkhtmlview`
4. Images with data URIs are extracted to temporary files for display
5. `PreviewPanel` renders using `HTMLScrolledText` or falls back to plain `ScrolledText`

**Optional Dependency Handling:**
- `tkhtmlview` import is wrapped in try/except with graceful fallback
- `HTML_RENDERING_AVAILABLE` flag controls feature availability
- Automatic fallback to plain text mode if HTML rendering fails

**Image Processing:**
- DOCX images stored in `DitaContext.images` as binary data
- XSLT converts to data URIs for embedded display
- Post-processor saves data URIs to temp files (`%TEMP%/orlando_preview/`)
- `tkhtmlview` displays images from file paths, not data URIs

**Error Handling:**
- Multiple fallback layers: HTML rendering → plain text → error message
- All exceptions caught to prevent UI crashes
- Detailed error information in service layer for debugging

## Testing Patterns

Tests are located in `tests/` mirroring the source structure:
- `tests/core/services/` - Service layer integration and unit tests
- `tests/ui/` - UI component tests
- Test fixtures in `tests/fixtures/` (includes `.docx` test files)
- `conftest.py` provides common fixtures and ensures project root is importable

When writing tests:
- Use `pytest.importorskip()` for optional dependencies
- Follow existing fixture patterns for `DitaContext` and XML structures
- Place test Word documents in `tests/fixtures/`

## Configuration System

`ConfigManager` loads YAML configurations:
- Built-in defaults in the package
- User overrides in `~/.orlando_toolkit/`
- Sections: `style_map`, `color_rules`, `image_naming`, `logging`
- Falls back gracefully if PyYAML is missing

## Code Conventions

- Pure functions preferred in core conversion logic
- Services layer for orchestration and I/O operations
- Immutable data structures where possible (`DitaContext`)
- Clear separation: GUI → Services → Core → Utils
- Type hints throughout codebase
- Comprehensive logging via `logging_config.py`

## Build Process

The project supports multiple deployment methods:
- **Source**: Direct Python execution via `run.py`
- **Executable**: Windows build via `build.bat` → `build_exe.py` → PyInstaller
- **Package**: PEP 517 wheel distribution

The build script auto-installs Python 3.13 via winget if missing on Windows.