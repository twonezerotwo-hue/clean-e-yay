# Local AI pause/resume for CS2. ASCII only; compatible with PowerShell 5.1.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$keeperScript = Join-Path $PSScriptRoot "local-autostart.ps1"
$py = Join-Path $root ".venv\Scripts\python.exe"
$ollama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
$voiceRoot = Join-Path $env:LOCALAPPDATA "VoiceStudioWorkspace\VoiceStudio\project"
$voicePy = Join-Path $voiceRoot ".venv\Scripts\python.exe"
$stateDir = Join-Path $env:LOCALAPPDATA "ToucheLocalRunner"
$stateFile = Join-Path $stateDir "cs2-game-state.json"
$approvedFile = Join-Path $stateDir "cs2-approved-processes.json"
$logFile = Join-Path $stateDir "cs2-game-mode.log"
# shortcut: this PC's Steam library; update this path if CS2 moves libraries.
$cs2 = "C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\bin\win64\cs2.exe"

function Game-Log([string]$message) {
    "[$(Get-Date -Format o)] $message" | Out-File -LiteralPath $logFile -Append -Encoding ascii
}

function Test-Cs2Running {
    return (@(Get-Process -Name cs2 -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -eq $cs2 }).Count -gt 0)
}

function Get-AiSnapshot {
    $all = @(Get-CimInstance Win32_Process)
    $keepers = @($all | Where-Object {
        $_.Name -eq "powershell.exe" -and
        $_.CommandLine -match ('(?i)-File\s+"?' + [regex]::Escape($keeperScript) + '"?(\s|$)')
    })
    $keeperIds = @($keepers | ForEach-Object { $_.ProcessId })
    $services = @($all | Where-Object {
        ($_.ExecutablePath -eq $py -and $_.CommandLine -match '-m\s+apps\.supervisor(\s|$)') -or
        ($_.Name -eq "node.exe" -and $_.ParentProcessId -in $keeperIds -and
            $_.CommandLine -match 'next.*start -p 4000') -or
        ($_.ExecutablePath -eq $voicePy -and $_.CommandLine -match 'uvicorn.*main:app') -or
        ($_.ExecutablePath -eq $ollama -and $_.CommandLine -match '\sserve(\s|$)') -or
        ($_.ExecutablePath -eq (Join-Path $root "tools\ngrok.exe") -and $_.CommandLine -match '\shttp\s+4000')
    })
    $approved = @($services)
    do {
        $ids = @($approved | ForEach-Object { $_.ProcessId })
        $children = @($all | Where-Object {
            $_.ParentProcessId -in $ids -and $_.ProcessId -notin $ids
        })
        $approved += $children
    } while ($children.Count -gt 0)
    return [pscustomobject]@{
        Keepers = $keepers
        Services = $services
        Approved = $approved
        RestoreKeeper = ($keepers.Count -gt 0 -or @($services | Where-Object {
            $_.ExecutablePath -eq $py
        }).Count -gt 0)
        Voice = (@($services | Where-Object { $_.ExecutablePath -eq $voicePy }).Count -gt 0)
        Ollama = (@($services | Where-Object { $_.ExecutablePath -eq $ollama }).Count -gt 0)
    }
}

function Pause-LocalAi($snapshot) {
    # Stop only the keeper itself; application workers get a graceful interrupt.
    foreach ($keeper in $snapshot.Keepers) {
        $current = Get-CimInstance Win32_Process -Filter "ProcessId=$($keeper.ProcessId)"
        if ($current -and $current.CreationDate -eq $keeper.CreationDate -and
            $current.CommandLine -eq $keeper.CommandLine) {
            Stop-Process -Id $keeper.ProcessId -Force -ErrorAction Stop
        }
    }
    ConvertTo-Json -InputObject @($snapshot.Approved | ForEach-Object {
        @{ pid = $_.ProcessId; path = $_.ExecutablePath }
    }) -Depth 3 | Set-Content -LiteralPath $approvedFile -Encoding UTF8
    foreach ($service in ($snapshot.Services | Sort-Object { $_.ExecutablePath -eq $ollama })) {
        if (-not (Get-Process -Id $service.ProcessId -ErrorAction SilentlyContinue)) { continue }
        if ($service.ExecutablePath -eq $ollama) {
            try {
                $loaded = Invoke-RestMethod "http://127.0.0.1:11434/api/ps" -TimeoutSec 5
                foreach ($model in $loaded.models) {
                    $body = @{ model=$model.name; keep_alive=0 } | ConvertTo-Json
                    Invoke-RestMethod "http://127.0.0.1:11434/api/generate" -Method Post `
                        -ContentType "application/json" -Body $body -TimeoutSec 20 | Out-Null
                }
            } catch { Game-Log "WARNING: model unload failed: $($_.Exception.Message)" }
        }
        $ErrorActionPreference = "Continue"
        try {
            & $py (Join-Path $PSScriptRoot "stop-ai-console.py") $service.ProcessId $approvedFile 2>> $logFile
            $result = $LASTEXITCODE
        } finally { $ErrorActionPreference = "Stop" }
        if ($result -ne 0) {
            Game-Log "WARNING: graceful stop refused/failed for PID $($service.ProcessId); not force-killed"
        }
    }
    Game-Log "CS2 detected: AI shutdown requested; saved files are retained"
}

function Resume-LocalAi($state) {
    if ($state.RestoreKeeper) {
        $keeperArgs = @("-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass",
            "-File", ('"' + $keeperScript + '"'))
        if (-not $state.Voice) { $keeperArgs += "-SkipVoiceStudio" }
        Start-Process -FilePath "powershell.exe" -ArgumentList $keeperArgs -WindowStyle Hidden -ErrorAction Stop | Out-Null
    } else {
        if ($state.Ollama) {
            Start-Process -FilePath $ollama -ArgumentList "serve" -WindowStyle Hidden -ErrorAction Stop | Out-Null
        }
        if ($state.Voice) {
            Start-Process -FilePath $voicePy -ArgumentList @("-m", "uvicorn", "main:app", "--app-dir", "backend",
                "--host", "127.0.0.1", "--port", "3900") -WorkingDirectory $voiceRoot `
                -WindowStyle Hidden -ErrorAction Stop | Out-Null
        }
    }
    Game-Log "CS2 closed: previous AI services restart requested"
}

function Update-GameMode {
    $playing = Test-Cs2Running
    if ($playing -and -not (Test-Path -LiteralPath $stateFile)) {
        $snapshot = Get-AiSnapshot
        @{ RestoreKeeper = $snapshot.RestoreKeeper; Voice = $snapshot.Voice; Ollama = $snapshot.Ollama } |
            ConvertTo-Json | Set-Content -LiteralPath ($stateFile + ".tmp") -Encoding UTF8
        Move-Item -LiteralPath ($stateFile + ".tmp") -Destination $stateFile -Force
        Pause-LocalAi $snapshot
    } elseif (-not $playing -and (Test-Path -LiteralPath $stateFile)) {
        $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
        Resume-LocalAi $state
        [IO.File]::Delete($stateFile)
    }
}

if ($MyInvocation.InvocationName -ne ".") {
    New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
    $mutex = New-Object Threading.Mutex($false, "Local\ToucheCs2GameMode")
    try { $owned = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $owned = $true }
    if (-not $owned) { $mutex.Dispose(); exit }
    Game-Log "game-mode watcher started"
    try {
        while ($true) {
            try { Update-GameMode } catch { Game-Log "ERROR: $($_.Exception.Message)" }
            Start-Sleep -Seconds 3
        }
    } finally {
        $mutex.ReleaseMutex()
        $mutex.Dispose()
    }
}
