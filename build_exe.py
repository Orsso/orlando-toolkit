#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Build script for creating Orlando Toolkit Windows executable
Run this script on Windows with PyInstaller installed
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def main():
    """Build the Windows executable"""
    
    # Get the current directory (should be the project root)
    project_root = Path(__file__).parent
    
    print("🔨 Building Orlando Toolkit Windows executable...")
    print(f"📁 Project root: {project_root}")
    
    # Check if PyInstaller is available
    try:
        subprocess.run([sys.executable, "-m", "PyInstaller", "--version"], 
                      check=True, capture_output=True)
        print("✅ PyInstaller is available")
    except subprocess.CalledProcessError:
        print("❌ PyInstaller not found. Install it with: pip install pyinstaller")
        return False
    
    # Clean previous builds
    dist_dir = project_root / "dist"
    build_dir = project_root / "build"
    
    for clean_path in [dist_dir, build_dir]:
        if clean_path.exists():
            if clean_path.is_file():
                clean_path.unlink()
                print(f"🗑️  Removed {clean_path.name}")
            else:
                shutil.rmtree(clean_path)
                print(f"🗑️  Removed {clean_path.name}/")
    
    # Define the build command
    icon_path = project_root / "assets" / "app_icon.ico"
    version_path = project_root / "version_info.txt"
    if not icon_path.exists():
        print(f"⚠️  Warning: Icon file not found at {icon_path}")
        icon_option = []
    else:
        icon_option = ["--icon", str(icon_path)]
        print(f"🎨 Using icon: {icon_path}")
    
    version_option = []
    if version_path.exists():
        version_option = ["--version-file", str(version_path)]
        print(f"📋 Using version info: {version_path}")
    
    # PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",                    # Single executable file
        "--windowed",                   # No console window
        "--name", "OrlandoToolkit",     # Executable name
        "--add-data", f"{project_root / 'assets'};assets",  # Include assets folder
        "--add-data", f"{project_root / 'orlando_toolkit' / 'dtd_package'};orlando_toolkit/dtd_package",  # Include DTD files
        "--hidden-import", "PIL._tkinter_finder",  # Pillow support
        "--hidden-import", "sv_ttk",    # sv-ttk theme
        "--collect-all", "sv_ttk",      # Include all sv-ttk files
        *icon_option,                   # Add icon if available
        *version_option,                # Add version info if available
        "run.py"                        # Entry point
    ]
    
    print("🔧 Running PyInstaller...")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        # Run PyInstaller
        result = subprocess.run(cmd, cwd=project_root, check=True, capture_output=True, text=True)
        print("✅ PyInstaller completed successfully!")
        
        # Check if exe was created
        exe_path = dist_dir / "OrlandoToolkit.exe"
        if exe_path.exists():
            file_size = exe_path.stat().st_size / (1024 * 1024)  # Size in MB
            print(f"🎉 Executable created: {exe_path}")
            print(f"📏 File size: {file_size:.1f} MB")
            
            # Create a release folder
            release_dir = project_root / "release"
            release_dir.mkdir(exist_ok=True)
            
            # Copy exe to release folder
            release_exe = release_dir / "OrlandoToolkit.exe"
            shutil.copy2(exe_path, release_exe)
            print(f"📦 Release copy created: {release_exe}")
            
            # Create a simple README for the release
            readme_content = """Orlando Toolkit - DOCX to DITA Converter
=============================================

This is a beta release of Orlando Toolkit.

INSTALLATION:
- No installation required
- Simply run OrlandoToolkit.exe

USAGE:
1. Launch OrlandoToolkit.exe
2. Click "Load Document (.docx)" 
3. Select your Word document
4. Fill in the metadata information
5. Review and rename images if needed
6. Click "Generate DITA Package" to export

REQUIREMENTS:
- Windows 10/11
- No additional dependencies required

For support or issues, please visit:
https://github.com/Orsso/Orlando-Toolkit

Version: Beta 1.0
"""
            
            readme_path = release_dir / "README.txt"
            readme_path.write_text(readme_content, encoding='utf-8')
            print(f"📄 README created: {readme_path}")
            
            return True
            
        else:
            print("❌ Executable not found after build")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"❌ PyInstaller failed:")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")
        return False

if __name__ == "__main__":
    success = main()
    if success:
        print("\n🎉 Build completed successfully!")
        print("📁 Check the 'release' folder for the final executable")
    else:
        print("\n❌ Build failed!")
        sys.exit(1) 