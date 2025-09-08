# Orlando Toolkit User Guide

## Overview

Orlando Toolkit is a DITA document processor with plugin-based format conversion. Process DITA archives directly or install plugins to convert from other formats.

## Getting Started

### Installation

**Windows Executable:**
1. Download `OrlandoToolkit.exe` 
2. Run installer
3. Launch from desktop shortcut

**From Source:**
```bash
git clone <repository>
pip install -r requirements.txt
python run.py
```

### Plugin Management

**Installing Plugins:**
1. Click **Plugin Management** on home screen
2. Enter GitHub repository URL (e.g., `https://github.com/user/plugin-name`)
3. Click **Install Plugin**
4. Restart application

**Managing Plugins:**
- View installed plugins in Plugin Manager
- Enable/disable plugins as needed
- Uninstall unused plugins to save space

## Using Orlando Toolkit

### Processing Documents

**DITA Archives (Built-in):**
1. Click **Process DITA Archive**
2. Select `.zip` file containing DITA content
3. Edit structure, images, and metadata
4. Export updated archive

**Plugin-Based Conversion:**
1. Ensure appropriate plugin is installed
2. Click **Convert Document** 
3. Select supported file (DOCX, PDF, etc.)
4. Review conversion and make edits
5. Export as DITA archive

### Working with Structure

**Navigation:**
- Use tree view to browse topics and sections
- Right-click for context menu options
- Search topics with filter bar

**Editing:**
- **Move:** Use up/down buttons or the 'send to' feature in the right click contextual menu
- **Rename:** 'Rename' in the contextual menu
- **Delete:** Select and press Delete key or 'Delete' in contextual menu
- **Merge:** Use depth limits to combine deep hierarchies or multi selection + 'Merge' in contextual menu

**Plugin Features:**
- Some plugins add format-specific tools (heading filters, style markers)
- Look for additional buttons and panels when plugin documents are loaded

### Images and Metadata

**Images/Media Tab:**
- Preview embedded images (and videos when a video-capable plugin is the source)
- Rename or replace media assets
- Manage media references

**Metadata Tab:**
- Edit document title and properties
- Configure output settings
- Set manual codes and identifiers

### Export

**Creating DITA Packages:**
1. Click **Export** in any tab
2. Choose output location
3. Application creates ZIP with:
   - `DATA/topics/` - Generated DITA topics
   - `DATA/media/` - Images (and videos when supported by the plugin)  
   - `DATA/<code>.ditamap` - Main DITA map

## Plugin Ecosystem

**Available Plugin Types:**
- **Document Converters:** Convert from external formats to DITA
- **UI Extensions:** Add format-specific editing features
- **Analysis Tools:** Validate and analyze content

**Finding Plugins:**
- Check plugin repositories on GitHub
- Look for `orlando-toolkit-plugin-` prefix
- Review plugin documentation for installation

## Troubleshooting

**Common Issues:**
- **Plugin not appearing:** Verify GitHub URL and restart application
- **Conversion errors:** Check file format compatibility with installed plugins
- **Missing features:** Ensure required plugins are installed and enabled

**Getting Help:**
- Check plugin documentation for format-specific issues
- Report bugs on GitHub repository
- Review application logs in `logs/` directory

## Configuration

**User Settings:**
- Configuration files in `~/.orlando_toolkit/` (Linux/Mac) or `%LOCALAPPDATA%\OrlandoToolkit\` (Windows)
- Customize color rules, style mappings, and plugin settings
- Changes apply after application restart