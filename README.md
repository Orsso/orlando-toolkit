# Orlando Toolkit

**Professional DOCX to DITA converter for Orlando software**

Orlando Toolkit converts Microsoft Word documents (.docx) to DITA archives compliant with Orlando software specifications.

## Features

- **Automated conversion**: Complete transformation of DOCX content (text, formatting, images, tables, lists)
- **Orlando compliance**: Strict adherence to Orlando-specific DITA conventions
- **Media handling**: Automatic extraction and integration of images
- **GUI interface**: User-friendly interface for metadata configuration

## Recent Fix: Image Layout Correction

This version addresses critical image placement issues:
- **Separates images from text content** preventing layout conflicts
- **Preserves logical content order** (text followed by associated images)
- **Generates compliant XML structure** according to Orlando standards

## Installation

### Prerequisites
- Python 3.8+
- Windows, macOS, or Linux

### Setup
```bash
git clone httpd://github.com/Orsso/Orlando-Toolkit
cd orlando-dita-packager
python -m venv venv
source venv/bin/activate  # Linux/macOS: venv\Scripts\activate on Windows
pip install -r requirements.txt    
```

## Usage

```bash
source venv/bin/activate  # Linux/macOS only
python run.py
``` 

1. Select DOCX document
2. Configure metadata (title, manual code, dates)
3. Set image parameters (prefix, nomenclature)
4. Generate DITA archive

## Technical Implementation

### Orlando DITA Specifications
- **Archive structure**: `DATA/topics/`, `DATA/media/`, `DATA/dtd/` organization
- **Unique identifiers**: Automatic ID assignment for all XML elements
- **Formatting classes**: Styling via `outputclass` attributes
- **Table structure**: Cell-level border attributes
- **Image handling**: Dedicated paragraphs for images, separated from text

### Core Modules
- `docx_to_dita_converter.py`: Main conversion engine
- `docx_parser.py`: DOCX content extraction
- `main.py`: Application orchestration
- `ui/`: GUI components

## Building Windows Executable

### Quick Build (Recommended)

1. **On Windows**, navigate to the project folder
2. Double-click `build.bat` OR run:
   ```cmd
   build.bat
   ```
3. Find your executable in the `release/` folder

### Manual Build

1. Install PyInstaller:
   ```cmd
   pip install pyinstaller
   ```

2. Run the build script:
   ```cmd
   python build_exe.py
   ```

### Build Output

- **Executable**: `release/OrlandoToolkit.exe` (~50-70MB, no dependencies)
- **User guide**: `release/README.txt`
- **Complete package**: Ready for distribution

The executable includes all dependencies and can run on any Windows 10/11 system without requiring Python installation.

## Support

Conversion logs are generated in `logs/` for troubleshooting.
