# ![Orlando Toolkit](https://github.com/user-attachments/assets/15f610f5-52c0-43c3-93fc-37ae5be11d13) Orlando Toolkit

A focused desktop application for DITA document processing with plugin-based format conversion support.

## Overview

Orlando Toolkit provides a streamlined interface for working with DITA (Darwin Information Typing Architecture) documents:

**Core Features:**
- **DITA-Only Mode**: Native DITA archive (.zip) processing and editing
- **Structure Editing**: Visual tree-based topic and section management  
- **Live Preview**: Real-time DITA document rendering
- **Plugin Architecture**: Extensible format conversion via plugins

**Supported Workflows:**
- Open and edit existing DITA archives
- Import from external formats (via plugins)
- Structure manipulation and topic organization
- Export ready-to-use DITA packages

## Installation

**Quick Install:** Download and run the [Installer](https://github.com/Orsso/orlando-toolkit/releases/download/Installer/OTK_Installer.bat)

**From Source:**
```bash
git clone https://github.com/Orsso/orlando-toolkit
cd orlando-toolkit
python -m pip install -r requirements.txt
python run.py
```

## Plugin System

Orlando Toolkit supports format conversion through a plugin architecture where plugins are installed from standalone GitHub repositories:

**Plugin Installation:**
1. Open Plugin Management from the splash screen
2. Enter a GitHub repository URL (e.g., `https://github.com/orsso/orlando-docx-plugin`)
3. Click "Import Plugin" to download and install
4. Activate the plugin to enable functionality

**Available Plugins:**
- **DOCX Plugin**: [orlando-docx-plugin](https://github.com/orsso/orlando-docx-plugin) — Convert Microsoft Word documents to DITA
- **Video Library Plugin**: [orlando-video-plugin](https://github.com/orsso/orlando-video-plugin) — Convert video files to DITA with inline preview
- **Plugin Development**: [docs/PLUGIN_DEVELOPMENT_GUIDE.md](docs/PLUGIN_DEVELOPMENT_GUIDE.md)

**Plugin Management:**
- Plugins install to `~/.orlando_toolkit/plugins/` (Unix) or `%LOCALAPPDATA%\OrlandoToolkit\plugins` (Windows)
- Each plugin is a standalone GitHub repository with complete packaging
- Plugin updates are managed through repository versions

*Note : plug-ins are NOT tested under Unix based systems, tinkering might be required*

## Getting Started

1. **DITA-Only Mode**: Open existing DITA archives directly 
2. **Plugin Mode**: Install plugins to convert from other formats
3. **Structure Editing**: Use the tree interface to reorganize topics and sections
4. **Export**: Generate complete DITA packages for downstream publishing

## Documentation

- **Plugin Development**: [docs/PLUGIN_DEVELOPMENT_GUIDE.md](docs/PLUGIN_DEVELOPMENT_GUIDE.md) - Build your own format converters
- **Architecture**: [docs/architecture_overview.md](docs/architecture_overview.md)  
- **Runtime Flow**: [docs/runtime_flow.md](docs/runtime_flow.md)
- **Configuration**: [orlando_toolkit/config/README.md](orlando_toolkit/config/README.md)

## Support

- **Issues**: Report bugs and feature requests via GitHub Issues
- **Discussions**: Community support via GitHub Discussions

## License

MIT — see `LICENSE`.

Orlando Toolkit is an independent, open‑source project and is not affiliated with "Orlando TechPubs" or Infotel. "Orlando" may be a trademark of its owner; references are for identification only.
