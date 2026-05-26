# Master Spec

## Goal

Build a Windows 10 trading system with:

- Python application (decision engine, risk gates, logging)
- MT5 Bridge EA (MQL5) that executes orders in MT5 Desktop
- Windows installer + prompt-to-update auto-updater using GitHub Releases

## Hard Rules

- Never commit secrets to GitHub.
- Updates replace only the app binaries; user data persists.
- No trade executes if Risk Cop vetoes.
- Live trading requires an explicit manual arming step.

## Components

- Python app: core logic, risk, comms to Bridge, logging, update client.
- Bridge EA: receives commands and places/modifies/closes orders; reports fills and account state.
- Installer: installs app, creates data folders, sets startup options.
- Updater: checks GitHub Releases, downloads signed updates, applies, migrates settings/DB.

## Windows Paths

- App (replace on update): `C:\Program Files\GodTierBot\app\`
- Persistent data: `C:\ProgramData\GodTierBot\`
  - `config\settings.yaml`
  - `data\godtierbot.sqlite`
  - `models\`
  - `logs\`
  - `support_bundles\`

## Update Channel

- GitHub Releases hosts:
  - Full installer `.exe`
  - Update package asset(s)
  - `version.json` manifest (see updater/version.json)
  - Release notes (changelog)
