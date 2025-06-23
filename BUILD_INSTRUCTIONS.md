# Build Instructions - Windows Executable

## Prerequisites

1. **Windows 10/11** with Python 3.8+ installed
2. **Git** to clone the repository
3. **PyInstaller** (will be installed automatically)

## Quick Build Method

### Option 1: Using the Batch Script (Recommended)

1. Open Command Prompt or PowerShell
2. Navigate to the project folder:
   ```cmd
   cd path\to\orlando-dita-packager
   ```

3. Double-click `build.bat` OR run in terminal:
   ```cmd
   build.bat
   ```

4. Wait for the build to complete
5. Find your executable in the `release/` folder

### Option 2: Using Python Script

1. Install PyInstaller if not already installed:
   ```cmd
   pip install pyinstaller
   ```

2. Run the build script:
   ```cmd
   python build_exe.py
   ```

### Option 3: Manual PyInstaller (Advanced)

1. Install PyInstaller:
   ```cmd
   pip install pyinstaller
   ```

2. Build using the spec file:
   ```cmd
   pyinstaller OrlandoToolkit.spec
   ```

## What Gets Included

The executable includes:
- ✅ All Python dependencies (lxml, python-docx, Pillow, sv-ttk)
- ✅ Application icon
- ✅ DTD files for DITA validation
- ✅ Assets folder (icons, etc.)
- ✅ Modern UI theme files

## Output

After a successful build:
- **Executable**: `release/OrlandoToolkit.exe` (single file, ~50-70MB)
- **README**: `release/README.txt` (user instructions)
- **No dependencies required** for end users

## Troubleshooting

### Build Fails
- Make sure Python is in your PATH
- Try installing dependencies manually: `pip install -r requirements.txt`
- Check that all assets exist in the `assets/` folder

### Exe Doesn't Run
- The exe is built for the same architecture as your Python (x64/x86)
- Windows Defender might flag it as unknown software (normal for PyInstaller)
- Make sure the release folder contains all necessary files

### Large File Size
- This is normal for PyInstaller builds (~50-70MB)
- It includes the entire Python runtime and all dependencies
- For smaller builds, consider using PyInstaller's `--exclude-module` options

## Release Distribution

The `release/` folder contains everything needed for distribution:
```
release/
├── OrlandoToolkit.exe    # Main executable
└── README.txt            # User instructions
```

You can zip this folder and distribute it to end users.

## Version Information

The exe includes version metadata visible in Windows Properties:
- Product Name: Orlando Toolkit
- Version: 1.0.0.0 Beta
- Description: DOCX to DITA Converter
- Copyright: 2025 Orso Developer 