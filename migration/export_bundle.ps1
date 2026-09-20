<#
    Jalankan skrip ini di KOMPUTER LAMA (yang sekarang menjalankan Cafe POS)
    pada hari migrasi ke mini PC.

    Langkah yang dilakukan:
    1. Matikan proses serve_production.py yang sedang jalan (kalau ada) -
       supaya database tidak sedang ditulis pas disalin (snapshot konsisten).
    2. Salin seluruh folder project ke lokasi tujuan (USB drive / network
       share / folder di mini PC lewat network path) - KECUALI venv,
       __pycache__, .git, dan cache lain yang tidak perlu ikut pindah
       (bakal dibuat ulang di mini PC lewat setup_mini_pc.ps1).

    Cara pakai (dari folder project ini):
        cd "D:\10.  PROJECT\PYTHON\POS_Cafe_Retail"
        powershell -ExecutionPolicy Bypass -File migration\export_bundle.ps1 -Destination "E:\CafePOS_Migrasi"

    -Destination bisa USB drive, folder network share (\\mini-pc\share\...),
    atau folder lokal biasa yang nanti dipindahkan manual.
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$Destination
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Get-Item "$PSScriptRoot\..").FullName

Write-Host "=== Cafe POS - Export untuk migrasi ===" -ForegroundColor Cyan
Write-Host "Sumber : $ProjectRoot"
Write-Host "Tujuan : $Destination"
Write-Host ""

# 1. Matikan server produksi kalau masih jalan, supaya database tidak
#    berubah lagi selama proses penyalinan.
$listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    $procId = $listener[0].OwningProcess
    Write-Host "Menghentikan server produksi (PID $procId) di port 8000..." -ForegroundColor Yellow
    Stop-Process -Id $procId -Force
    Start-Sleep -Seconds 1
} else {
    Write-Host "Server produksi tidak sedang jalan - lanjut." -ForegroundColor Yellow
}

# 2. Salin project, kecualikan folder yang akan dibuat ulang di mini PC.
if (-not (Test-Path $Destination)) {
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
}

$ExcludeDirs = @("venv", "__pycache__", ".git", ".pytest_cache", ".refactor_backup", "android-app\app\build", "android-app\.gradle")

Write-Host ""
Write-Host "Menyalin project (ini bisa makan waktu beberapa menit tergantung ukuran uploads/backups)..." -ForegroundColor Cyan

$robocopyArgs = @(
    "`"$ProjectRoot`"",
    "`"$Destination`"",
    "/E",
    "/XD"
) + ($ExcludeDirs | ForEach-Object { "`"$ProjectRoot\$_`"" }) + @("/NFL", "/NDL", "/NP")

Start-Process -FilePath "robocopy.exe" -ArgumentList $robocopyArgs -NoNewWindow -Wait

Write-Host ""
Write-Host "=== Selesai ===" -ForegroundColor Green
Write-Host "Project sudah disalin ke: $Destination"
Write-Host ""
Write-Host "Langkah selanjutnya di MINI PC:" -ForegroundColor Cyan
Write-Host "  1. Pastikan folder tersalin lengkap ke lokasi projectnya di mini PC."
Write-Host "  2. Jalankan migration\setup_mini_pc.ps1 dari folder itu."
Write-Host "  3. Update BASE_URL di .env sesuai IP mini PC yang baru."
Write-Host "  4. Generate ulang QR code tiap meja (lewat halaman Denah Meja)."
Write-Host "  5. Kalau pakai Android app kasir: update server_url di strings.xml"
Write-Host "     dan domain di network_security_config.xml, lalu build ulang APK."
