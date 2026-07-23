# Chạy trên CHÍNH máy đang/sẽ chạy chế độ "Máy chủ" của app Giám sát dịch bệnh.
# Tự động hoá đúng phần tải xuống được — phần tạo Tunnel + lấy lệnh cài đặt (token) BẮT BUỘC
# phải làm thủ công trên one.dash.cloudflare.com vì cần đăng nhập tài khoản Cloudflare của bạn,
# không có cách nào tự động hoá được bước đó. Xem đầy đủ: docs/huong-dan/5-mo-ra-internet.pdf.
#
# Cách chạy: mở PowerShell (không cần quyền Administrator cho bước này), tại thư mục bất kỳ:
#   .\install-cloudflared.ps1

$ErrorActionPreference = "Stop"
$installDir = "C:\cloudflared"
$exePath = Join-Path $installDir "cloudflared.exe"
$downloadUrl = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"

Write-Host "Kiểm tra cổng 8765 hiện có đang bị chương trình khác dùng không..." -ForegroundColor Cyan
$portInUse = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue
if ($portInUse) {
    $pid8765 = $portInUse[0].OwningProcess
    $procName = (Get-Process -Id $pid8765 -ErrorAction SilentlyContinue).ProcessName
    Write-Host "CẢNH BÁO: Cổng 8765 đang bị chiếm bởi tiến trình '$procName' (PID $pid8765)." -ForegroundColor Yellow
    Write-Host "Nếu đó không phải app Giám sát dịch bệnh đang chạy chế độ Máy chủ, cloudflared" -ForegroundColor Yellow
    Write-Host "sẽ chuyển tiếp vào NHẦM chương trình. Kiểm tra lại trước khi tiếp tục." -ForegroundColor Yellow
    Write-Host ""
}

if (-not (Test-Path $installDir)) {
    Write-Host "Tạo thư mục $installDir..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
}

if (Test-Path $exePath) {
    Write-Host "Đã có sẵn $exePath — tải bản mới nhất đè lên." -ForegroundColor Cyan
}

Write-Host "Đang tải cloudflared mới nhất..." -ForegroundColor Cyan
Invoke-WebRequest -Uri $downloadUrl -OutFile $exePath -UseBasicParsing

$version = & $exePath --version
Write-Host ""
Write-Host "Xong. Đã cài: $version" -ForegroundColor Green
Write-Host "Vị trí: $exePath" -ForegroundColor Green
Write-Host ""
Write-Host "Bước tiếp theo (làm thủ công, không tự động hoá được):" -ForegroundColor Cyan
Write-Host "1. Vào one.dash.cloudflare.com -> Networks -> Tunnels -> Create a tunnel -> Cloudflared"
Write-Host "2. Copy lệnh dạng: cloudflared.exe service install <token>"
Write-Host "3. Mở PowerShell VỚI QUYỀN ADMINISTRATOR tại $installDir, dán lệnh đó vào chạy"
Write-Host "4. Quay lại trang Cloudflare, thêm Public Hostname: cdc-hp.io.vn -> localhost:8765"
Write-Host ""
Write-Host "Chi tiết đầy đủ: docs/huong-dan/5-mo-ra-internet.pdf (Mục 5)." -ForegroundColor Cyan
