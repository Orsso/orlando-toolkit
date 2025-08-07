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