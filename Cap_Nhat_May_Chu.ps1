# Cập nhật máy chủ trực tiếp từ máy — KHÔNG qua nút "Cập nhật ứng dụng" trên trình duyệt.
#
# Vì sao có script này: nút cập nhật qua trình duyệt chạy bằng cách tự bật 1 tiến trình PowerShell
# ẩn, tách rời khỏi dịch vụ Windows đang chạy (cần thiết vì bộ cài phải dừng được chính dịch vụ
# đang phục vụ request đó) — nhưng đôi khi tiến trình ẩn đó không chạy được (gặp thật: không rõ
# nguyên nhân, có thể do phần mềm diệt virus can thiệp), làm giao diện kẹt mãi ở "đang cài đặt" dù
# chưa có gì thật sự chạy. Script này KHÔNG qua bước "tách tiến trình ẩn" đó — tải, kiểm tra và cài
# đặt ngay trong chính cửa sổ đang mở, để nếu có lỗi thì THẤY NGAY trên màn hình thay vì kẹt âm thầm.
#
# Chạy bằng cách bấm đúp Cap_Nhat_May_Chu.bat (script này tự được gọi từ đó) — với quyền
# Administrator, vì bộ cài cần quyền đó để đăng ký lại dịch vụ Windows.

$ErrorActionPreference = 'Stop'
$Repo = 'cdc-hp/bcbtn'
$ApiUrl = "https://api.github.com/repos/$Repo/releases/latest"
$UserAgent = 'CDC-GiamSatDichBenh-ManualUpdater/1.0'
$HealthUrl = 'http://127.0.0.1:8765/health'

function Write-Section([string]$Text) {
    Write-Host ""
    Write-Host "=== $Text ===" -ForegroundColor Cyan
}

try {
    Write-Section "Kiem tra ban phat hanh moi nhat"
    $release = Invoke-RestMethod -Uri $ApiUrl -Headers @{ 'User-Agent' = $UserAgent; 'Accept' = 'application/vnd.github+json' } -TimeoutSec 20
    $version = $release.tag_name.TrimStart('v', 'V')
    if (-not $version) { throw "Khong doc duoc so phien ban tu GitHub." }
    $assetName = "CDC-GiamSatDichBenh-Server-Setup-v$version.exe"
    Write-Host "Phien ban moi nhat: $version ($assetName)"

    $asset = $release.assets | Where-Object { $_.name -eq $assetName } | Select-Object -First 1
    if (-not $asset) {
        throw "Khong tim thay file $assetName trong ban phat hanh moi nhat tren GitHub. " +
              "Kiem tra lai tai https://github.com/$Repo/releases"
    }
    $sumsAsset = $release.assets | Where-Object { $_.name -eq 'SHA256SUMS.txt' } | Select-Object -First 1

    Write-Section "Tai bo cai"
    $destDir = Join-Path $env:TEMP 'cdc_giam_sat_update'
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    $installerPath = Join-Path $destDir $assetName
    Write-Host "Dang tai ve $installerPath ..."
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $installerPath -Headers @{ 'User-Agent' = $UserAgent } -TimeoutSec 300
    Write-Host ("Da tai xong ({0:N1} MB)." -f ((Get-Item $installerPath).Length / 1MB))

    Write-Section "Kiem tra ma SHA-256"
    if ($sumsAsset) {
        # Invoke-WebRequest .Content co the tra ve byte[] (khong phai string) tuy Content-Type may
        # chu tra ve - gap that: SHA256SUMS.txt cua GitHub Releases khien .Content thanh byte[],
        # -split "`r?`n" tren do khong loi nhung ra tung phan tu la 1 byte rieng le, so khop luon
        # thanh cong that bai am tham (khong throw, chi khong tim thay dong nao). Tai ra file roi
        # doc lai bang Get-Content de chac chan luon la text, khong phu thuoc Content-Type.
        $sumsPath = Join-Path $destDir 'SHA256SUMS.txt'
        Invoke-WebRequest -Uri $sumsAsset.browser_download_url -OutFile $sumsPath -Headers @{ 'User-Agent' = $UserAgent } -TimeoutSec 30
        $sumsLines = Get-Content -LiteralPath $sumsPath -Encoding UTF8
        $expectedLine = $sumsLines | Where-Object { $_ -match [regex]::Escape($assetName) }
        if ($expectedLine) {
            $expectedHash = ($expectedLine -split '\s+')[0].Trim().ToLower()
            $actualHash = (Get-FileHash -Path $installerPath -Algorithm SHA256).Hash.ToLower()
            if ($actualHash -ne $expectedHash) {
                Remove-Item -LiteralPath $installerPath -Force -ErrorAction SilentlyContinue
                throw "Ma SHA-256 KHONG KHOP (mong doi $expectedHash, thuc te $actualHash) - " +
                      "file tai ve co the bi loi hoac bi thay doi giua duong. DA XOA file tai ve, KHONG cai dat. Chay lai script."
            }
            Write-Host "Ma SHA-256 hop le: $actualHash"
        } else {
            Write-Warning "Khong tim thay dong SHA-256 cua $assetName trong SHA256SUMS.txt - bo qua kiem tra."
        }
    } else {
        Write-Warning "Ban phat hanh nay khong co SHA256SUMS.txt - bo qua kiem tra ma."
    }

    Write-Section "Cai dat phien ban $version"
    Write-Host "Dich vu Windows se tam ngat trong vai giay de cai dat, roi tu khoi dong lai..."
    $installArgs = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-')
    $process = Start-Process -FilePath $installerPath -ArgumentList $installArgs -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "Bo cai ket thuc voi ma loi $($process.ExitCode). Xem File Explorer > $destDir de kiem tra lai file cai dat."
    }

    Write-Section "Xac nhan sau khi cai"
    $ok = $false
    for ($i = 0; $i -lt 10; $i++) {
        Start-Sleep -Seconds 3
        try {
            $health = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 5
            if ($health.status -eq 'ok') {
                Write-Host "Dich vu dang chay - phien ban bao cao: $($health.version)" -ForegroundColor Green
                $ok = $true
                break
            }
        } catch {
            # dich vu co the con dang khoi dong lai, thu lai vong sau
        }
    }
    if (-not $ok) {
        Write-Warning "Da cai xong nhung chua goi duoc $HealthUrl de xac nhan. Kiem tra tay: Get-Service CDCGiamSatDichBenh"
    }

    Write-Host ""
    Write-Host "HOAN TAT. Da cap nhat len phien ban $version." -ForegroundColor Green
    exit 0
} catch {
    Write-Host ""
    Write-Host "CAP NHAT THAT BAI: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
