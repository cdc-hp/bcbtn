#ifndef MyAppVersion
  #define MyAppVersion "0.3.0"
#endif

#define MyAppName "Giám sát dịch bệnh"
#define MyAppExeName "GiamSatDichBenh.exe"
#define MyAppPublisher "CDC Hải Phòng"

[Setup]
AppId={{4C1A50E6-6F11-4AA2-992C-C66ACCEB21C1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\GiamSatDichBenh
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=setup_output
OutputBaseFilename=GiamSatDichBenh-Setup-v{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\GiamSatDichBenh\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Tạo biểu tượng ngoài màn hình"; GroupDescription: "Biểu tượng bổ sung:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Mở {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Chỉ xóa cache nằm trong thư mục chương trình. Dữ liệu người dùng nằm ngoài {app} và được giữ nguyên.
Type: filesandordirs; Name: "{app}\update_cache"
