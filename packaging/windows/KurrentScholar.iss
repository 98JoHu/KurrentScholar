#define MyAppName "KurrentScholar"
#define MyAppVersion "0.1.1-dev"
#define MyAppPublisher "KurrentScholar contributors"
#define MyAppExeName "KurrentScholar.exe"

[Setup]
AppId={{E13775A4-89A2-44A9-BCA0-FE08052A2353}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\KurrentScholar
DefaultGroupName=KurrentScholar
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..\dist\installer
OutputBaseFilename=KurrentScholar-Setup-Windows-x64
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayIcon={app}\KurrentScholar.exe
LicenseFile=..\..\LICENSE
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\KurrentScholar\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\KurrentScholar"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\KurrentScholar"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,KurrentScholar}"; Flags: nowait postinstall skipifsilent
