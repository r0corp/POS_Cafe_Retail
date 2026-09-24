<#
    Jalankan skrip ini DI MINI PC CABANG BARU, SEBAGAI ADMINISTRATOR
    (klik kanan PowerShell -> Run as Administrator), SETELAH Tailscale
    sudah di-install & login pakai akun yang sama dengan cabang lain.

    Menggabungkan migration\setup_mini_pc.ps1 + ops\install_agent.ps1
    jadi 1 langkah, supaya bikin cabang baru tidak perlu jalankan
    beberapa skrip terpisah lagi:
      1. Venv + install dependency dari requirements.txt.
      2. Firewall rule port 8000 (aplikasi POS) + Scheduled Task
         "CafePOS AutoStart" & "CafePOS DailyBackup".
      3. Generate token acak buat ops\.env (kalau belum ada).
      4. Firewall rule port 8787 (Ops Agent) + Scheduled Task
         "OrulabsPOS Ops Agent".
      5. Cetak ringkasan di akhir: IP Tailscale + token, tinggal
         disalin ke dashboard.html di laptop kontrol.

    Cara pakai (dari folder project hasil clone/salin, di mini PC baru):
        cd C:\OrulabsPOS
        powershell -ExecutionPolicy Bypass -File migration\bootstrap_new_branch.ps1
#>

param(
    [string]$BackupTime = "03:00",
    [int]$AgentPort = 8787
)

$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Skrip ini harus dijalankan sebagai Administrator." -ForegroundColor Red
    Write-Host "Klik kanan PowerShell -> Run as Administrator, lalu jalankan lagi." -ForegroundColor Red
    exit 1
}

$ProjectRoot = (Get-Item "$PSScriptRoot\..").FullName
Write-Host "=== Orulabs POS - Bootstrap Cabang Baru ===" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"
Write-Host ""

# ---------- 1. Venv + dependency ----------
Write-Host "[1/5] Membuat virtual environment..." -ForegroundColor Cyan
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

if (-not (Test-Path "$ProjectRoot\.env")) {
    Write-Host "PERINGATAN: .env belum ada - buat manual sebelum aplikasi POS bisa jalan (lihat DEPLOYMENT.md)." -ForegroundColor Yellow
}

# ---------- 2. Firewall + Scheduled Task aplikasi POS ----------
Write-Host ""
Write-Host "[2/5] Firewall rule port 8000 + Scheduled Task aplikasi POS..." -ForegroundColor Cyan
Remove-NetFirewallRule -DisplayName "CafePOS 8000" -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "CafePOS 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow | Out-Null

$autoStartAction = New-ScheduledTaskAction -Execute "$ProjectRoot\venv\Scripts\python.exe" -Argument "serve_production.py" -WorkingDirectory $ProjectRoot
$autoStartTriggers = @((New-ScheduledTaskTrigger -AtStartup), (New-ScheduledTaskTrigger -AtLogOn))
$autoStartSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 0) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Unregister-ScheduledTask -TaskName "CafePOS AutoStart" -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName "CafePOS AutoStart" -Action $autoStartAction -Trigger $autoStartTriggers -Settings $autoStartSettings -Principal (New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest) | Out-Null

$backupAction = New-ScheduledTaskAction -Execute "$ProjectRoot\venv\Scripts\python.exe" -Argument "backup_now.py" -WorkingDirectory $ProjectRoot
$backupTrigger = New-ScheduledTaskTrigger -Daily -At $BackupTime
Unregister-ScheduledTask -TaskName "CafePOS DailyBackup" -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName "CafePOS DailyBackup" -Action $backupAction -Trigger $backupTrigger -Principal (New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest) | Out-Null
Write-Host "Selesai - task 'CafePOS AutoStart' & 'CafePOS DailyBackup' terdaftar."

