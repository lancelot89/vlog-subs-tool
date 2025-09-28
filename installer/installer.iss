#define MyAppVersion GetEnv("APP_VERSION")
#if "{#MyAppVersion}" == ""
  #define MyAppVersion "1.0.0"
#endif

[Setup]
AppName=VLog Subs Tool
AppVersion={#MyAppVersion}
AppId={{2F4371CB-21F6-4F09-8F17-0B26C4F05A7A}}
DefaultDirName={autopf}\VlogSubsTool
DefaultGroupName=VLog Subs Tool
DisableDirPage=no
DisableProgramGroupPage=yes
OutputBaseFilename=VlogSubsToolSetup
OutputDir=output
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
VersionInfoVersion={#MyAppVersion}
SetupLogging=yes
WizardStyle=modern

[Files]
Source: "..\dist\AppRoot\*"; DestDir: "{app}"; Flags: recursesubdirs replacesameversion

[Icons]
Name: "{group}\VLog Subs Tool"; Filename: "{app}\run.bat"; WorkingDir: "{app}"; Comment: "VLog字幕ツールを起動"
Name: "{commondesktop}\VLog Subs Tool"; Filename: "{app}\run.bat"; WorkingDir: "{app}"; Tasks: desktopicon; Comment: "VLog字幕ツールを起動"

[Tasks]
Name: "desktopicon"; Description: "デスクトップにショートカットを作成"; GroupDescription: "追加オプション:"; Flags: unchecked

[Run]
Filename: "{app}\run.bat"; Description: "VLog字幕ツールを起動"; Flags: nowait postinstall skipifsilent

[InstallDelete]
Type: filesandordirs; Name: "{app}\env\Lib\site-packages\*.pyc"

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C rmdir /S /Q ""%LOCALAPPDATA%\VlogSubsTool\logs"""; Flags: runhidden
