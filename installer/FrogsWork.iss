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
#define AppPublisherURL "https://korraone.com"
#define AppTagline "Sales invoicing for Australian sole traders"
#define AppExeName "FrogsWork.exe"
#define AppIcon "..\client_app\assets\app.ico"

[Setup]
AppId={{8F4E2A91-6C3D-4B8E-9F1A-2D7E5C4B9A03}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppPublisherURL}
AppSupportURL=https://korraone.com/support
AppUpdatesURL={#AppURL}
AppComments={#AppTagline}
VersionInfoVersion={#AppVersion}.0
VersionInfoProductVersion={#AppVersion}.0
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} installer
VersionInfoProductName={#AppName}
VersionInfoProductTextVersion={#AppVersion}
VersionInfoCopyright=Copyright (C) 2026 {#AppPublisher}
SetupIconFile={#AppIcon}
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

[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\{#AppExeName}"; Parameters: "--export-uninstall-data"; Flags: waituntilidle runhidden

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\FrogsWork"

[Code]
var
  DeveloperLink: TNewStaticText;

procedure DeveloperLinkClick(Sender: TObject);
var
  ResultCode: Integer;
begin
  ShellExec('open', '{#AppPublisherURL}', '', '', SW_SHOW, ewNoWait, ResultCode);
end;

procedure InitializeWizard();
begin
  DeveloperLink := TNewStaticText.Create(WizardForm);
  DeveloperLink.Parent := WizardForm.FinishedPage;
  DeveloperLink.Caption := 'Developed by {#AppPublisher} ({#AppPublisherURL})';
  DeveloperLink.Left := WizardForm.FinishedLabel.Left;
  DeveloperLink.Top := WizardForm.FinishedLabel.Top + WizardForm.FinishedLabel.Height + 12;
  DeveloperLink.Width := WizardForm.FinishedLabel.Width;
  DeveloperLink.Height := ScaleY(32);
  DeveloperLink.AutoSize := False;
  DeveloperLink.WordWrap := True;
  DeveloperLink.Font.Style := [fsUnderline];
  DeveloperLink.Font.Color := clNavy;
  DeveloperLink.Cursor := crHand;
  DeveloperLink.OnClick := @DeveloperLinkClick;
end;

procedure StopFrogsWorkProcesses();
var
  ResultCode: Integer;
begin
  Exec('taskkill.exe', '/F /T /IM {#AppExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function TryRemoveInstallDir(const AppDir: String): Boolean;
var
  Attempt: Integer;
begin
  Result := not DirExists(AppDir);
  if Result then
    Exit;

  for Attempt := 1 to 3 do
  begin
    DelTree(AppDir, True, True, True);
    if not DirExists(AppDir) then
    begin
      Result := True;
      Exit;
    end;
    Sleep(1000);
  end;

  Result := not DirExists(AppDir);
end;

function InitializeUninstall(): Boolean;
begin
  StopFrogsWorkProcesses();
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  AppDir: String;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;

  StopFrogsWorkProcesses();
  AppDir := ExpandConstant('{app}');
  if TryRemoveInstallDir(AppDir) then
    Exit;

  MsgBox(
    'FrogsWork was removed from Windows, but some program files could not be deleted.' + #13#10 + #13#10 +
    'This usually happens when File Explorer (or another program) still has the install folder open.' + #13#10 + #13#10 +
    'Close that window, then delete this folder:' + #13#10 + AppDir,
    mbInformation,
    MB_OK);
end;

[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%n{#AppTagline}%n%nFrogsWork is developed by {#AppPublisher} ({#AppPublisherURL}).%n%nYour invoices and settings are stored separately in AppData and can be exported to Downloads when you uninstall.
FinishedLabel=FrogsWork [version] is ready to use.%n%nProduct site: {#AppURL}%nSupport: https://korraone.com/support
