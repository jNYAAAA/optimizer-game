; Inno Setup script для Optimizer Game
; Сборка: ISCC.exe installer.iss

#define MyAppName "Optimizer Game"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "jNYAAAA"
#define MyAppURL "https://github.com/jNYAAAA/optimizer-game"
#define MyAppExeName "OptimizerGame.exe"

[Setup]
AppId={{8F3C2A1E-4B7D-4E9A-9C21-6D5A0F2B7C34}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist_installer
OutputBaseFilename=OptimizerGame-Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
WizardImageFile=assets\installer\wizard.bmp
WizardSmallImageFile=assets\installer\wizard_small.bmp
InfoBeforeFile=assets\installer\before.txt
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\installer\before.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Messages]
russian.WelcomeLabel2=Установит [name/ver] на ваш компьютер.%n%nOptimizer Game показывает характеристики ПК и температуры, проверяет и устанавливает драйверы, оптимизирует Windows и применяет игровые настройки.%n%nДля продолжения нажмите «Далее».
