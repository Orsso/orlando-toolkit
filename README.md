#  ![output-onlinepngtools](https://github.com/user-attachments/assets/15f610f5-52c0-43c3-93fc-37ae5be11d13) Orlando Toolkit 

**Convert Word documents to DITA archives for Orlando**

This tool converts Microsoft Word (.docx) files into DITA archives that work with Orlando specifications.

## What does it do?

Orlando Toolkit takes your Word documents and converts them to DITA format (Darwin Information Typing Architecture). It preserves your text, images, and tables while making sure everything follows Orlando's technical requirements.

## Features

- Converts DOCX content (text, formatting, images, tables, lists)
- Follows Orlando DITA conventions
- Handles images automatically
- Simple GUI for configuration

## Recent Fix: Image Layout

Fixed issues where images appeared in wrong places:
- Images are now separated from text properly
- Content order is preserved
- XML structure follows Orlando standards

## Installation

### Download Ready-to-Use Version

**Don't want to install Python?** Download the latest pre-built executable from the [Releases page](https://github.com/Orsso/Orlando-Toolkit/releases).

The `.exe` file works on Windows 10/11 without any installation.

### Requirements
- Python 3.8+
- Windows, macOS, or Linux

### Setup

1. **Get the code**
   ```bash
   git clone https://github.com/Orsso/Orlando-Toolkit
   cd orlando-dita-packager
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   ```

3. **Activate it**
   - Linux/macOS: `source venv/bin/activate`
   - Windows: `venv\Scripts\activate`

4. **Install packages**
   ```bash
   pip install -r requirements.txt
   ```

## Usage

```bash
source venv/bin/activate  # Linux/macOS only
python run.py
``` 

1. Select your DOCX file
2. Fill in metadata (title, manual code, dates)
3. Set image settings (prefix, naming)
4. Generate archive

The tool creates a ZIP file with everything Orlando needs.

## Building Your Own Executable

If you want to build the executable yourself (requires Python):

```cmd
build.bat
```

Find `OrlandoToolkit.exe` in the `release/` folder.

## For Developers

### Archive Structure
- `DATA/topics/` - DITA topic files
- `DATA/media/` - Images and media
- `DATA/dtd/` - Document type definitions

### Key Files
- `docx_to_dita_converter.py` - Main conversion logic
- `docx_parser.py` - Extracts content from DOCX
- `main.py` - Application entry point
- `ui/` - GUI components

### Technical Details
- Auto-generates unique XML IDs
- Uses `outputclass` attributes for styling
- Cell-level table formatting
- Dedicated image paragraphs

## Troubleshooting

Check `logs/` folder for detailed conversion information if something goes wrong.

