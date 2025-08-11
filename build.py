#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Build script for creating Orlando Toolkit Windows executable
Renamed to build.py. This file remains temporarily for backward compatibility.
"""

import sys
import subprocess
import shutil
from pathlib import Path
from typing import List, Optional


def print_step(step_num: int, title: str) -> None:
    """Print a step header."""
    print("   +---------------------------------------------------------------------+")
    print(f"     Step {step_num}: {title}")
    print("   +---------------------------------------------------------------------+")


def print_success_box(title: str, lines: List[str]) -> None:
    """Print a success message box."""
    print("   +======================================================================+")
    print(".")
    print(f"                         {title}")
    print(".")
    for line in lines:
        print(f"     {line}")
    print(".")
    print("   +======================================================================+")


def print_error_box(title: str, lines: List[str]) -> None:
    """Print an error message box."""
    print("   +=======================================================================+")
    print(f"                              {title}")
    print("   +=======================================================================+")
    for line in lines:
        print(f"     {line}")
    print("   +=======================================================================+")


def create_desktop_shortcut(exe_path: Path) -> Optional[Path]:
    """Create a desktop shortcut using PowerShell."""
    try:
        # Get user's desktop path
        desktop_path = Path.home() / "Desktop"
        shortcut_path = desktop_path / "Orlando Toolkit.lnk"

        # PowerShell script to create shortcut
        ps_script = f"""
