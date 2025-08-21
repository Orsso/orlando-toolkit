# ![Orlando Toolkit](https://github.com/user-attachments/assets/15f610f5-52c0-43c3-93fc-37ae5be11d13) Orlando Toolkit

Convert Microsoft Word (.docx) manuals into Orlando‑ready DITA projects with an approachable desktop UI.

---

## Overview

Orlando Toolkit parses a .docx, builds a DITA map with topics, extracts images, and produces a ZIP archive ready for import into Orlando. A built‑in preview and structure editor help you validate the result before exporting.


### Features

- DOCX → DITA conversion: headings, lists, tables, inline styles
- Orlando‑compliant DITA map and topic files
- Image extraction and normalization to PNG for reliable preview
- Live preview (HTML when available, safe XML/text fallback)
- Structure editing: move up/down, rename, delete
- Depth‑limit merge with optional style exclusions (Structure tab)
- Undo/redo for structure changes
- One‑click ZIP packaging for import
- YAML‑based configuration with user overrides

## Disclaimer

Orlando Toolkit is an independent, open-source project and is not affiliated with 'Orlando TechPubs' or Infotel. 'Orlando' and any related names may be trademarks of their respective owners. Any references are for identification and descriptive purposes only.

---

## Quick start

### Windows installer (runtime bundle)

Recommended:
```bat
install.bat
```

What `install.bat` does now:
- Downloads a prebuilt runtime bundle ZIP from GitHub Releases
- Extracts to `%LOCALAPPDATA%\OrlandoToolkit\AppRuntime` using an atomic swap
- Creates a desktop shortcut that launches `launch.cmd` (runs `pythonw.exe` with the app)
- Logs to `%LOCALAPPDATA%\OrlandoToolkit\Logs\deploy-<timestamp>.log`


### Run from source

Requirements: Python 3.10+ (Windows/macOS/Linux)

```bash
git clone https://github.com/Orsso/orlando-toolkit
cd orlando-toolkit
python -m pip install -r requirements.txt
python run.py
```

---

## Using the app

1. Load a .docx
2. Optionally adjust metadata
3. Review structure and images; toggle depth merge if needed
4. Export → creates a ZIP with DITA map, topics, and media

Output layout:
- `DATA/topics/` – generated DITA topics
- `DATA/media/` – extracted images
- `DATA/<manual_code>.ditamap` – root map with metadata

---

## Documentation

- Architecture: [docs/architecture_overview.md](docs/architecture_overview.md)
- Runtime flow: [docs/runtime_flow.md](docs/runtime_flow.md)
- Core layer: [orlando_toolkit/core/README.md](orlando_toolkit/core/README.md)
- UI layer: [orlando_toolkit/ui/README.md](orlando_toolkit/ui/README.md)
- Config: [orlando_toolkit/config/README.md](orlando_toolkit/config/README.md)

---

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

