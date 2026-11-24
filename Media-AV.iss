#define MyAppName "MediaAV"
#define MyAppVersion "1.0.0"
#define MyAppExeName "mediaAV-msi.exe"

[Setup]
AppId={{B5E9E8B6-6D60-4D83-9D56-0E1D7F2A3A91}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\MediaAV
DefaultGroupName={#MyAppName}
OutputDir=release
OutputBaseFilename=Media-AV-Windows
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
CloseApplications=yes
Uninstallable=yes
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}

[Files]
Source: "dist\mediaAV-msi\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Chay {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
