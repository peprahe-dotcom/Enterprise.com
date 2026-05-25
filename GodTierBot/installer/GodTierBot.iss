[Setup]
AppName=GodTierBot
AppVersion=0.1.0
DefaultDirName={pf}\GodTierBot
DefaultGroupName=GodTierBot
OutputBaseFilename=GodTierBot-Setup
Compression=lzma
SolidCompression=yes
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Files]
Source: "..\dist\GodTierBot\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "..\mql5_bridge\GodTierBridge.mq5"; DestDir: "{app}\mt5_payload"; Flags: ignoreversion
Source: "..\mql5_bridge\README_INSTALL.txt"; DestDir: "{app}\mt5_payload"; Flags: ignoreversion

[Icons]
Name: "{group}\GodTierBot"; Filename: "{app}\GodTierBot.exe"
Name: "{commondesktop}\GodTierBot"; Filename: "{app}\GodTierBot.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; Flags: unchecked
Name: "startup"; Description: "Start GodTierBot when Windows starts"; Flags: checkedonce

[Run]
Filename: "{app}\GodTierBot.exe"; Description: "Launch GodTierBot"; Flags: nowait postinstall skipifsilent

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "GodTierBot"; ValueData: """{app}\GodTierBot.exe"""; Tasks: startup

[Code]
var
  Mt5DataFolder: string;

function SelectDirectoryPageNeeded: Boolean;
begin
  Result := True;
end;

procedure CopyMt5Payload;
var
  ExpertsDir: string;
  Ex5Path: string;
begin
  if Mt5DataFolder = '' then
    exit;

  ExpertsDir := AddBackslash(Mt5DataFolder) + 'MQL5\Experts\';
  ForceDirectories(ExpertsDir);

  Ex5Path := ExpandConstant('{app}\mt5_payload\GodTierBridge.ex5');
  if FileExists(Ex5Path) then
  begin
    FileCopy(Ex5Path, ExpertsDir + 'GodTierBridge.ex5', False);
  end
  else
  begin
    FileCopy(ExpandConstant('{app}\mt5_payload\GodTierBridge.mq5'), ExpertsDir + 'GodTierBridge.mq5', False);
    MsgBox('GodTierBridge.ex5 is not included. GodTierBridge.mq5 was copied instead. Open MetaEditor and compile it once (F7).', mbInformation, MB_OK);
  end;
end;

procedure InitializeWizard;
begin
  Mt5DataFolder := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if MsgBox('Do you want to install the MT5 bridge into your MT5 Data Folder now?', mbConfirmation, MB_YESNO) = IDYES then
    begin
      if BrowseForFolder('Select your MT5 Data Folder (MT5 -> File -> Open Data Folder)', Mt5DataFolder, False) then
        CopyMt5Payload;
    end;
  end;
end;
