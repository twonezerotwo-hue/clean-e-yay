param([Parameter(Mandatory=$true)][string]$TempDir)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "..\..\scripts\cs2-game-mode.ps1")
$script:processes = @(
    [pscustomobject]@{ ProcessId=101; ParentProcessId=1; Name="powershell.exe"; ExecutablePath="powershell.exe"; CommandLine=('-File "' + $keeperScript + '"') },
    [pscustomobject]@{ ProcessId=102; ParentProcessId=1; Name="powershell.exe"; ExecutablePath="powershell.exe"; CommandLine='-File C:\other\keeper.ps1' },
    [pscustomobject]@{ ProcessId=201; ParentProcessId=101; Name="python.exe"; ExecutablePath=$py; CommandLine='python -m apps.supervisor' },
    [pscustomobject]@{ ProcessId=202; ParentProcessId=201; Name="python.exe"; ExecutablePath='C:\Python\python.exe'; CommandLine='python -m apps.supervisor' },
    [pscustomobject]@{ ProcessId=203; ParentProcessId=1; Name="python.exe"; ExecutablePath='C:\other\python.exe'; CommandLine='python -m apps.supervisor' },
    [pscustomobject]@{ ProcessId=301; ParentProcessId=1; Name="python.exe"; ExecutablePath=$voicePy; CommandLine='python -m uvicorn main:app' },
    [pscustomobject]@{ ProcessId=401; ParentProcessId=101; Name="node.exe"; ExecutablePath='C:\node.exe'; CommandLine='node next start -p 4000' },
    [pscustomobject]@{ ProcessId=402; ParentProcessId=102; Name="node.exe"; ExecutablePath='C:\node.exe'; CommandLine='node next start -p 4000' },
    [pscustomobject]@{ ProcessId=501; ParentProcessId=1; Name="ollama.exe"; ExecutablePath=$ollama; CommandLine='ollama serve' }
)
function Get-CimInstance { return $script:processes }
$snapshot = Get-AiSnapshot
if ($snapshot.Keepers.Count -ne 1 -or $snapshot.Keepers[0].ProcessId -ne 101) { throw "Keeper selection leaked" }
$selected = @($snapshot.Approved | ForEach-Object { $_.ProcessId } | Sort-Object)
if (($selected -join ',') -ne '201,202,301,401,501') { throw "AI selection included another checkout" }
if (-not $snapshot.RestoreKeeper -or -not $snapshot.Voice -or -not $snapshot.Ollama) { throw "Prior services were not captured" }
$stateFile = Join-Path $TempDir "state.json"
$logFile = Join-Path $TempDir "game.log"
$script:playing = $false
$script:paused = 0
$script:resumed = 0
function Test-Cs2Running { return $script:playing }
function Get-AiSnapshot { return @{ RestoreKeeper=$true; Voice=$false; Ollama=$true } }
function Pause-LocalAi($snapshot) { $script:paused++ }
function Resume-LocalAi($state) {
    if (-not $state.RestoreKeeper -or $state.Voice -or -not $state.Ollama) { throw "Restore state changed" }
    $script:resumed++
}
Update-GameMode
if ($script:paused -ne 0 -or $script:resumed -ne 0) { throw "Idle mode changed services" }
$script:playing = $true
Update-GameMode
Update-GameMode
if ($script:paused -ne 1 -or -not (Test-Path -LiteralPath $stateFile)) { throw "Pause is not idempotent" }
$script:playing = $false
Update-GameMode
Update-GameMode
if ($script:resumed -ne 1 -or (Test-Path -LiteralPath $stateFile)) { throw "Resume is not idempotent" }
# A restarted watcher must recover a persisted pause after CS2 has closed.
'{"RestoreKeeper":true,"Voice":false,"Ollama":true}' | Set-Content -LiteralPath $stateFile
Update-GameMode
if ($script:resumed -ne 2) { throw "Persisted pause was not recovered" }
Write-Output "CS2 pause/resume state checks passed"
