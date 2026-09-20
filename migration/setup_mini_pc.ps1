<#
    Jalankan skrip ini DI MINI PC, dari folder project yang sudah
    disalin ke sana (hasil export_bundle.ps1), SEBAGAI ADMINISTRATOR
    (klik kanan PowerShell -> Run as Administrator) - dibutuhkan buat
    bikin Firewall rule & Scheduled Task.

    Yang dilakukan:
    1. Buat virtual environment baru + install dependency dari requirements.txt
       (venv lama sengaja tidak ikut disalin - venv itu spesifik per komputer).
    2. Tampilkan IP LAN mini PC ini - dipakai buat update BASE_URL di .env,
       generate ulang QR code meja, dan update config Android app.
    3. Buat Windows Firewall rule buat port 8000 (biar HP/tablet lain di
       WiFi yang sama bisa akses).
    4. Daftarkan 2 Scheduled Task:
         - "CafePOS AutoStart"   -> jalankan serve_production.py otomatis
           tiap kali mini PC nyala/ada yang login, auto-restart kalau
           proses itu crash.
         - "CafePOS DailyBackup" -> jalankan backup_now.py tiap hari jam
           03:00 (bisa diubah lewat parameter -BackupTime).

    Cara pakai (dari folder project hasil salinan, di mini PC):
        cd "D:\CafePOS"   # sesuaikan lokasi hasil salin
        powershell -ExecutionPolicy Bypass -File migration\setup_mini_pc.ps1
#>

param(
    [string]$BackupTime = "03:00"
)

$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Skrip ini harus dijalankan sebagai Administrator (buat Firewall rule & Scheduled Task)." -ForegroundColor Red
    Write-Host "Klik kanan PowerShell -> Run as Administrator, lalu jalankan lagi." -ForegroundColor Red
    exit 1
}

$ProjectRoot = (Get-Item "$PSScriptRoot\..").FullName
Write-Host "=== Cafe POS - Setup di mini PC ===" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"
Write-Host ""

# 1. Venv + dependency
Write-Host "Membuat virtual environment..." -ForegroundColor Cyan
$pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonExe) {
    Write-Host "Python tidak ditemukan di PATH. Install Python 3.11+ dulu, lalu jalankan skrip ini lagi." -ForegroundColor Red
    exit 1
}

Push-Location $ProjectRoot
& $pythonExe -m venv venv
& "$ProjectRoot\venv\Scripts\python.exe" -m pip install --upgrade pip | Out-Null
& "$ProjectRoot\venv\Scripts\pip.exe" install -r requirements.txt
Pop-Location

# 2. Tampilkan IP LAN
Write-Host ""
Write-Host "=== IP LAN mini PC ini ===" -ForegroundColor Cyan
$ips = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" }
$ips | Select-Object InterfaceAlias, IPAddress | Format-Table -AutoSize
Write-Host "Pakai salah satu IP di atas (biasanya yang Ethernet/WiFi utama) untuk:" -ForegroundColor Yellow
Write-Host "  - BASE_URL di .env, contoh: BASE_URL=http://<IP-mini-pc>:8000"
Write-Host "  - Generate ulang QR code tiap meja (halaman Denah Meja)"
Write-Host "  - server_url di android-app/app/src/main/res/values/strings.xml"
Write-Host "  - domain di android-app/app/src/main/res/xml/network_security_config.xml"

if (-not (Test-Path "$ProjectRoot\.env")) {
    Write-Host ""
    Write-Host "PERINGATAN: .env tidak ditemukan di project ini." -ForegroundColor Red
    Write-Host "Cek lagi apakah export_bundle.ps1 sudah menyalin file .env (file tersembunyi/dotfile)."
}

# 3. Firewall rule
Write-Host ""
Write-Host "Membuat Firewall rule untuk port 8000..." -ForegroundColor Cyan
Remove-NetFirewallRule -DisplayName "CafePOS 8000" -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "CafePOS 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow | Out-Null
Write-Host "Firewall rule 'CafePOS 8000' dibuat."

# 4a. Scheduled Task - auto start
Write-Host ""
Write-Host "Mendaftarkan Scheduled Task 'CafePOS AutoStart'..." -ForegroundColor Cyan

$autoStartAction = New-ScheduledTaskAction -Execute "$ProjectRoot\venv\Scripts\python.exe" -Argument "serve_production.py" -WorkingDirectory $ProjectRoot
$autoStartTriggers = @(
    (New-ScheduledTaskTrigger -AtStartup),
    (New-ScheduledTaskTrigger -AtLogOn)
)
$autoStartSettings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 0) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

Unregister-ScheduledTask -TaskName "CafePOS AutoStart" -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName "CafePOS AutoStart" `
    -Action $autoStartAction `
    -Trigger $autoStartTriggers `
    -Settings $autoStartSettings `
    -Principal (New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest) `
    | Out-Null
Write-Host "Task 'CafePOS AutoStart' terdaftar (jalan saat startup/logon, auto-restart kalau crash, sampai 5x percobaan)."

# 4b. Scheduled Task - daily backup
Write-Host ""
Write-Host "Mendaftarkan Scheduled Task 'CafePOS DailyBackup' (jam $BackupTime)..." -ForegroundColor Cyan

$backupAction = New-ScheduledTaskAction -Execute "$ProjectRoot\venv\Scripts\python.exe" -Argument "backup_now.py" -WorkingDirectory $ProjectRoot
$backupTrigger = New-ScheduledTaskTrigger -Daily -At $BackupTime

Unregister-ScheduledTask -TaskName "CafePOS DailyBackup" -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName "CafePOS DailyBackup" `
    -Action $backupAction `
    -Trigger $backupTrigger `
    -Principal (New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest) `
    | Out-Null
Write-Host "Task 'CafePOS DailyBackup' terdaftar."

Write-Host ""
Write-Host "=== Setup selesai ===" -ForegroundColor Green
Write-Host "Langkah yang masih HARUS dilakukan manual:" -ForegroundColor Yellow
Write-Host "  1. Edit .env -> BASE_URL sesuai IP mini PC di atas."
Write-Host "  2. Generate ulang QR code tiap meja (halaman Denah Meja) supaya mengarah ke IP baru."
Write-Host "  3. Kalau pakai Android app: update strings.xml + network_security_config.xml, build ulang APK."
Write-Host "  4. Tes: nyalakan task 'CafePOS AutoStart' manual sekali lewat Task Scheduler buat pastikan aplikasi kebuka,"
Write-Host "     lalu coba restart mini PC beneran buat pastikan auto-start-nya jalan."
