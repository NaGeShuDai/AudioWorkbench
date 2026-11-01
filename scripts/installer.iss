#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif
[Setup]
AppId={{F6DE4785-645A-4D64-973C-44A99A62A7B5}
AppName=AudioWorkbench
AppVersion={#AppVersion}
AppPublisher=NaGeShuDai
AppPublisherURL=https://github.com/NaGeShuDai/AudioWorkbench
AppSupportURL=https://github.com/NaGeShuDai/AudioWorkbench/issues
DefaultDirName={localappdata}\Programs\AudioWorkbench
DefaultGroupName=AudioWorkbench
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=AudioWorkbench-{#AppVersion}-Setup-x64
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\AudioWorkbench.exe
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
chinesesimplified.DesktopShortcut=创建桌面快捷方式
chinesesimplified.LaunchApplication=启动 AudioWorkbench
english.DesktopShortcut=Create a desktop shortcut
english.LaunchApplication=Launch AudioWorkbench

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopShortcut}"; Flags: unchecked

[Files]
Source: "..\dist\AudioWorkbench\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\AudioWorkbench"; Filename: "{app}\AudioWorkbench.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\AudioWorkbench"; Filename: "{app}\AudioWorkbench.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\AudioWorkbench.exe"; Description: "{cm:LaunchApplication}"; Flags: nowait postinstall skipifsilent