$WshShell = New-Object -comObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut(\"{shortcut_path}\")
$Shortcut.TargetPath = \"{exe_path}\"
$Shortcut.WorkingDirectory = \"{exe_path.parent}\"
$Shortcut.Description = \"Orlando Toolkit - DOCX to DITA Converter\"
$Shortcut.Save()
"""

        # Execute PowerShell script
        subprocess.run(["powershell", "-Command", ps_script], capture_output=True, text=True, check=True)

        return shortcut_path if shortcut_path.exists() else None

    except (subprocess.CalledProcessError, Exception):
        return None


def main() -> bool:
    """Build the Windows executable."""

    # Get the current directory (should be the project root)
    project_root = Path(__file__).parent

    # Step 1: Environment verification
    print_step(1, "Build Environment Verification")

    print(f"   Project root: {project_root}")
    print(f"   Python executable: {sys.executable}")

    # Detect Python installation type
    python_path = Path(sys.executable)
    if "python.exe" in python_path.name.lower() and python_path.parent.name.lower() != "scripts":
        install_type = "Portable Python"
    elif "python.exe" in python_path.name.lower() and "program files" in str(python_path).lower():
        install_type = "System Installation"
    else:
        install_type = "Custom Installation"

    print(f"   Installation type: {install_type}")
    print(f"   Python version: {sys.version.split()[0]}")

    # Check if tkinter is available (critical for GUI app)
    try:
        import tkinter  # noqa: F401
        import tkinter.ttk  # noqa: F401
        import tkinter.filedialog  # noqa: F401
        print("   tkinter: Available (with TTK support)")
    except ImportError as e:
        print_error_box("tkinter Not Available", [
            "tkinter module is required but not found.",
            "This is common with some portable Python distributions.",
            "",
            f"Error: {str(e)}",
            "",
            "Solutions:",
            "- Use a Python installation that includes tkinter",
            "- Install a complete Python distribution from python.org",
            "- Try a different Python distribution (e.g., official Python)",
        ])
        return False

    # Check additional GUI/optional dependencies
    missing_modules: List[str] = []

    try:
        import PIL  # noqa: F401
        print("   Pillow (PIL): Available")
    except ImportError:
        missing_modules.append("Pillow")

    try:
        import sv_ttk  # noqa: F401
        print("   sv-ttk theme: Available")
    except ImportError:
        missing_modules.append("sv-ttk")

    try:
        import tkinterweb  # noqa: F401
        print("   tkinterweb: Available")
    except Exception:
        missing_modules.append("tkinterweb")

    if missing_modules:
        print(f"   Warning: Missing optional modules: {', '.join(missing_modules)}")
        print("   These will be installed automatically if needed.")

    # Check if PyInstaller is available
    try:
        result = subprocess.run([sys.executable, "-m", "PyInstaller", "--version"], check=True, capture_output=True, text=True)
        version = result.stdout.strip()
        print(f"   PyInstaller version: {version}")
    except subprocess.CalledProcessError:
        print_error_box("PyInstaller Not Available", [
            "PyInstaller module not found.",
            "Install it with: pip install pyinstaller",
        ])
        return False

    # Step 2: Clean previous builds
    print_step(2, "Cleaning Previous Builds")

    dist_dir = project_root / "dist"
    build_dir = project_root / "build"

    cleaned_items: list[str] = []
    for clean_path in [dist_dir, build_dir]:
        if clean_path.exists():
            if clean_path.is_file():
                clean_path.unlink()
                cleaned_items.append(f"Removed file: {clean_path.name}")
            else:
                shutil.rmtree(clean_path)
                cleaned_items.append(f"Removed directory: {clean_path.name}/")

    if cleaned_items:
        for item in cleaned_items:
            print(f"   {item}")
    else:
        print("   No previous build artifacts found.")

    # Step 3: Configure build parameters
    print_step(3, "Configuring Build Parameters")

    # Check for icon file
    icon_path = project_root / "assets" / "app_icon.ico"
    if not icon_path.exists():
        print(f"   Warning: Icon file not found at {icon_path}")
        icon_option: list[str] = []
    else:
        icon_option = ["--icon", str(icon_path)]
        print(f"   Icon file: {icon_path}")

    # Check for version info
    version_path = project_root / "version_info.txt"
    version_option: list[str] = []
    if version_path.exists():
        version_option = ["--version-file", str(version_path)]
        print(f"   Version info: {version_path}")
    else:
        print("   Version info: Not configured")

    print("   Build mode: Single executable file")
    print("   Window mode: No console window")
    print("   Output name: OrlandoToolkit.exe")

    # Step 4: Execute PyInstaller
    print_step(4, "Executing PyInstaller")

    # PyInstaller command - robust for different Python installations
    cmd: List[str] = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",  # Single executable file
        "--windowed",  # No console window
        "--name",
        "OrlandoToolkit",  # Executable name
        "--clean",  # Clean PyInstaller cache
        "--noconfirm",  # Overwrite output without asking
        "--icon",
        str(project_root / "assets" / "app_icon.ico"),
        "--add-data",
        f"{project_root / 'assets'};assets",  # Include assets folder
        "--add-data",
        f"{project_root / 'orlando_toolkit' / 'config'};orlando_toolkit/config",  # Include config data
        "--hidden-import",
        "tkinter",
        "--hidden-import",
        "tkinter.ttk",
        "--hidden-import",
        "tkinter.filedialog",
        "--hidden-import",
        "tkinter.messagebox",
        "--hidden-import",
        "tkinter.scrolledtext",
        "--hidden-import",
        "tkinter.font",
        "--hidden-import",
        "tkinter.constants",
    ]

    # Add optional imports only if modules are available
    if "Pillow" not in missing_modules:
        cmd.extend(["--hidden-import", "PIL._tkinter_finder"])

    if "sv-ttk" not in missing_modules:
        cmd.extend([
            "--hidden-import",
            "sv_ttk",
            "--collect-all",
            "sv_ttk",
        ])

    if "tkinterweb" not in missing_modules:
        cmd.extend([
            "--hidden-import",
            "tkinterweb",
            "--collect-all",
            "tkinterweb",
        ])

    # Add icon and version options
    cmd.extend(icon_option)
    cmd.extend(version_option)
    cmd.append("run.py")  # Entry point

    print("   Starting PyInstaller compilation...")
    print("   +---------------------------------------------------------------------+")
    print("     ======================================== Compiling")
    print("   +---------------------------------------------------------------------+")

    try:
        # Run PyInstaller with real-time output
        subprocess.run(cmd, cwd=project_root, check=True)

        # Step 5: Verify build output
        print_step(5, "Build Verification")

        # Check if exe was created
        dist_dir = project_root / "dist"
        exe_path = dist_dir / "OrlandoToolkit.exe"
        if exe_path.exists():
            file_size = exe_path.stat().st_size / (1024 * 1024)  # Size in MB
            print(f"   Executable created: {exe_path}")
            print(f"   File size: {file_size:.1f} MB")

            # Create a release folder
            release_dir = project_root / "release"
            release_dir.mkdir(exist_ok=True)

            # Copy exe to release folder
            release_exe = release_dir / "OrlandoToolkit.exe"
            shutil.copy2(exe_path, release_exe)
            print(f"   Release copy: {release_exe}")

            print_success_box(
                "Build Completed Successfully",
                [
                    "OrlandoToolkit.exe has been created.",
                    "",
                    f"Location: .\\release\\OrlandoToolkit.exe",
                    f"Size: {file_size:.1f} MB",
                    "",
                    "The executable is ready for distribution.",
                ],
            )

            return True

        else:
            print_error_box(
                "Build Verification Failed",
                [
                    "Executable not found after compilation.",
                    "Check PyInstaller output for errors.",
                ],
            )
            return False

    except subprocess.CalledProcessError:
        print_error_box(
            "PyInstaller Compilation Failed",
            [
                "The compilation process encountered an error.",
                "Check the output above for detailed error information.",
                "Common issues: missing dependencies, file permissions.",
            ],
        )
        return False
    except KeyboardInterrupt:
        print_error_box(
            "Build Cancelled",
            [
                "Build process was interrupted by user.",
                "Partial build files may remain in dist/ and build/ directories.",
            ],
        )
        return False


if __name__ == "__main__":
    success = main()
    if not success:
        sys.exit(1)