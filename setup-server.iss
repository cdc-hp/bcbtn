; Bản cài đặt RIÊNG cho chế độ Máy chủ — cài duy nhất 1 lần trên máy đóng vai trò máy chủ
; chính (xem README.md mục "Cài đặt" và CLAUDE.md). Không hỏi chọn mô hình
; như setup.iss (bản cài tổng hợp 3 chế độ) — luôn ghi thẳng mode="server" vào deployment.json.
; Dùng chung thư mục build dist\GiamSatDichBenh (ứng dụng giống hệt bản setup.iss, chỉ khác cấu
; hình mặc định do installer ghi ra).
#ifndef MyAppVersion
  #define MyAppVersion "0.6.0"
#endif

#define MyAppName "Giám sát dịch bệnh — Máy chủ"
#define MyAppExeName "GiamSatDichBenh.exe"
#define MyAppPublisher "CDC Hải Phòng"

[Setup]
AppId={{BE79DFED-4D5C-491E-821A-4519F846362B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\GiamSatDichBenh-Server
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=setup_output
OutputBaseFilename=GiamSatDichBenh-Server-Setup-v{#MyAppVersion}
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
  ServerPage: TInputQueryWizardPage;

function EscapeJson(Value: String): String;
begin
  Result := Value;
  StringChangeEx(Result, '\', '\\', True);
  StringChangeEx(Result, '"', '\"', True);
end;

procedure InitializeWizard;
begin
  ServerPage := CreateInputQueryPage(
    wpSelectDir,
    'Cấu hình máy chủ',
    'Cổng và mật khẩu kết nối LAN',
    'Máy này sẽ lưu CSDL chính và chia sẻ cho các máy trạm quản trị qua mạng LAN. ' +
    'Mật khẩu để trống nghĩa là không yêu cầu mật khẩu dùng chung (vẫn có thể thêm tài khoản ' +
    'riêng từng quản trị viên sau khi cài — xem tab Hàng đợi trong ứng dụng). ' +
    'Khi Windows hỏi tường lửa, chỉ cho phép mạng Riêng tư.'
  );
  ServerPage.Add('Tên máy chủ hiển thị:', False);
  ServerPage.Values[0] := GetComputerNameString;
  ServerPage.Add('Cổng LAN:', False);
  ServerPage.Values[1] := '8765';
  ServerPage.Add('Mật khẩu dùng chung (không bắt buộc):', True);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  PortValue: Integer;
begin
  Result := True;
  if CurPageID = ServerPage.ID then
  begin
    PortValue := StrToIntDef(ServerPage.Values[1], 0);
    if (PortValue < 1) or (PortValue > 65535) then
    begin
      MsgBox('Cổng LAN phải là số từ 1 đến 65535.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure WriteDeploymentConfig;
var
  ConfigDir, ConfigPath, Port, ServerName, Password, Json: String;
begin
  ConfigDir := ExpandConstant('{localappdata}\CDC_HaiPhong\GiamSatDichBenh');
  ConfigPath := ConfigDir + '\deployment.json';
  ForceDirectories(ConfigDir);

  ServerName := ServerPage.Values[0];
  Port := ServerPage.Values[1];
  Password := ServerPage.Values[2];

  Json := '{' + #13#10 +
    '  "mode": "server",' + #13#10 +
    '  "server_host": "0.0.0.0",' + #13#10 +
    '  "server_port": ' + Port + ',' + #13#10 +
    '  "server_url": "http://127.0.0.1:' + Port + '",' + #13#10 +
    '  "password": "' + EscapeJson(Password) + '",' + #13#10 +
    '  "auto_start_server": true,' + #13#10 +
    '  "server_name": "' + EscapeJson(ServerName) + '",' + #13#10 +
    '  "discovery_enabled": true,' + #13#10 +
    '  "auto_reconnect": true,' + #13#10 +
    '  "reconnect_attempts": 3,' + #13#10 +
    '  "reconnect_delay_seconds": 1.0' + #13#10 +
    '}';
  SaveStringToFile(ConfigPath, Json, False);
end;

procedure ConfigureServerFirewall;
var
  ResultCode: Integer;
  Params, Port: String;
begin
  Port := ServerPage.Values[1];
  Params := '/C netsh advfirewall firewall delete rule name="GSBTN Server TCP ' + Port + '" >nul 2>&1' +
    ' & netsh advfirewall firewall add rule name="GSBTN Server TCP ' + Port + '" dir=in action=allow protocol=TCP localport=' + Port + ' profile=private' +
    ' & netsh advfirewall firewall delete rule name="GSBTN Discovery UDP 8766" >nul 2>&1' +
    ' & netsh advfirewall firewall add rule name="GSBTN Discovery UDP 8766" dir=in action=allow protocol=UDP localport=8766 profile=private';
  ShellExec('runas', ExpandConstant('{cmd}'), Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigPath: String;
begin
  if CurStep = ssPostInstall then
  begin
    // Cài lại/cập nhật lên bản mới không được ghi đè deployment.json đã có — sẽ xóa mất mật
    // khẩu/cổng máy chủ đang dùng. Chỉ hỏi và ghi cấu hình khi đây thực sự là lần cài đầu.
    ConfigPath := ExpandConstant('{localappdata}\CDC_HaiPhong\GiamSatDichBenh\deployment.json');
    if not FileExists(ConfigPath) then
    begin
      WriteDeploymentConfig;
      ConfigureServerFirewall;
    end;
  end;
end;
