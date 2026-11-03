#define MyAppName "NEXUS-DASH"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "ItsWanheda"
#define MyAppExeName "NEXUS-DASH.exe"

[Setup]
AppId={{CB5A6D68-79F4-4B1C-A3AA-2BCE71A3E1D1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\NEXUS-DASH
DefaultGroupName=NEXUS-DASH
OutputDir=..\dist
OutputBaseFilename=NEXUS-DASH-Setup-{#MyAppVersion}-x64
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "..\dist\NEXUS-DASH\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\NEXUS-DASH"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\NEXUS-DASH"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch NEXUS-DASH"; Flags: nowait postinstall skipifsilent
