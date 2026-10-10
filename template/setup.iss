; Windows setup (Inno Setup), generated from template/setup.iss and installer.conf
; Installs per user without admin rights, with start menu entry, desktop shortcut and uninstaller.
#define AppName "@APP_NAME@"
#define AppVersion "@VERSION@"
#define AppExe "@WINDOWS_EXE@"
#define WindowsFile "@WINDOWS_FILE@"

[Setup]
AppId={{@APP_GUID@}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisherURL=https://github.com/@REPO@
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=output
OutputBaseFilename=@APP_ID@-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
@SETUP_ICON@
UninstallDisplayIcon={app}\{#AppExe}
; Kein Restart Manager. Er schickt laufenden Anwendungen eine Nachricht an ihr
; Fenster und wartet dann auf eine Frist - ein Programm ohne Fenster bekommt sie
; nie, und die Installation steht minutenlang bei "Anwendungen werden geschlossen".
; Stattdessen beendet InitializeSetup die Prozesse unten selbst, das geht sofort.
CloseApplications=no
RestartApplications=no

[Code]
// Vor der Installation die eigenen Prozesse beenden. Der Restart Manager wuerde
// dafuer erst auf eine Antwort warten, die ein Programm ohne Fenster nie gibt.
// Die Notizmappe speichert von selbst, sobald man eine Sekunde nicht tippt.
function InitializeSetup(): Boolean;
var Rueckgabe: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM "{#AppExe}" /T',
       '', SW_HIDE, ewWaitUntilTerminated, Rueckgabe);
  Result := True;
end;

// Dasselbe beim Entfernen: laeuft das Programm noch, sind seine Dateien gesperrt
// und die Deinstallation bleibt daran haengen.
function InitializeUninstall(): Boolean;
var Rueckgabe: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM "{#AppExe}" /T',
       '', SW_HIDE, ewWaitUntilTerminated, Rueckgabe);
  Result := True;
end;

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Alles aus program\ - bei einem Buendel aus einem Ordner (PyInstaller --onedir)
; sind das viele Dateien, bei einer einzelnen exe eben nur diese eine.
Source: "program\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent shellexec
