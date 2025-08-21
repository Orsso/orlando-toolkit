# ![Orlando Toolkit](https://github.com/user-attachments/assets/15f610f5-52c0-43c3-93fc-37ae5be11d13) Orlando Toolkit

Convert Microsoft Word (.docx) manuals into Orlando‑ready DITA projects with a clear, focused desktop app.

---

## Overview

- DOCX → DITA (map + topics)
- Extracts and normalizes images 
- Live preview 
- Edit structure 
- Export a ZIP ready for import

---

## Quick start

- Download and run the [Installer](https://github.com/Orsso/orlando-toolkit/releases/download/Installer/OTK_Installer.bat).

*Note: The script serve also as an updater.* 

### From source
```bash
git clone https://github.com/Orsso/orlando-toolkit
cd orlando-toolkit
python -m pip install -r requirements.txt
python run.py
```

---

Output layout:
- `DATA/topics/` — topics
- `DATA/media/` — images
- `DATA/<manual_code>.ditamap` — root map

---

## Documentation

- Architecture: [docs/architecture_overview.md](docs/architecture_overview.md)
- Runtime flow: [docs/runtime_flow.md](docs/runtime_flow.md)
- Configuration: [orlando_toolkit/config/README.md](orlando_toolkit/config/README.md)

---

## License & notice

MIT — see `LICENSE`.

Orlando Toolkit is an independent, open‑source project and is not affiliated with “Orlando TechPubs” or Infotel. “Orlando” may be a trademark of its owner; references are for identification only.
