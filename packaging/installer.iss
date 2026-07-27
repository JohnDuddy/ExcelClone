; Inno Setup script for Duddy Spreadsheet.
;
; Build with:  iscc /DAppVersion=1.0.0 packaging\installer.iss
; tools/build_release.py passes the version automatically.
;
; Requires Inno Setup 6 (free): https://jrsoftware.org/isdl.php

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#define AppName "Duddy Spreadsheet"
#define AppPublisher "Duddy Software"
#define AppURL "https://duddysoftware.com"
#define AppExeName "DuddySpreadsheet.exe"
#define SourceDir "..\dist\DuddySpreadsheet"

[Setup]
AppId={{8F2A4C91-6D3E-4B7A-9C15-2E8D4F0A7B36}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=..\EULA.md
OutputDir=..\dist
OutputBaseFilename=DuddySpreadsheet-{#AppVersion}-Setup
SetupIconFile=..\assets\duddysheet.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Per-user installs need no administrator rights, which matters in the
; locked-down environments this product targets.
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; \
    GroupDescription: "Additional shortcuts:"
Name: "associate"; Description: "Associate .dsheet files with {#AppName}"; \
    GroupDescription: "File associations:"

[Files]
Source: "{#SourceDir}\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; \
    Tasks: desktopicon

[Registry]
; Native workbook association.
Root: HKA; Subkey: "Software\Classes\.dsheet"; ValueType: string; \
    ValueName: ""; ValueData: "DuddySpreadsheet.Workbook"; \
    Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\DuddySpreadsheet.Workbook"; \
    ValueType: string; ValueName: ""; ValueData: "{#AppName} Workbook"; \
    Flags: uninsdeletekey; Tasks: associate
Root: HKA; Subkey: "Software\Classes\DuddySpreadsheet.Workbook\DefaultIcon"; \
    ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExeName},0"; \
    Tasks: associate
Root: HKA; \
    Subkey: "Software\Classes\DuddySpreadsheet.Workbook\shell\open\command"; \
    ValueType: string; ValueName: ""; \
    ValueData: """{app}\{#AppExeName}"" ""%1"""; Tasks: associate
; Advertise the application so Windows offers it under Open With for .xlsx
; without seizing the association from an installed Office.
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExeName}\shell\open\command"; \
    ValueType: string; ValueName: ""; \
    ValueData: """{app}\{#AppExeName}"" ""%1"""; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.xlsx\OpenWithProgids"; \
    ValueType: string; ValueName: "DuddySpreadsheet.Workbook"; ValueData: ""; \
    Flags: uninsdeletevalue; Tasks: associate

[Run]
Filename: "{app}\{#AppExeName}"; \
    Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove only what the installer created. User workbooks, licence, and
; settings under %LOCALAPPDATA% are deliberately left in place so that
; uninstalling never destroys a customer's work or their activation.
Type: filesandordirs; Name: "{app}\_internal"
