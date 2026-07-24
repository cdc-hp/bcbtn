; Bản cài đặt DUY NHẤT cho Web App tập trung (Giai đoạn 9, xem TASKS.md) — thay hoàn toàn mô
; hình cũ "máy chủ LAN + máy trạm quản trị riêng" (setup-server.iss/setup-admin.iss). Cài như
; dịch vụ Windows (service_windows.py, CDCGiamSatDichBenh) chạy Web App qua Uvicorn; quản trị
; hoàn toàn qua trình duyệt sau khi cài — bộ cài KHÔNG hỏi tài khoản/GAS/đồng bộ/thư mục sao lưu
; như installer cũ (những cái đó cấu hình ở /cdc/setup và /cdc/cau-hinh sau khi cài xong), chỉ
; hỏi đúng 1 câu: cổng lắng nghe.
;
; Cần quyền Administrator (PrivilegesRequired=admin) vì phải đăng ký dịch vụ Windows — khác hẳn
; setup.iss/setup-server.iss/setup-admin.iss (PrivilegesRequired=lowest, cài theo từng người
; dùng). setup.iss/setup-server.iss/setup-admin.iss VẪN GIỮ NGUYÊN cho tới khi Web App được xác
; nhận thay thế đủ chức năng trên máy thật (xem TASKS.md Giai đoạn 11).
#ifndef MyAppVersion
  #define MyAppVersion "0.11.0"
#endif

#define MyAppName "CDC Hải Phòng - Giám sát dịch bệnh (Máy chủ Web)"
#define MyAppExeName "CDCGiamSatDichBenh.exe"
#define MyAppPublisher "CDC Hải Phòng"

