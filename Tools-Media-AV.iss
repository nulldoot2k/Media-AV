#define MyAppName "Tools Media AV"
#define MyAppVersion "1.0.0"
#define MyAppExeName "media-msi.exe"

[Setup]
AppId={{B5E9E8B6-6D60-4D83-9D56-0E1D7F2A3A91}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\Tools Media AV
DefaultGroupName={#MyAppName}
OutputDir=release
OutputBaseFilename=Tools-Media-AV-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest

[Files]
Source: "dist\media-msi.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Chay {#MyAppName}"; Flags: nowait postinstall skipifsilent
