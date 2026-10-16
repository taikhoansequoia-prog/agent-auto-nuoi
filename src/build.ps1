# ============================================================
# build.ps1 - Dong goi EXE chuan hoa (Sprint 0.1)
#   - Tat app dang chay (mo file .pyd -> PermissionError khi build)
#   - Stamp build time (va version neu truyen -Version) vao version.py
#   - PyInstaller build, bao ket qua + duong dan EXE
# Cach dung:
#   powershell -ExecutionPolicy Bypass -File build.ps1
#   powershell -ExecutionPolicy Bypass -File build.ps1 -Version 1.2.0
# ============================================================
param([string]$Version = "")
$ErrorActionPreference = "Stop"
$Py = "C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64\python.exe"
$Root = $PSScriptRoot

# 1. Dong app dang chay (neu co)
$killed = Get-Process GPM_Auto_Bot -ErrorAction SilentlyContinue
if ($killed) {
    Write-Host "[build] Dang dong $($killed.Count) tien trinh GPM_Auto_Bot cu..." -ForegroundColor Yellow
    $killed | Stop-Process -Force
    Start-Sleep -Seconds 2
}

# 2. Stamp version + build time vao version.py
$verFile = Join-Path $Root "version.py"
if (Test-Path $verFile) {
    $stamp = Get-Date -Format "dd/MM/yyyy HH:mm"
    $content = Get-Content $verFile -Raw
    if ($Version) { $content = $content -replace '__version__ = ".*?"', "__version__ = `"$Version`"" }
    $content = $content -replace '__build_time__ = ".*?"', "__build_time__ = `"$stamp`""
    Set-Content -Path $verFile -Value $content -NoNewline -Encoding UTF8
    Write-Host "[build] Da stamp version.py -> build $stamp" -ForegroundColor Cyan
} else {
    Write-Host "[build] CANH BAO: khong thay version.py, bo qua stamp." -ForegroundColor Yellow
}

# 3. Build
Push-Location $Root
try {
    & $Py -m PyInstaller GPM_Auto_Bot.spec --noconfirm
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[build] THAT BAI (exit $LASTEXITCODE). Xem thong loi o tren." -ForegroundColor Red
        exit 1
    }
} finally {
    Pop-Location
}

$exe = Join-Path $Root "dist\GPM_Auto_Bot\GPM_Auto_Bot.exe"
Write-Host "[build] THANH CONG -> $exe" -ForegroundColor Green
Write-Host "[build] Muc luc: mo app moi kiem tra tieu de cua so (phai hien 'build ...')." -ForegroundColor Cyan
