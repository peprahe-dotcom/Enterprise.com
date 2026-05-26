# Updater

`version.json` is a template manifest that the installed app downloads from GitHub Releases (or a static URL) to decide if an update is available.

Recommended publishing flow:

- Release tag: `vX.Y.Z`
- Assets:
  - `GodTierBot_Setup_X.Y.Z.exe` (full installer)
  - `GodTierBot_app_X.Y.Z.zip` (app-only update package)
- Update the `url` fields in the published `version.json` (or generate it automatically during release).
