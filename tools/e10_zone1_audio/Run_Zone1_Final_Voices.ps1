# E10 Zone 1 - FINAL LOCKED VOICES full spoken-dialogue launcher (Owner machine only).
#
# Do not run this from the remote Claude Web sandbox -- it cannot reach
# api.elevenlabs.io. This script is meant to be launched by
# Run_Zone1_Final_Voices.cmd on the Owner's local Windows machine.
#
# Generates the COMPLETE approved Zone 1 spoken dialogue (both locales,
# every canonical beat, verbatim -- never rewritten) using the final LOCKED
# cast in casting_candidates.json. FAILS CLOSED: if any of the 8 role x
# locale slots is not locked with a real approved voice_id, nothing is
# generated. No BGM/SFX/ambience. Output is local review-only until the
# Owner performs final listening approval.
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

Write-Host "=== E10 Zone 1：正式配音完整生成 (FINAL LOCKED VOICES) ===" -ForegroundColor Cyan
Write-Host "本工具會用已鎖定核准的 8 個角色聲音，生成 Zone 1 全部中英文正式台詞語音。"
Write-Host "只要有任何一個角色尚未鎖定核准的聲音，就不會生成任何檔案（fail closed）。"
Write-Host "不會生成背景音樂或音效，也不會部署或連線正式環境。這些檔案在您試聽核准前，"
Write-Host "都只是本機審核用素材，不是正式production素材。"
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
    Write-Host "[2/2] 正在生成 Zone 1 完整正式配音（中英文全部台詞）..." -ForegroundColor Cyan
    Write-Host "（若資料夾內有先前產生的正式配音檔，會先清除再重新產生。這一步需要生成較多語音，請耐心等候。）"
    & $PythonExe $PythonScript --generate-tts
    if ($LASTEXITCODE -ne 0) {
        Fail "正式配音產生或驗證失敗，請往上捲動查看詳細錯誤訊息。最常見原因是還有角色尚未鎖定核准的聲音（GENERATE_TTS_BLOCKED_UNRESOLVED_ROLES）——這種情況請聯絡 Claude 確認 casting 是否已完整鎖定。若持續失敗，請把完整錯誤訊息回報給 Claude。" `
             "'--generate-tts' exited with code $LASTEXITCODE."
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

# 4. Open the final voice review folder for the Owner.
$FinalDir = Join-Path $ScriptDir "_local_review\zone1_final_voices"
if (-not (Test-Path $FinalDir)) {
    Fail "找不到正式配音審核資料夾，產生流程可能未完全成功。" "Expected output folder not found: $FinalDir"
}
$Mp3Count = (Get-ChildItem -Path $FinalDir -Filter "*.mp3" -File | Where-Object { $_.Length -gt 0 }).Count
if ($Mp3Count -eq 0) {
    Fail "審核資料夾內沒有產生任何檔案，請重新執行一次；若持續失敗，請回報給 Claude。" `
         "Expected non-empty MP3 files, found $Mp3Count in $FinalDir."
}

Write-Host ""
Write-Host "完成！已產生 $Mp3Count 個正式配音審核檔，正在開啟資料夾..." -ForegroundColor Green
Start-Process explorer.exe $FinalDir

Write-Host ""
Write-Host "全部完成，可以關閉這個視窗了。這些是審核用素材，尚非正式 production 素材。" -ForegroundColor Green
Write-Host "試聽核准後，請告訴 Claude，才會進到 BGM / SFX 與後續整合。" -ForegroundColor Green
Start-Sleep -Seconds 2
