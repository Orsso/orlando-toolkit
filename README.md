# Orlando Toolkit

![Orlando Toolkit](https://github.com/user-attachments/assets/15f610f5-52c0-43c3-93fc-37ae5be11d13)

**Convert Word documents to DITA archives for Orlando**

---

## Overview

Orlando Toolkit converts Microsoft Word (.docx) files into DITA archives that comply with Orlando specifications. It preserves your text, images, and tables while ensuring everything follows Orlando's technical requirements.

### Key Features

- **DOCX to DITA conversion** - Text, formatting, images, tables, and lists
- **Orlando compliance** - Follows Orlando-specific DITA conventions  
- **Automatic image handling** - Extracts and processes images correctly
- **User-friendly interface** - Simple GUI for metadata configuration

### Recent Improvements

✅ **Fixed image layout issues** - Images now appear in correct positions  
✅ **Preserved content order** - Logical flow maintained during conversion  
✅ **Orlando-compliant XML** - Generated structure follows standards  

---

## Quick Start

### Option 1: Download Pre-built Version (Recommended)

**No Python installation required**

1. Go to [Releases](https://github.com/Orsso/orlando-toolkit/releases)
2. Download the latest `.exe` file
3. Run directly on Windows 10/11

### Option 2: Install from Source

**For developers or customization**

#### Installation Steps

**Requirements:** Python 3.8+, Windows/macOS/Linux

```bash
# 1. Clone repository
git clone https://github.com/Orsso/orlando-toolkit
cd orlando-dita-packager

# 2. Create virtual environment
python -m venv venv

# 3. Activate environment
source venv/bin/activate    # Linux/macOS
# venv\Scripts\activate     # Windows

# 4. Install dependencies
pip install -r requirements.txt
```

---

## Usage

### Starting the Application

```bash
# Activate environment (if using source install)
source venv/bin/activate  # Linux/macOS only

# Run application
python run.py
```

### Conversion Process

1. **📁 Select DOCX file** - Choose your Word document
2. **📝 Configure metadata** - Title, manual code, dates
3. **🖼️ Set image options** - Prefix and naming conventions
4. **⚡ Generate archive** - Creates ZIP with all Orlando files

**Output**: Complete DITA archive ready for Orlando import

---

## Advanced Usage

### Building Executable

Create an exe from source code.

```cmd
build.bat
```

Output: `release/OrlandoToolkit.exe`

### Project Structure

```
orlando-dita-packager/
├── src/
│   ├── docx_to_dita_converter.py  # Main conversion engine
│   ├── docx_parser.py             # DOCX content extraction
│   ├── main.py                    # Application entry point
│   └── ui/                        # GUI components
├── logs/                          # Conversion logs
└── release/                       # Built executables
```

### Orlando DITA Specifications

| Component | Purpose |
|-----------|---------|
| `DATA/topics/` | DITA topic files |
| `DATA/media/` | Images and media assets |
| `DATA/dtd/` | Document type definitions |

**Technical Features:**
- Auto-generated unique XML IDs
- `outputclass` attribute styling
- Cell-level table formatting
- Dedicated image paragraphs

---

## Support

### Troubleshooting

**Conversion issues?** Check the `logs/` folder for detailed diagnostic information.

**Common solutions:**
- Ensure DOCX file is not corrupted
- Verify all required metadata is provided
- Check image file formats are supported


---

*Orlando Toolkit - Streamlining DITA conversion workflows*

