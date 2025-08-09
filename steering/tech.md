# Technology Stack & Build System

## Core Technologies
- **Python 3.10+** - Main programming language
- **Tkinter** - GUI framework with sv-ttk theme for modern appearance
- **lxml** - XML processing and DITA generation
- **python-docx** - Word document parsing
- **Pillow (PIL)** - Image processing and format conversion
- **PyYAML** - Configuration file handling

## Architecture Pattern
- **Layered architecture** with clear separation of concerns
- **GUI-agnostic core** - business logic separated from UI
- **Service-oriented** - ConversionService orchestrates workflows
- **Immutable data structures** - DitaContext for thread-safe operations
- **Pure functions** - stateless conversion logic in core modules

## Build System

### Development Setup
```bash
# Clone and setup
git clone https://github.com/Orsso/orlando-toolkit
cd orlando-toolkit
python -m pip install -r requirements.txt

# Launch application
python run.py
```

### Windows Executable Build
```bash
# Automated build (sets up portable Python environment if missing)
build.bat

# Manual build
python build_exe.py
```

### Build Tools
- **PyInstaller** - Creates single-file Windows executable
- **WinPython** - Portable Python runtime for Windows builds
- **build.bat** - Automated build script with dependency checking

## Key Dependencies
```
lxml - XML processing
python-docx - Word document parsing  
Pillow - Image processing
sv-ttk - Modern Tkinter theme
pyyaml - Configuration management
tkinterweb>=3.13 - HTML rendering for preview panel
```

## Logging & Configuration
- **Centralized logging** via `logging_config.py`
- **YAML-based configuration** with user overrides in `~/.orlando_toolkit/`
- **Rotating file logs** in `./logs/` directory (5MB max, 2 backups)
- **Environment variable support** for log directory (`ORLANDO_LOG_DIR`)

## Distribution
- **Windows executable** - Single file, no installation required
- **Python wheel** - Cross-platform source distribution
- **No embedded DTDs** - XML uses PUBLIC IDs; toolchains resolve via catalogs