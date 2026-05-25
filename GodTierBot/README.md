# GodTierBot (Windows Installer + MT5 Bridge)

This project generates a Windows installer that runs a local trading bot app and installs an MT5 Expert Advisor bridge into your MT5 Data Folder.

## What Runs Where

- MT5 chart: `GodTierBridge` (MQL5 EA)
- Windows app: `GodTierBot` (Python packaged as an EXE)
- EA talks to the app via `http://127.0.0.1:8080` using MT5 `WebRequest`

## Fast Setup (Laptop)

1. Make sure MT5 Desktop is installed and you can log in.
2. Run `GodTierBot-Setup.exe`.
3. In MT5:
   - Tools → Options → Expert Advisors → enable “Allow WebRequest for listed URL”
   - Add: `http://127.0.0.1:8080`
4. Drag `GodTierBridge` onto any chart and enable AutoTrading.

## Build The Installer (Windows)

### Prereqs

- Python 3.11 (Windows)
- Inno Setup (Windows)

### Build

From a Windows terminal in the repo folder:

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python installer\build.py
```

Output:

- `dist_installer\GodTierBot-Setup.exe`

## Repo Layout

- `app\godtierbot\` Python app (API + desktop UI + tray)
- `mql5_bridge\` MT5 EA source
- `installer\` PyInstaller + Inno Setup build scripts