# ---------- 3. Token Ops Agent ----------
Write-Host ""
Write-Host "[3/5] Menyiapkan ops\.env (token Ops Agent)..." -ForegroundColor Cyan
$envPath = "$ProjectRoot\ops\.env"
if (-not (Test-Path $envPath)) {
    $token = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 40 | ForEach-Object { [char]$_ })
    $exampleContent = Get-Content "$ProjectRoot\ops\.env.example" -Raw
    $newContent = $exampleContent -replace 'ganti-dengan-token-acak-yang-panjang', $token
    $newContent = $newContent -replace 'PROJECT_ROOT=C:\\OrulabsPOS', "PROJECT_ROOT=$ProjectRoot"
    Set-Content -Path $envPath -Value $newContent
    Write-Host "Token baru digenerate: $token" -ForegroundColor Green
} else {
    Write-Host "ops\.env sudah ada - dipakai apa adanya (token tidak diubah)." -ForegroundColor Yellow
}

# ---------- 4. Firewall + Scheduled Task Ops Agent ----------
Write-Host ""
Write-Host "[4/5] Firewall rule port $AgentPort + Scheduled Task Ops Agent..." -ForegroundColor Cyan
Remove-NetFirewallRule -DisplayName "OrulabsPOS Ops Agent" -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "OrulabsPOS Ops Agent" -Direction Inbound -Protocol TCP -LocalPort $AgentPort -Action Allow | Out-Null

$agentAction = New-ScheduledTaskAction -Execute "$ProjectRoot\venv\Scripts\python.exe" -Argument "ops\agent.py" -WorkingDirectory $ProjectRoot
$agentTriggers = @((New-ScheduledTaskTrigger -AtStartup), (New-ScheduledTaskTrigger -AtLogOn))
$agentSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 0) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Unregister-ScheduledTask -TaskName "OrulabsPOS Ops Agent" -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName "OrulabsPOS Ops Agent" -Action $agentAction -Trigger $agentTriggers -Settings $agentSettings -Principal (New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest) | Out-Null

Start-ScheduledTask -TaskName "OrulabsPOS Ops Agent"
Start-Sleep -Seconds 2

# ---------- 5. Ringkasan ----------
Write-Host ""
Write-Host "[5/5] Verifikasi..." -ForegroundColor Cyan

$tailscaleExe = (Get-Command tailscale -ErrorAction SilentlyContinue).Source
if (-not $tailscaleExe -and (Test-Path "C:\Program Files\Tailscale\tailscale.exe")) {
    $tailscaleExe = "C:\Program Files\Tailscale\tailscale.exe"
}
$tsIp = if ($tailscaleExe) { & $tailscaleExe ip -4 } else { "(Tailscale belum terdeteksi - jalankan 'tailscale ip -4' manual)" }

try {
    $ping = Invoke-RestMethod -Uri "http://localhost:$AgentPort/ping" -TimeoutSec 5
    Write-Host "Ops Agent hidup: $($ping | ConvertTo-Json -Compress)" -ForegroundColor Green
} catch {
    Write-Host "Ops Agent belum merespons - cek Task Scheduler ('OrulabsPOS Ops Agent')." -ForegroundColor Red
}

Write-Host ""
Write-Host "=== Bootstrap selesai ===" -ForegroundColor Green
Write-Host "Langkah manual yang masih HARUS dilakukan:" -ForegroundColor Yellow
Write-Host "  1. Isi .env (BASE_URL sesuai IP LAN mini PC ini, CAFE_NAME, dst) - lihat DEPLOYMENT.md."
Write-Host "  2. Setup database: python -c \"from app import create_app, db; app = create_app(); app.app_context().push(); db.create_all()\" lalu python seed_users.py"
Write-Host "  3. Generate ulang QR code tiap meja setelah BASE_URL diisi."
Write-Host ""
Write-Host "Untuk didaftarkan di dashboard.html (laptop kontrol):" -ForegroundColor Cyan
Write-Host "  IP Tailscale : $tsIp"
Write-Host "  Port Agent   : $AgentPort"
Write-Host "  Token        : lihat isi ops\.env (baris AGENT_TOKEN) di atas"
Write-Host "  (atau langsung pakai tombol 'Cari Device di Tailscale' di dashboard - IP-nya akan muncul otomatis)"
