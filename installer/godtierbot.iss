[Setup]
AppId={{E2A1D7E0-8AE6-4B3A-8A74-5D7B64B7C3A2}
AppName=GodTierBot
AppVersion=0.1.0
DefaultDirName={pf}\GodTierBot
DefaultGroupName=GodTierBot
DisableProgramGroupPage=yes
OutputBaseFilename=GodTierBot_Setup_0.1.0
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin

[Dirs]
Name: "{commonappdata}\GodTierBot"
Name: "{commonappdata}\GodTierBot\config"
Name: "{commonappdata}\GodTierBot\data"
Name: "{commonappdata}\GodTierBot\models"
Name: "{commonappdata}\GodTierBot\logs"
Name: "{commonappdata}\GodTierBot\cache"
Name: "{commonappdata}\GodTierBot\support_bundles"

[Files]
Source: "..\dist\GodTierBot\*"; DestDir: "{app}\app"; Flags: recursesubdirs createallsubdirs
Source: "..\docs\*"; DestDir: "{app}\docs"; Flags: recursesubdirs createallsubdirs
Source: "..\updater\*"; DestDir: "{app}\updater"; Flags: recursesubdirs createallsubdirs
Source: "..\config\settings.yaml.example"; DestDir: "{commonappdata}\GodTierBot\config"; DestName: "settings.yaml"; Flags: onlyifdoesntexist
Source: "..\copier_config.example.json"; DestDir: "{commonappdata}\GodTierBot\config"; DestName: "copier_config.json"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\GodTierBot (Run Execution)"; Filename: "{app}\app\GodTierBot.exe"; Parameters: "run-execution"; WorkingDir: "{app}\app"
Name: "{group}\GodTierBot (Run Copier)"; Filename: "{app}\app\GodTierBot.exe"; Parameters: "run-copier"; WorkingDir: "{app}\app"
Name: "{group}\GodTierBot (Export Support Bundle)"; Filename: "{app}\app\GodTierBot.exe"; Parameters: "export-support-bundle"; WorkingDir: "{app}\app"
Name: "{group}\Uninstall GodTierBot"; Filename: "{uninstallexe}"
