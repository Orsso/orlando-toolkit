#!/usr/bin/env python3
"""
Dev mode launcher for Orlando Toolkit.

This script launches Orlando Toolkit with dev mode enabled,
which loads plugins from the local ./plugins/ directory
instead of the user's installed plugins directory.
"""

import os
import sys
from pathlib import Path

def main():
    """Launch Orlando Toolkit in development mode."""
    
    print("🚧 Starting Orlando Toolkit in DEV MODE")
    print(f"📁 Plugin directory: {Path.cwd() / 'plugins'}")
    
    # Check if plugins directory exists
    plugins_dir = Path.cwd() / 'plugins'
    if not plugins_dir.exists():
        print(f"❌ ERROR: Plugins directory not found: {plugins_dir}")
        print("   Create the plugins directory and add your plugins there.")
        sys.exit(1)
    
    # List available plugins
    plugin_dirs = [d for d in plugins_dir.iterdir() if d.is_dir() and (d / 'plugin.json').exists()]
    if plugin_dirs:
        print(f"📦 Found {len(plugin_dirs)} plugin(s):")
        for plugin_dir in plugin_dirs:
            print(f"   - {plugin_dir.name}")
    else:
        print("⚠️  No plugins found in ./plugins/ directory")
    
    print()
    
    # Set environment variable to enable dev mode
    os.environ['ORLANDO_DEV_MODE'] = '1'
    
    # Import and run the normal launcher
    try:
        from run import main as run_main
        run_main()
    except ImportError:
        print("❌ ERROR: Could not import run.py - make sure you're in the orlando-toolkit directory")
        sys.exit(1)
    except Exception as e:
        print(f"❌ ERROR: Failed to launch application: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()