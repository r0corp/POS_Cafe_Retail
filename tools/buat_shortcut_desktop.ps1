# tools/buat_shortcut_desktop.ps1
#
# Bikin shortcut "Orulabs POS" di Desktop, buka aplikasi dalam jendela
# Chrome/Edge mode "app" (tanpa address bar/tab, kelihatan seperti
# aplikasi biasa) - dobel klik ikonnya = aplikasi langsung kebuka di
# http://localhost:8000, tidak perlu buka browser lalu ketik alamat.
#
# Script ini SAMA PERSIS dipakai di laptop dev maupun mini PC toko -
# path repo-nya dideteksi otomatis dari lokasi file ini sendiri, jadi
# tidak perlu diedit sebelum dipakai di mesin yang berbeda.
#
# Cara pakai: dobel klik tools\buat_shortcut_desktop.bat (bukan file
# .ps1 ini langsung).

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$logoSource = Join-Path $repoRoot "android-app\app\src\main\res\drawable\ic_launcher_foreground.png"
$icoDir = Join-Path $repoRoot "tools"
$icoPath = Join-Path $icoDir "orulabs_pos.ico"
$appUrl = "http://localhost:8000"

if (-not (Test-Path $logoSource)) {
    throw "Tidak ketemu logo sumber di $logoSource"
}

Write-Host "Menyiapkan ikon (logo besar tanpa background, gaya ikon Chrome)..."
$pythonExe = Get-Command python -All -ErrorAction SilentlyContinue |
    Where-Object { $_.Source -notmatch "\\WindowsApps\\" } |
    Select-Object -First 1 -ExpandProperty Source
if (-not $pythonExe) {
    throw "python.exe asli tidak ketemu di PATH (yang ketemu cuma stub WindowsApps)."
}

$pyScript = @"
from PIL import Image
im = Image.open(r'$logoSource').convert('RGBA')
bbox = im.getbbox()
cropped = im.crop(bbox)
w, h = cropped.size
side = max(w, h)
margin = int(side * 0.06)
canvas_size = side + margin * 2
canvas = Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 0, 0))
canvas.paste(cropped, ((canvas_size - w) // 2, (canvas_size - h) // 2), cropped)
canvas.save(r'$icoPath', format='ICO', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
"@
& $pythonExe -c $pyScript

$browser = $null
foreach ($p in @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
)) {
    if (Test-Path $p) { $browser = $p; break }
}
if (-not $browser) {
    throw "Chrome/Edge tidak ketemu di lokasi umum - install salah satu dulu."
}
Write-Host "Pakai browser: $browser"

$desktopPath = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktopPath "Orulabs POS.lnk"
Remove-Item $shortcutPath -Force -ErrorAction SilentlyContinue

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($shortcutPath)
$Shortcut.TargetPath = $browser
$Shortcut.Arguments = "--app=$appUrl --new-window"
$Shortcut.IconLocation = $icoPath
$Shortcut.Description = "Orulabs Cafe POS"
$Shortcut.WorkingDirectory = Split-Path $browser
$Shortcut.Save()

Write-Host ""
Write-Host "Selesai! Shortcut 'Orulabs POS' sudah ada di Desktop."
Write-Host "Dobel klik untuk buka aplikasi di $appUrl"
