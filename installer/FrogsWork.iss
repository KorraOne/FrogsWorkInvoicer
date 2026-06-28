; FrogsWork Windows installer (Inno Setup 6)
; Build: scripts/build_installer.ps1 -Version "1.1.0"

#ifndef AppVersion
#define AppVersion "1.1.0"
#endif

#ifndef AppSource
#define AppSource "..\client_app\dist\FrogsWork"
#endif

#define AppName "FrogsWork"
#define AppPublisher "KorraOne"
#define AppURL "https://frogswork.com"
#define AppExeName "FrogsWork.exe"

[Setup]
AppId={{8F4E2A91-6C3D-4B8E-9F1A-2D7E5C4B9A03}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL=https://korraone.com/support
AppUpdatesURL={#AppURL}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
PrivilegesRequired=lowest
OutputDir=..\client_app\dist
OutputBaseFilename=FrogsWork-{#AppVersion}-setup
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "exportpdfs"; Description: "Save invoice PDFs to Downloads before removing local data (on uninstall)"; GroupDescription: "Uninstall:"; Flags: checkedonce

[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\{#AppExeName}"; Parameters: "--export-uninstall-data"; Flags: waituntilidle runhidden; Tasks: exportpdfs

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\FrogsWork"

[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%nYour invoices and settings are stored separately in AppData and can be exported to Downloads when you uninstall.