[Setup]
AppId={{C61C125E-D1BF-4DB8-92C4-A8FF5133E493}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\CDC-GiamSatDichBenh
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=setup_output
OutputBaseFilename=CDC-GiamSatDichBenh-Server-Setup-v{#MyAppVersion}
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
Source: "dist_cdc_service\CDCGiamSatDichBenh\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Mở trang quản trị"; Filename: "{code:GetAdminUrl}"
Name: "{group}\Thư mục dữ liệu"; Filename: "{code:GetDataDir}"

[UninstallRun]
Filename: "{app}\{#MyAppExeName}"; Parameters: "stop"; Flags: runhidden; RunOnceId: "StopService"
Filename: "{app}\{#MyAppExeName}"; Parameters: "remove"; Flags: runhidden; RunOnceId: "RemoveService"

[Run]
Filename: "{code:GetAdminUrl}"; Description: "Mở trang quản trị (thiết lập tài khoản đầu tiên)"; Flags: postinstall shellexec skipifsilent runasoriginaluser

[Code]
var
  ConfigPage: TInputQueryWizardPage;
  ExistingConfigFound: Boolean;
  ResolvedPort: String;

function DataDir(Param: String): String;
begin
  Result := 'C:\ProgramData\CDC Hai Phong\GiamSatDichBenh';
end;

function GetDataDir(Param: String): String;
begin
  Result := DataDir('');
end;

function ConfigFilePath: String;
begin
  Result := DataDir('') + '\deployment.json';
end;

function ReadExistingPort(Path: String): String;
var
  Contents: AnsiString;
  Text: String;
  StartPos, EndPos: Integer;
begin
  Result := '';
  if not FileExists(Path) then Exit;
  if not LoadStringFromFile(Path, Contents) then Exit;
  Text := String(Contents);
  StartPos := Pos('"server_port":', Text);
  if StartPos = 0 then Exit;
  StartPos := StartPos + Length('"server_port":');
  EndPos := Pos(',', Copy(Text, StartPos, Length(Text) - StartPos + 1));
  if EndPos = 0 then
    EndPos := Pos('}', Copy(Text, StartPos, Length(Text) - StartPos + 1));
  if EndPos = 0 then Exit;
  Result := Trim(Copy(Text, StartPos, EndPos - 1));
end;

procedure InitializeWizard;
var
  ExistingPort: String;
begin
  ExistingConfigFound := FileExists(ConfigFilePath);
  ExistingPort := ReadExistingPort(ConfigFilePath);
  if ExistingPort = '' then ExistingPort := '8765';

  ConfigPage := CreateInputQueryPage(
    wpSelectDir,
    'Cổng máy chủ',
    'Cổng lắng nghe của Web App',
    'Web App chạy như 1 dịch vụ Windows, quản trị hoàn toàn qua trình duyệt (không cần mở ứng ' +
    'dụng riêng). Giữ nguyên cổng mặc định nếu không chắc — chỉ đổi khi cổng này bị phần mềm ' +
    'khác chiếm. Tên miền công khai, khoá API Google Apps Script, máy chủ phụ và thư mục sao ' +
    'lưu thiết lập SAU khi cài đặt, qua trang "Cấu hình" trong trình duyệt sau khi đăng nhập.'
  );
  ConfigPage.Add('Cổng lắng nghe:', False);
  ConfigPage.Values[0] := ExistingPort;
  // Đặt trước ở đây (không phải chờ CurStepChanged) vì [Icons] được engine xử lý TRƯỚC
  // ssPostInstall — nếu để ResolvedPort rỗng tới lúc đó, shortcut "Mở trang quản trị" sẽ tạo ra
  // với URL thiếu cổng (http://127.0.0.1:/cdc/login). NextButtonClick cập nhật lại nếu người
  // dùng đổi giá trị trên trang này.
  ResolvedPort := ExistingPort;

  // #13#10 KHÔNG được đứng đầu dòng — ISPP (preprocessor Inno Setup) quét cả file trước khi
  // Pascal Script biên dịch, thấy dòng bắt đầu bằng "#" là tưởng nhầm 1 chỉ thị preprocessor
  // (lỗi thật gặp phải: "Error ...: Unknown preprocessor directive." ở đúng dòng #13#10 đứng
  // đầu). Phải để token Pascal (không phải "#") đứng đầu mỗi dòng vật lý.
  if ExistingConfigFound then
    ConfigPage.Description := ConfigPage.Description + #13#10#13#10 +
      'Đã phát hiện cấu hình sẵn có trên máy này (đang nâng cấp) — giá trị hiện ' +
      'tại được điền sẵn. Đổi giá trị này ở đây sẽ KHÔNG có tác dụng, bộ cài giữ nguyên cấu ' +
      'hình cũ để không mất thiết lập/khoá bí mật đã có; hãy đổi cổng ở trang Cấu hình sau khi ' +
      'đăng nhập nếu cần.';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  PortValue: Integer;
begin
  Result := True;
  if CurPageID = ConfigPage.ID then
  begin
    PortValue := StrToIntDef(ConfigPage.Values[0], 0);
    if (PortValue < 1) or (PortValue > 65535) then
    begin
      MsgBox('Cổng phải là số từ 1 đến 65535.', mbError, MB_OK);
      Result := False;
    end
    else
      ResolvedPort := ConfigPage.Values[0];
  end;
end;

function GetAdminUrl(Param: String): String;
begin
  Result := 'http://127.0.0.1:' + ResolvedPort + '/cdc/login';
end;

procedure WriteDeploymentConfig;
var
  Json: String;
begin
  ForceDirectories(DataDir(''));
  Json := '{' + #13#10 +
    '  "server_host": "0.0.0.0",' + #13#10 +
    '  "server_port": ' + ConfigPage.Values[0] + #13#10 +
    '}';
  SaveStringToFile(ConfigFilePath, Json, False);
end;

procedure ConfigureFirewall(Port: String);
var
  ResultCode: Integer;
  Params: String;
begin
  Params := '/C netsh advfirewall firewall delete rule name="CDC GiamSatDichBenh TCP ' + Port + '" >nul 2>&1' +
    ' & netsh advfirewall firewall add rule name="CDC GiamSatDichBenh TCP ' + Port +
    '" dir=in action=allow protocol=TCP localport=' + Port + ' profile=private,domain';
  Exec(ExpandConstant('{cmd}'), Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

// Dừng + gỡ dịch vụ cũ TRƯỚC KHI Inno Setup copy file [Files] — nếu dịch vụ cũ vẫn đang chạy,
// file .exe đang bị khoá và bước copy sẽ lỗi. Không kiểm tra ResultCode (không sao nếu chưa
// từng cài dịch vụ — lần cài đầu tiên).
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  ExistingExe: String;
begin
  Result := '';
  ExistingExe := ExpandConstant('{app}\{#MyAppExeName}');
  if FileExists(ExistingExe) then
  begin
    Exec(ExistingExe, 'stop', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec(ExistingExe, 'remove', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  NewExe: String;
begin
  if CurStep = ssPostInstall then
  begin
    // Chỉ ghi cấu hình mới khi máy này CHƯA từng cài — giữ nguyên deployment.json khi nâng cấp
    // (không được ghi đè mất khoá GAS/máy chủ phụ đã cấu hình qua /cdc/cau-hinh).
    if not ExistingConfigFound then
      WriteDeploymentConfig;

    // ResolvedPort đã được chốt ở NextButtonClick (đọc từ cấu hình cũ nếu đang nâng cấp, hoặc
    // giá trị người dùng nhập nếu cài lần đầu) — không đọc lại từ file ở đây, tránh lệch với
    // giá trị đã dùng để tạo shortcut [Icons] (được engine xử lý TRƯỚC bước này).
    ConfigureFirewall(ResolvedPort);

    NewExe := ExpandConstant('{app}\{#MyAppExeName}');
    Exec(NewExe, 'install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec(NewExe, 'start', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;
