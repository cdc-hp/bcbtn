; Bản cài đặt RIÊNG cho Máy trạm quản trị — kết nối tới máy chủ đã cài sẵn (setup-server.iss)
; qua địa chỉ IP LAN. Không hỏi chọn mô hình như setup.iss — luôn ghi thẳng mode="workstation"
; vào deployment.json. Tài khoản đăng nhập cá nhân của từng quản trị viên (khác mật khẩu dùng
; chung) được nhập SAU khi cài, ngay trong ứng dụng (Kết nối máy chủ LAN → Đăng nhập quản trị
; viên) — xem README phần "Máy trạm quản trị". Dùng chung thư mục build dist\GiamSatDichBenh.
#ifndef MyAppVersion
  #define MyAppVersion "0.6.0"
#endif

#define MyAppName "Giám sát dịch bệnh — Máy trạm quản trị"
#define MyAppExeName "GiamSatDichBenh.exe"
#define MyAppPublisher "CDC Hải Phòng"

[Setup]
AppId={{6105B3CF-3232-4D37-8A76-D58329D2D10F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\GiamSatDichBenh-Admin
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=setup_output
OutputBaseFilename=GiamSatDichBenh-Admin-Setup-v{#MyAppVersion}
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
Type: filesandordirs; Name: "{app}\update_cache"

[Code]
var
  WorkstationPage: TInputQueryWizardPage;

function EscapeJson(Value: String): String;
begin
  Result := Value;
  StringChangeEx(Result, '\', '\\', True);
  StringChangeEx(Result, '"', '\"', True);
end;

procedure InitializeWizard;
begin
  WorkstationPage := CreateInputQueryPage(
    wpSelectDir,
    'Cấu hình máy trạm quản trị',
    'Nhập địa chỉ máy chủ trong mạng LAN',
    'Ví dụ: http://192.168.1.10:8765 — lấy từ tab Server trên máy chủ. ' +
    'Mật khẩu ở đây là mật khẩu dùng chung của máy chủ (nếu có); sau khi cài, mở ứng dụng và ' +
    'vào "Kết nối máy chủ LAN" để đăng nhập TÀI KHOẢN RIÊNG của bạn — mỗi quản trị viên một ' +
    'tài khoản, tách biệt với mật khẩu dùng chung này.'
  );
  WorkstationPage.Add('Địa chỉ máy chủ:', False);
  WorkstationPage.Values[0] := 'http://192.168.1.10:8765';
  WorkstationPage.Add('Mật khẩu dùng chung (để trống nếu không dùng):', True);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = WorkstationPage.ID then
  begin
    if (Pos('http://', Lowercase(WorkstationPage.Values[0])) <> 1) and
       (Pos('https://', Lowercase(WorkstationPage.Values[0])) <> 1) then
    begin
      MsgBox('Địa chỉ máy chủ phải bắt đầu bằng http:// hoặc https://', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure WriteDeploymentConfig;
var
  ConfigDir, ConfigPath, ServerUrl, Password, Json: String;
begin
  ConfigDir := ExpandConstant('{localappdata}\CDC_HaiPhong\GiamSatDichBenh');
  ConfigPath := ConfigDir + '\deployment.json';
  ForceDirectories(ConfigDir);

  ServerUrl := WorkstationPage.Values[0];
  Password := WorkstationPage.Values[1];

  Json := '{' + #13#10 +
    '  "mode": "workstation",' + #13#10 +
    '  "server_host": "0.0.0.0",' + #13#10 +
    '  "server_port": 8765,' + #13#10 +
    '  "server_url": "' + EscapeJson(ServerUrl) + '",' + #13#10 +
    '  "password": "' + EscapeJson(Password) + '",' + #13#10 +
    '  "auto_start_server": true,' + #13#10 +
    '  "server_name": "",' + #13#10 +
    '  "discovery_enabled": true,' + #13#10 +
    '  "auto_reconnect": true,' + #13#10 +
    '  "reconnect_attempts": 3,' + #13#10 +
    '  "reconnect_delay_seconds": 1.0' + #13#10 +
    '}';
  SaveStringToFile(ConfigPath, Json, False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigPath: String;
begin
  if CurStep = ssPostInstall then
  begin
    // Cài lại/cập nhật lên bản mới không được ghi đè deployment.json đã có — sẽ xóa mất địa chỉ
    // máy chủ/mật khẩu đang dùng. Chỉ hỏi và ghi cấu hình khi đây thực sự là lần cài đầu.
    ConfigPath := ExpandConstant('{localappdata}\CDC_HaiPhong\GiamSatDichBenh\deployment.json');
    if not FileExists(ConfigPath) then
      WriteDeploymentConfig;
  end;
end;
