<#
    Jalankan skrip ini DI MINI PC untuk update aplikasi ke versi terbaru
    dari GitHub (r0corp/POS_Cafe_Retail), SEBAGAI ADMINISTRATOR (klik kanan
    PowerShell -> Run as Administrator) - dibutuhkan buat stop/start service.

    Dipakai untuk update rutin SETELAH proses migrasi awal selesai (lewat
    export_bundle.ps1 + setup_mini_pc.ps1, atau lewat zip manual). Skrip ini
    TIDAK menyentuh .env, instance/ (database), app/static/uploads/,
    app/static/qrcodes/, atau venv/ - semua data & konfigurasi lokal aman.

    Yang dilakukan:
    1. Kalau folder ini belum jadi git repo, hubungkan dulu ke GitHub
       (sekali saja, run pertama kali).
    2. Hentikan service Windows "OrulabsPOS" (NSSM) kalau sedang jalan.
    3. Ambil kode terbaru dari origin/main (git fetch + reset --hard,
       aman karena mini PC tidak seharusnya py ada perubahan lokal di
       file kode - hanya di .env/instance/uploads yang di luar git).
    4. Install ulang dependency (jaga-jaga kalau requirements.txt berubah).
    5. Compile ulang terjemahan (jaga-jaga kalau ada string baru).
    6. Jalankan lagi service "OrulabsPOS".

    Cara pakai (dari folder project di mini PC):
        cd C:\OrulabsPOS
        powershell -ExecutionPolicy Bypass -File migration\update_mini_pc.ps1
#>

param(
    [string]$ServiceName = "OrulabsPOS",
    [string]$NssmPath = "C:\nssm\nssm.exe",
    [string]$RepoUrl = "https://github.com/r0corp/POS_Cafe_Retail.git"
)

$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Skrip ini harus dijalankan sebagai Administrator (buat stop/start service NSSM)." -ForegroundColor Red
    Write-Host "Klik kanan PowerShell -> Run as Administrator, lalu jalankan lagi." -ForegroundColor Red
    exit 1
}

$ProjectRoot = (Get-Item "$PSScriptRoot\..").FullName
Write-Host "=== Orulabs POS - Update dari GitHub ===" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"
Write-Host ""

Push-Location $ProjectRoot

# 1. Hubungkan ke GitHub kalau belum (run pertama kali di mini PC ini).
if (-not (Test-Path "$ProjectRoot\.git")) {
    Write-Host "Belum terhubung ke GitHub - menghubungkan sekarang (sekali saja)..." -ForegroundColor Cyan
    git init | Out-Null
    git remote add origin $RepoUrl
    git fetch origin
    git checkout -f -B main origin/main
    Write-Host "Terhubung ke $RepoUrl." -ForegroundColor Green
} else {
    Write-Host "Sudah terhubung ke git repo - lanjut ambil update." -ForegroundColor Cyan
}

# 2. Stop service.
Write-Host ""
$nssmExists = Test-Path $NssmPath
if ($nssmExists) {
    Write-Host "Menghentikan service '$ServiceName'..." -ForegroundColor Cyan
    & $NssmPath stop $ServiceName | Out-Null
    Start-Sleep -Seconds 2
} else {
    Write-Host "nssm.exe tidak ditemukan di '$NssmPath' - lewati stop/start service (matikan manual kalau perlu)." -ForegroundColor Yellow
}

# 3. Tarik kode terbaru.
Write-Host ""
Write-Host "Mengambil update terbaru dari GitHub..." -ForegroundColor Cyan
git fetch origin
$before = git rev-parse HEAD
git reset --hard origin/main
$after = git rev-parse HEAD

if ($before -eq $after) {
    Write-Host "Sudah versi terbaru, tidak ada perubahan." -ForegroundColor Green
} else {
    Write-Host "Update: $($before.Substring(0,7)) -> $($after.Substring(0,7))" -ForegroundColor Green
    git log --oneline "$before..$after"
}

# 4. Dependency.
Write-Host ""
Write-Host "Sinkronkan dependency Python..." -ForegroundColor Cyan
& "$ProjectRoot\venv\Scripts\pip.exe" install -r requirements.txt --quiet

# 5. Terjemahan.
Write-Host "Compile ulang terjemahan..." -ForegroundColor Cyan
& "$ProjectRoot\venv\Scripts\pybabel.exe" compile -d app\translations | Out-Null

# 6. Start service lagi.
Write-Host ""
if ($nssmExists) {
    Write-Host "Menjalankan lagi service '$ServiceName'..." -ForegroundColor Cyan
    & $NssmPath start $ServiceName | Out-Null
    Start-Sleep -Seconds 2
    & $NssmPath status $ServiceName
} else {
    Write-Host "Jalankan server manual: venv\Scripts\python.exe serve_production.py" -ForegroundColor Yellow
}

Pop-Location

Write-Host ""
Write-Host "=== Selesai ===" -ForegroundColor Green
Write-Host "Cek http://localhost:8000 untuk pastikan aplikasi jalan normal setelah update."
