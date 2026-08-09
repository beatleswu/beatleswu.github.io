# E10 Zone 1 - AUDITION SET B (recast) one-click launcher (Owner machine only).
#
# Do not run this from the remote Claude Web sandbox -- it cannot reach
# api.elevenlabs.io. This script is meant to be launched by
# Run_Audition_Set_B.cmd on the Owner's local Windows machine.
#
# Set B recasts ONLY the roles the Owner rejected in Set A (zh-TW Elder,
# zh-TW Hero, English Hero). It never touches roles already locked/approved
# in casting_candidates.json, and it never regenerates Set A.
#
# Credential handling: the API key is read once via a masked prompt into
# this process's environment only. It is never written to disk, never
# echoed/logged, and is cleared from the environment before this script
# exits (success or failure).

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

function Fail([string]$ZhMessage, [string]$EnMessage) {
    # exit inside a try/finally is not guaranteed to run the finally block in
    # PowerShell, so clear the key here explicitly on every failure path too.
    Remove-Item Env:\ELEVENLABS_API_KEY -ErrorAction SilentlyContinue
    Write-Host ""
    Write-Host "錯誤：$ZhMessage" -ForegroundColor Red
    if ($EnMessage) {
        Write-Host "Error detail: $EnMessage" -ForegroundColor DarkGray
    }
    Write-Host ""
    Read-Host "按 Enter 鍵關閉視窗 / Press Enter to close"
    exit 1
}

Write-Host "=== E10 Zone 1：試聽重選集 (AUDITION SET B - 補選角色) ===" -ForegroundColor Cyan
Write-Host "本工具只會為 3 個待補選角色（zh-TW 村長、zh-TW 主角、英文主角）"
Write-Host "從 ElevenLabs Voice Library 尋找新的候選聲音並產生試聽檔（約 9 個）。"
Write-Host "已核准鎖定的聲音（旁白、傳令、村長英文版）不會被重新產生或覆蓋。"
Write-Host "不會生成完整劇情台詞、背景音樂或音效，也不會部署或連線正式環境。"
Write-Host ""

# 1. Verify this launcher is sitting next to the real tool (correct repo location).
$PythonScript = Join-Path $ScriptDir "generate_zone1_audio.py"
if (-not (Test-Path $PythonScript)) {
    Fail "找不到 generate_zone1_audio.py，請確認這個資料夾是完整的 repo 內容（tools\e10_zone1_audio\）。" `
         "generate_zone1_audio.py not found next to this launcher script."
}

# 2. Verify Python is available.
$PythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCmd) {
    $PythonCmd = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $PythonCmd) {
    Fail "找不到 Python，請先安裝 Python 3（可從 python.org 下載）並確認安裝時有勾選「Add to PATH」。" `
         "Neither 'python' nor 'py' was found on PATH."
}
$PythonExe = $PythonCmd.Source

# 3. Securely prompt for the API key (masked input, this process only).
$SecureKey = Read-Host -Prompt "請輸入 ElevenLabs API Key（輸入時畫面不會顯示文字）" -AsSecureString
if ($SecureKey.Length -eq 0) {
    Fail "沒有輸入 API Key，已取消。" "No API key was entered."
}
$Bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureKey)
try {
    $PlainKey = [System.Runtime.InteropServices.Marshal]::PtrToStringUni($Bstr)
} finally {
    [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Bstr)
}
if ([string]::IsNullOrWhiteSpace($PlainKey)) {
    Fail "API Key 是空白的，已取消。" "API key was blank after decoding."
}

# Process-scoped only: not saved to user/machine environment, not written to disk.
$env:ELEVENLABS_API_KEY = $PlainKey
$PlainKey = $null

$ExitedCleanly = $false
try {
    Write-Host ""
    Write-Host "[1/2] 正在確認連線與 eleven_v3 模型可用性..." -ForegroundColor Cyan
    & $PythonExe $PythonScript --check
    if ($LASTEXITCODE -ne 0) {
        Fail "連線或模型檢查未通過，請確認 API Key 是否正確、網路是否正常，以及帳號是否可使用 eleven_v3 模型。" `
             "'--check' exited with code $LASTEXITCODE."
    }

    Write-Host ""
    Write-Host "[2/2] 正在搜尋 Voice Library 並產生補選試聽檔（AUDITION SET B）..." -ForegroundColor Cyan
    Write-Host "（若資料夾內有先前產生的補選試聽檔，會先清除再重新產生，避免新舊檔案混在一起。）"
    Write-Host "（此步驟需要即時查詢 ElevenLabs Voice Library，可能需要一點時間，請耐心等候。）"
    & $PythonExe $PythonScript --audition-set-b
    if ($LASTEXITCODE -ne 0) {
        Fail "補選試聽檔案產生或驗證失敗，請往上捲動查看詳細錯誤訊息（例如 Voice Library 搜尋失敗、加入聲音失敗，或某個角色完全沒有產生出可用的候選聲音）。若持續失敗，請把完整錯誤訊息回報給 Claude。" `
             "'--audition-set-b' exited with code $LASTEXITCODE."
    }
    $ExitedCleanly = $true
}
finally {
    # Always clear the key from this process, regardless of success/failure.
    Remove-Item Env:\ELEVENLABS_API_KEY -ErrorAction SilentlyContinue
}

if (-not $ExitedCleanly) {
    exit 1
}

# 4. Open the audition folder for the Owner.
$AuditionDir = Join-Path $ScriptDir "_local_review\audition_set_b"
if (-not (Test-Path $AuditionDir)) {
    Fail "找不到試聽資料夾，產生流程可能未完全成功。" "Expected output folder not found: $AuditionDir"
}
$Mp3Count = (Get-ChildItem -Path $AuditionDir -Filter "*.mp3" -File | Where-Object { $_.Length -gt 0 }).Count
if ($Mp3Count -eq 0) {
    Fail "試聽資料夾內沒有產生任何檔案，請重新執行一次；若持續失敗，請回報給 Claude。" `
         "Expected at least 1 non-empty MP3 file, found $Mp3Count in $AuditionDir."
}

Write-Host ""
Write-Host "完成！已產生 $Mp3Count 個補選試聽檔，正在開啟資料夾..." -ForegroundColor Green
Start-Process explorer.exe $AuditionDir

Write-Host ""
Write-Host "全部完成，可以關閉這個視窗了。試聽完畢後，請告訴 Claude 您選定的聲音。" -ForegroundColor Green
Start-Sleep -Seconds 2
