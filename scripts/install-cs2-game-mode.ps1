# Per-user installation; no administrator privileges required. ASCII only.
$ErrorActionPreference = "Stop"
$watcher = Join-Path $PSScriptRoot "cs2-game-mode.ps1"
$helper = Join-Path $PSScriptRoot "stop-ai-console.py"
$python = Join-Path (Split-Path -Parent $PSScriptRoot) ".venv\Scripts\python.exe"
foreach ($required in @($watcher, $helper, $python)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required file: $required" }
}
$startup = [Environment]::GetFolderPath("Startup")
$vbs = Join-Path $startup "ToucheCs2GameMode.vbs"
$command = 'powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $watcher + '"'
$content = "Set sh = CreateObject(""WScript.Shell"")`r`nsh.Run """ + $command.Replace('"', '""') + """, 0, False`r`n"
[IO.File]::WriteAllText($vbs, $content, [Text.Encoding]::ASCII)
Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-WindowStyle", "Hidden",
    "-ExecutionPolicy", "Bypass", "-File", ('"' + $watcher + '"')) -WindowStyle Hidden -ErrorAction Stop | Out-Null
Write-Output "CS2 game mode installed and started: $vbs"
