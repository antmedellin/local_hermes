<# : ---- batch launcher (PowerShell sees this whole block as a comment) ----
@echo off
setlocal
set "HERMES_SETUP_FILE=%~f0"
set "HERMES_SETUP_DIR=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& ([scriptblock]::Create([IO.File]::ReadAllText($env:HERMES_SETUP_FILE))) %*"
exit /b %errorlevel%
---- end batch launcher, PowerShell script starts below ---- #>
<#
.SYNOPSIS
    One-shot setup for Local Hermes on a shared Windows PC: WSL2 + Ubuntu + Docker Desktop + Hermes stack.

.DESCRIPTION
    Steps:
      1.  Verify WSL2 is installed
      2.  Set WSL2 memory (55 GB) and swap (8 GB) in %USERPROFILE%\.wslconfig
      3.  Create the Ubuntu distro and a Linux user (password = "password")
      4.  apt update / upgrade
      5.  apt install gedit htop git
      6.  git clone local_hermes
      7.  git submodule update --init --recursive
      8.  Verify Docker Desktop is installed and running
      9.  Turn on Docker Desktop WSL integration for Ubuntu
      10. docker compose pull
      11. docker compose build
      12. docker compose up -d
      13. Create the "Hermes" desktop shortcut
      14. Verify Hermes (containers, AI models downloaded and responding, dashboard, login) and open it

    No admin rights needed. WSL and Docker Desktop must already be installed on the PC.
    Safe to re-run: every step checks what is already done and skips it.
    Each Windows profile gets its OWN Ubuntu, repo, containers and models.
    The Linux username is the Windows username in lowercase.

HOW TO USE
    Double-click Setup-LocalHermes.cmd. That is it: this one file is the whole setup.
    Each person runs it while signed in to their own Windows profile.
    Afterwards, use the "Hermes" desktop shortcut after each sign-in.
    To change settings, edit the default values in the param() block below.
#>
[CmdletBinding()]
param(
    [string]$DistroName        = "Ubuntu",
    [string]$LinuxUser         = "",     # "" = Windows username, lowercase
    [string]$LinuxPassword     = "password",
    [int]   $MemoryGB          = 55,
    [int]   $SwapGB            = 8,
    [string]$RepoUrl           = "https://github.com/antmedellin/local_hermes.git",
    [string]$RepoFolder        = "local_hermes",
    [string]$DashboardUrl      = "http://localhost:9119",
    [string]$DashboardUser     = "admin",
    [string]$DashboardPassword = "password",
    [int]   $DockerTimeoutSec  = 300,
    [int]   $ModelTimeoutMin   = 120     # first-time model download limit
)

# "Continue" on purpose: wsl.exe and docker.exe write normal messages to stderr, and Windows
# PowerShell 5.1 would treat those as fatal under "Stop". Native tools are checked with $LASTEXITCODE.
# PowerShell cmdlets that MUST succeed (file writes, backups, settings) use -ErrorAction Stop so
# any failure jumps straight to the error handler instead of printing red text and carrying on.
$ErrorActionPreference = "Continue"
$env:WSL_UTF8 = "1"                   # makes wsl.exe print UTF-8 instead of UTF-16
$TotalSteps = 14

if (-not $LinuxUser) {
    $LinuxUser = ($env:USERNAME.ToLower() -replace '[^a-z0-9_-]', '')
    if ($LinuxUser -notmatch '^[a-z_][a-z0-9_-]{0,31}$') { $LinuxUser = "hermes" }
}

$setupDir = if ($env:HERMES_SETUP_DIR) { $env:HERMES_SETUP_DIR } else { $env:USERPROFILE }
$logPath  = Join-Path $setupDir "setup-localhermes.log"
try { Start-Transcript -Path $logPath -Append | Out-Null } catch {}

# ---------------------------------------------------------------- helpers
function Step([int]$n, [string]$msg) { Write-Host "`n[$n/$TotalSteps] $msg" -ForegroundColor Cyan }
function Ok([string]$msg)            { Write-Host "  OK   $msg" -ForegroundColor Green }
function Info([string]$msg)          { Write-Host "  ..   $msg" }
function Warn([string]$msg)          { Write-Host "  !!   $msg" -ForegroundColor Yellow }

function Get-Distros {
    (wsl.exe --list --quiet 2>$null) -replace "`0", "" |
        ForEach-Object { $_.Trim() } | Where-Object { $_ }
}

# Runs a bash command inside the distro and shows its output live. Returns the exit code.
# Use single quotes inside $Command (never double quotes).
function Invoke-Linux {
    param([Parameter(Mandatory)][string]$Command, [switch]$AsRoot, [switch]$AllowFail)
    $user = if ($AsRoot) { "root" } else { $LinuxUser }
    wsl.exe -d $DistroName -u $user -- bash -lc $Command | Out-Host
    $code = $LASTEXITCODE
    if ($code -ne 0 -and -not $AllowFail) { throw "Linux command failed (exit $code): $Command" }
    return $code
}

function Set-WslConfigKey([System.Collections.Generic.List[string]]$lines, [string]$key, [string]$value) {
    $newLine = "$key=$value"
    $sec = -1
    for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i].Trim() -ieq "[wsl2]") { $sec = $i; break } }
    if ($sec -lt 0) {
        if ($lines.Count -gt 0) { $lines.Add("") }
        $lines.Add("[wsl2]"); $lines.Add($newLine); return
    }
    $end = $lines.Count
    for ($j = $sec + 1; $j -lt $lines.Count; $j++) { if ($lines[$j].Trim() -match '^\[.+\]$') { $end = $j; break } }
    for ($j = $sec + 1; $j -lt $end; $j++) {
        if ($lines[$j] -match "^\s*$key\s*=") { $lines[$j] = $newLine; return }
    }
    $lines.Insert($sec + 1, $newLine)
}

function Set-JsonProp($obj, [string]$name, $value) {
    # keeps whatever casing the file already uses for the key
    $existing = $obj.PSObject.Properties | Where-Object { $_.Name -ieq $name } | Select-Object -First 1
    if ($existing) { $existing.Value = $value }
    else { $obj | Add-Member -NotePropertyName $name -NotePropertyValue $value }
}

$DockerExe = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
$DockerCli = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"

function Test-DockerEngine {
    if (-not (Test-Path $DockerCli)) { return $false }
    & $DockerCli info *> $null
    return ($LASTEXITCODE -eq 0)
}

function Start-DockerDesktop {
    # SilentlyContinue here = "no Docker process found" is a normal answer, not an error
    if (-not (Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue)) {
        Start-Process -FilePath $DockerExe | Out-Null
    }
    $deadline = (Get-Date).AddSeconds($DockerTimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-DockerEngine) { return $true }
        Start-Sleep -Seconds 5
    }
    return $false
}

function Stop-DockerDesktop {
    # SilentlyContinue here = a process that already closed is fine
    Get-Process -Name "Docker Desktop", "com.docker.backend", "com.docker.build" -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 8
}

# ---------------------------------------------------------------- Start-Hermes launcher
# Written to %LOCALAPPDATA%\LocalHermes\Start-Hermes.ps1. Used by the desktop shortcut AND by
# step 14 of this setup, so the same checks run every time Hermes is opened.
# Literal text: the __NAME__ placeholders are filled in at step 13.
$LauncherTemplate = @'
# Start-Hermes: created by Setup-LocalHermes.cmd
# Checks that Docker, this user's Hermes containers and AI models are running and that the
# dashboard login works, then opens the dashboard. Every failed check stops with a message.
param([int]$ModelTimeoutMin = 60, [int]$DashboardTimeoutSec = 180, [switch]$NoPause)

$Distro    = '__DISTRO__'
$LinuxUser = '__USER__'
$Repo      = '__REPO__'
$Url       = '__URL__'
$DashUser  = '__DASHUSER__'
$DashPass  = '__DASHPASS__'
$DockerExe = '__DOCKEREXE__'
$DockerCli = '__DOCKERCLI__'
$OllamaUrl = 'http://localhost:11434'
$DefaultModels = @('gemma4:12b', 'qwen3-embedding:8b')   # used only if docker-compose.yml cannot be read

$ErrorActionPreference = 'Continue'        # native tools are checked with $LASTEXITCODE
$ProgressPreference    = 'SilentlyContinue' # hides the web-request progress bar (it slows PowerShell 5.1 a lot)
$env:WSL_UTF8 = '1'
$logPath = Join-Path $env:LOCALAPPDATA 'LocalHermes\start-hermes.log'
try { Start-Transcript -Path $logPath -Append | Out-Null } catch {}

function Ok([string]$m)   { Write-Host "  OK  $m" -ForegroundColor Green }
function Info([string]$m) { Write-Host "  ..  $m" }
function Warn([string]$m) { Write-Host "  !!  $m" -ForegroundColor Yellow }
function Done([int]$code) { try { Stop-Transcript | Out-Null } catch {}; exit $code }
function Fail([string]$m) {
    Write-Host ''
    Write-Host "  XX  $m" -ForegroundColor Red
    Write-Host "      Log: $logPath"
    if (-not $NoPause) { Read-Host 'Press Enter to close' | Out-Null }
    Done 1
}
function Linux([string]$cmd) { wsl.exe -d $Distro -u $LinuxUser -- bash -lc $cmd }
function Get-HttpCode([string]$u) {
    # 0 = nothing answered
    try { return [int](Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 5).StatusCode }
    catch { if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode }; return 0 }
}
function Get-ContainerState([string]$name) {
    $s = & $DockerCli inspect -f '{{.State.Status}}' $name 2>$null
    if ($LASTEXITCODE -ne 0) { return 'missing' }
    return "$s".Trim()
}
function Show-Containers { Linux "cd ~/$Repo && docker compose ps -a" | Out-Host }

Write-Host "Starting Local Hermes for $LinuxUser" -ForegroundColor Cyan

# 1. Docker Desktop is installed ----------------------------------------------------
if (-not (Test-Path $DockerExe)) { Fail 'Docker Desktop is not installed on this PC. Installing it needs an admin, so ask IT.' }

# 2. Docker is not still running under another profile ------------------------------
# (SilentlyContinue = "no such process" is a normal answer here, not an error)
$me = [System.Diagnostics.Process]::GetCurrentProcess().SessionId
$others = Get-Process -Name 'Docker Desktop', 'com.docker.backend' -ErrorAction SilentlyContinue |
    Where-Object { $_.SessionId -ne $me }
if ($others) { Fail 'Docker is still running under another profile on this PC. Restart the computer (Start > Power > Restart), sign back in, and try again.' }

# 3. Docker engine is running -------------------------------------------------------
$inDockerUsers = [bool]((whoami /groups) -match '\\docker-users\b')
if (-not (Get-Process -Name 'Docker Desktop' -ErrorAction SilentlyContinue)) {
    Info 'Starting Docker Desktop (first time on this profile: click Accept if a Docker agreement window appears)'
    Start-Process -FilePath $DockerExe
}
$up = $false
for ($i = 0; $i -lt 60; $i++) {
    & $DockerCli info *> $null
    if ($LASTEXITCODE -eq 0) { $up = $true; break }
    Start-Sleep -Seconds 5
}
if (-not $up) {
    if (-not $inDockerUsers) { Fail "Docker did not start, and your account is not in the 'docker-users' group. Ask IT to run:  net localgroup docker-users `"$env:USERDOMAIN\$env:USERNAME`" /add   then sign out and back in." }
    Fail 'Docker did not start within 5 minutes. Open Docker Desktop, accept any prompt or read its error, then try again.'
}
Ok 'Docker is running'

# 4. Ubuntu can reach Docker --------------------------------------------------------
$ok = $false
for ($i = 0; $i -lt 24; $i++) {
    Linux 'docker info > /dev/null 2>&1'
    if ($LASTEXITCODE -eq 0) { $ok = $true; break }
    Start-Sleep -Seconds 5
}
if (-not $ok) { Fail "Ubuntu cannot reach Docker. In Docker Desktop: Settings > Resources > WSL integration > turn on $Distro > Apply & restart. Then try again." }
Ok 'Ubuntu can reach Docker'

# 5. Containers are up --------------------------------------------------------------
Info 'Starting Hermes containers (already-running ones are left alone)'
Linux "cd ~/$Repo && docker compose up -d" | Out-Host
if ($LASTEXITCODE -ne 0) { Fail 'Could not start the Hermes containers (see the messages above).' }
foreach ($c in 'ollama', 'hermes', 'hermes-dashboard') {
    $st = Get-ContainerState $c
    if ($st -ne 'running') { Show-Containers; Fail "Container '$c' is not running (state: $st). See the list above." }
}
Ok 'Containers are running (ollama, hermes, hermes-dashboard)'

# 6. AI models are fully downloaded -------------------------------------------------
$compose = (Linux "cat ~/$Repo/docker-compose.yml") -join "`n"
$Models = @([regex]::Matches($compose, 'ollama pull\s+([A-Za-z0-9._:/-]+)') | ForEach-Object { $_.Groups[1].Value } | Select-Object -Unique)
if ($Models.Count -eq 0) { $Models = $DefaultModels }

$api = $false
for ($i = 0; $i -lt 36; $i++) { if ((Get-HttpCode "$OllamaUrl/api/version") -eq 200) { $api = $true; break }; Start-Sleep -Seconds 5 }
if (-not $api) { Show-Containers; Fail "Ollama is not answering at $OllamaUrl." }

function Get-MissingModels {
    try   { $have = @((Invoke-RestMethod -Uri "$OllamaUrl/api/tags" -TimeoutSec 10).models | ForEach-Object { $_.name }) }
    catch { $have = @() }
    return @($Models | Where-Object { ($have -notcontains $_) -and ($have -notcontains "$($_):latest") })
}

$missing = Get-MissingModels
if ($missing.Count -gt 0) {
    Info "Downloading AI models: $($missing -join ', ')"
    Info 'The first time on a profile this can take 10 to 60 minutes. Leave this window open.'
    $start = Get-Date
    $deadline = $start.AddMinutes($ModelTimeoutMin)
    $restarted = $false
    while ($missing.Count -gt 0) {
        if ((Get-Date) -gt $deadline) { Fail "Models still not downloaded after $ModelTimeoutMin minutes: $($missing -join ', '). Check the network, then double-click the Hermes shortcut (the download resumes)." }
        if ((Get-ContainerState 'ollama-pull') -ne 'running') {
            # The downloader stopped but models are still missing: start it once more, then give up.
            if ($restarted) {
                & $DockerCli logs --tail 20 ollama-pull 2>&1 | Out-Host
                Fail 'The model download stopped before finishing (see above). Check the network and free disk space, then double-click the Hermes shortcut.'
            }
            Info 'Restarting the model downloader'
            & $DockerCli start ollama-pull *> $null
            $restarted = $true
        }
        $tail = & $DockerCli logs --tail 3 ollama-pull 2>&1 | Out-String
        $pcts = [regex]::Matches($tail, '(\d{1,3})%')
        $pct  = if ($pcts.Count -gt 0) { ", current file $($pcts[$pcts.Count - 1].Value)" } else { '' }
        $mins = [int]((Get-Date) - $start).TotalMinutes
        Info "Still downloading ($mins min so far$pct). Waiting for: $($missing -join ', ')"
        Start-Sleep -Seconds 30
        $missing = Get-MissingModels
    }
}
Ok "Models downloaded: $($Models -join ', ')"

# 7. AI models load and respond -----------------------------------------------------
# Embedding models first, chat model last, so the chat model is the one left loaded.
Info 'Loading the models to check they actually answer (can take a few minutes)'
foreach ($m in @($Models | Where-Object { $_ -match 'embed' })) {
    try {
        $body = @{ model = $m; input = 'warm up' } | ConvertTo-Json
        $r = Invoke-RestMethod -Method Post -Uri "$OllamaUrl/api/embed" -ContentType 'application/json' -Body $body -TimeoutSec 600
        if (-not $r.embeddings) { throw 'empty response' }
        Ok "$m answers"
    } catch { Fail "Model $m did not answer: $($_.Exception.Message)" }
}
foreach ($m in @($Models | Where-Object { $_ -notmatch 'embed' })) {
    try {
        $body = @{ model = $m; prompt = 'Reply with OK.'; stream = $false; options = @{ num_predict = 5 } } | ConvertTo-Json
        $r = Invoke-RestMethod -Method Post -Uri "$OllamaUrl/api/generate" -ContentType 'application/json' -Body $body -TimeoutSec 900
        if ($null -eq $r.response) { throw 'empty response' }
        Ok "$m answers"
    } catch { Fail "Model $m did not answer: $($_.Exception.Message)" }
}
try {
    foreach ($p in (Invoke-RestMethod -Uri "$OllamaUrl/api/ps" -TimeoutSec 10).models) {
        $size = [double]$p.size; $vram = [double]$p.size_vram
        if ($vram -le 0)        { Warn "$($p.name) is running on the CPU, not the GPU. It will be very slow. Check the NVIDIA driver." }
        elseif ($vram -lt $size) { Warn "$($p.name) is $([int](100 * $vram / $size))% on the GPU, the rest on the CPU. Answers will be slower." }
        else                    { Ok "$($p.name) is loaded on the GPU" }
    }
} catch { }   # informational only

# 8. Dashboard answers --------------------------------------------------------------
Info "Waiting for the dashboard at $Url"
$ready = $false
$deadline = (Get-Date).AddSeconds($DashboardTimeoutSec)
while ((Get-Date) -lt $deadline) {
    if ((Get-HttpCode "$Url/api/status") -eq 200) { $ready = $true; break }
    Start-Sleep -Seconds 5
}
if (-not $ready) {
    Show-Containers
    & $DockerCli logs --tail 20 hermes-dashboard 2>&1 | Out-Host
    Fail "The dashboard did not respond within $DashboardTimeoutSec seconds (see above)."
}
Ok 'Dashboard is responding'

# 9. Dashboard login works ----------------------------------------------------------
try {
    $body = @{ provider = 'basic'; username = $DashUser; password = $DashPass; next = '' } | ConvertTo-Json
    Invoke-WebRequest -Method Post -Uri "$Url/auth/password-login" -ContentType 'application/json' -Body $body `
        -SessionVariable dash -UseBasicParsing -TimeoutSec 15 | Out-Null
    Ok "Login works ($DashUser / $DashPass)"
} catch {
    $code = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 }
    switch ($code) {
        401     { Fail "The dashboard rejected $DashUser / $DashPass. The password in hermes_files/data/config.yaml does not match." }
        404     { Ok 'This dashboard has no login (nothing to check)' }
        429     { Warn 'Too many login attempts in the last minute, so the login check was skipped.' }
        default { Fail "Login check failed: $($_.Exception.Message)" }
    }
}

# 10. Open it -----------------------------------------------------------------------
Start-Process $Url
Write-Host ''
Write-Host 'Hermes is ready.' -ForegroundColor Green
Write-Host "If the page asks you to sign in, use $DashUser / $DashPass. Let the browser save it."
if (-not $NoPause) { Start-Sleep -Seconds 8 }
Done 0
'@

# ---------------------------------------------------------------- main
try {
    Write-Host "Local Hermes setup  |  distro: $DistroName  |  user: $LinuxUser" -ForegroundColor White

    # 1 ---------------------------------------------------------------
    Step 1 "Verifying WSL2"
    $wslReady = $false
    # SilentlyContinue = "wsl.exe not found" is a normal answer here
    if (Get-Command wsl.exe -ErrorAction SilentlyContinue) {
        wsl.exe --version *> $null
        if ($LASTEXITCODE -eq 0) { $wslReady = $true }
        else {
            wsl.exe --status *> $null
            if ($LASTEXITCODE -eq 0) { $wslReady = $true; Warn "This PC has an old WSL. If later steps fail, ask IT to run 'wsl --update'." }
        }
    }
    if (-not $wslReady) { throw "WSL is not installed on this PC. Installing it needs an admin: ask IT to run 'wsl --install --no-distribution' and restart the PC." }
    wsl.exe --set-default-version 2 *> $null
    Ok "WSL2 is installed"

    # 2 ---------------------------------------------------------------
    Step 2 "Setting WSL2 memory ($MemoryGB GB) and swap ($SwapGB GB)"
    $totalGB = [math]::Round((Get-CimInstance Win32_ComputerSystem -ErrorAction Stop).TotalPhysicalMemory / 1GB)
    if ($totalGB -le $MemoryGB + 4) {
        Warn "This PC has $totalGB GB of RAM. memory=${MemoryGB}GB leaves Windows almost nothing; WSL may fail to start or the PC may freeze."
    }
    $cfgPath = Join-Path $env:USERPROFILE ".wslconfig"
    $lines = New-Object System.Collections.Generic.List[string]
    if (Test-Path $cfgPath) {
        Copy-Item $cfgPath "$cfgPath.bak" -Force -ErrorAction Stop
        foreach ($l in (Get-Content $cfgPath -ErrorAction Stop)) { $lines.Add($l) }
    }
    Set-WslConfigKey $lines "memory" "${MemoryGB}GB"
    Set-WslConfigKey $lines "swap"   "${SwapGB}GB"
    Set-Content -Path $cfgPath -Value $lines -Encoding ASCII -ErrorAction Stop
    wsl.exe --shutdown
    Ok "memory=${MemoryGB}GB, swap=${SwapGB}GB written to $cfgPath (WSL restarted to apply it)"

    # 3 ---------------------------------------------------------------
    Step 3 "Creating $DistroName distro"
    if ((Get-Distros) -notcontains $DistroName) {
        wsl.exe --install -d $DistroName --no-launch
        if ((Get-Distros) -notcontains $DistroName) {
            # older Store-style distros need one registration run (Ubuntu -> ubuntu.exe)
            $distroExe = ($DistroName.ToLower() -replace '[^a-z0-9]', '') + ".exe"
            if (Get-Command $distroExe -ErrorAction SilentlyContinue) { & $distroExe install --root }
        }
        if ((Get-Distros) -notcontains $DistroName) { throw "Distro '$DistroName' did not register. Run 'wsl --install -d $DistroName' manually, then re-run." }
        Ok "$DistroName installed"
    } else {
        Ok "$DistroName already exists"
    }
    wsl.exe --set-version $DistroName 2 *> $null

    wsl.exe -d $DistroName -u root -- id -u $LinuxUser *> $null
    if ($LASTEXITCODE -ne 0) {
        Invoke-Linux -AsRoot "useradd -m -s /bin/bash -G sudo $LinuxUser" | Out-Null
    }
    Invoke-Linux -AsRoot "echo '${LinuxUser}:${LinuxPassword}' | chpasswd" | Out-Null
    Invoke-Linux -AsRoot "groupadd -f docker && usermod -aG docker $LinuxUser" | Out-Null
    Invoke-Linux -AsRoot "printf '[boot]\nsystemd=true\n\n[user]\ndefault=$LinuxUser\n' > /etc/wsl.conf" | Out-Null
    wsl.exe --manage $DistroName --set-default-user $LinuxUser *> $null   # newer WSL only, harmless otherwise
    wsl.exe --terminate $DistroName *> $null                              # reload wsl.conf + docker group
    Ok "User '$LinuxUser' ready (password: $LinuxPassword, sudo + docker groups)"

    # 4 ---------------------------------------------------------------
    Step 4 "apt update / upgrade"
    Invoke-Linux -AsRoot "export DEBIAN_FRONTEND=noninteractive; apt-get update && apt-get -y upgrade" | Out-Null
    Ok "Packages up to date"

    # 5 ---------------------------------------------------------------
    Step 5 "apt install gedit htop"
    Invoke-Linux -AsRoot "export DEBIAN_FRONTEND=noninteractive; apt-get install -y gedit htop git ca-certificates" | Out-Null
    Ok "gedit, htop, git installed"

    # 6 ---------------------------------------------------------------
    Step 6 "git clone local_hermes"
    Invoke-Linux "if [ -d ~/$RepoFolder/.git ]; then cd ~/$RepoFolder && git pull --ff-only; else git clone $RepoUrl ~/$RepoFolder; fi" | Out-Null
    Ok "Repo at /home/$LinuxUser/$RepoFolder"

    # 7 ---------------------------------------------------------------
    Step 7 "git submodule update --init --recursive"
    Invoke-Linux "cd ~/$RepoFolder && git submodule update --init --recursive && mkdir -p ollama_storage" | Out-Null
    Ok "Submodules pulled, ollama_storage folder created"

    # 8 ---------------------------------------------------------------
    Step 8 "Verifying Docker Desktop"
    if (-not (Test-Path $DockerExe)) { throw "Docker Desktop is not installed on this PC. Installing it needs an admin, so ask IT." }
    $mySession = [System.Diagnostics.Process]::GetCurrentProcess().SessionId
    $others = Get-Process -Name "Docker Desktop", "com.docker.backend" -ErrorAction SilentlyContinue |
        Where-Object { $_.SessionId -ne $mySession }
    if ($others) { throw "Docker is still running under another profile on this PC. Restart the computer (Start > Power > Restart), sign back in, and run setup again." }
    $inDockerUsers = [bool]((whoami /groups) -match '\\docker-users\b')
    if (-not $inDockerUsers) { Warn "Your account is not in the 'docker-users' group. Docker may refuse to start." }
    if (-not (Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue)) {
        Info "Starting Docker Desktop. First time on this profile: click Accept if a Docker agreement window appears."
    }
    if (-not (Start-DockerDesktop)) {
        if (-not $inDockerUsers) { throw "Docker did not start. Ask IT to add you to docker-users:  net localgroup docker-users `"$env:USERDOMAIN\$env:USERNAME`" /add   then sign out and back in, and run setup again." }
        throw "Docker did not start within $DockerTimeoutSec s. Open Docker Desktop, accept any prompt or read its error, then run setup again."
    }
    if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
        Warn "nvidia-smi not found. Ollama uses 'gpus: all' and will fail without an NVIDIA GPU and driver."
    }
    Ok "Docker Desktop is installed and running"

    # 9 ---------------------------------------------------------------
    Step 9 "Docker Desktop WSL integration for $DistroName"
    $settingsPath = @("$env:APPDATA\Docker\settings-store.json", "$env:APPDATA\Docker\settings.json") |
        Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $settingsPath) { throw "Docker settings file not found in $env:APPDATA\Docker. Open Docker Desktop once, then re-run." }
    $pascal = $settingsPath -like "*settings-store.json"

    $settings = Get-Content $settingsPath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
    $kDistros = if ($pascal) { "IntegratedWslDistros" } else { "integratedWslDistros" }
    $kEngine  = if ($pascal) { "WslEngineEnabled" }     else { "wslEngineEnabled" }
    $current  = @($settings.PSObject.Properties | Where-Object { $_.Name -ieq $kDistros } | ForEach-Object { $_.Value }) | Where-Object { $_ }
    $engineOn = ($settings.PSObject.Properties | Where-Object { $_.Name -ieq $kEngine } | ForEach-Object { $_.Value }) -eq $true

    if (($current -contains $DistroName) -and $engineOn) {
        Ok "Already enabled"
    } else {
        Stop-DockerDesktop   # Docker overwrites its settings file on exit, so edit while it is stopped
        $settings = Get-Content $settingsPath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
        Copy-Item $settingsPath "$settingsPath.bak" -Force -ErrorAction Stop
        Set-JsonProp $settings $kEngine $true
        Set-JsonProp $settings $kDistros ([string[]]@(@($current) + $DistroName | Select-Object -Unique))
        $json = $settings | ConvertTo-Json -Depth 50
        [System.IO.File]::WriteAllText($settingsPath, $json, (New-Object System.Text.UTF8Encoding($false)))
        if (-not (Start-DockerDesktop)) { throw "Docker did not restart after enabling WSL integration." }
        Ok "Integration enabled (backup: $settingsPath.bak)"
    }

    $ok = $false
    for ($i = 0; $i -lt 24; $i++) {
        if ((Invoke-Linux "docker info > /dev/null 2>&1" -AllowFail) -eq 0) { $ok = $true; break }
        Start-Sleep -Seconds 5
    }
    if (-not $ok) { throw "docker is not reachable inside $DistroName. In Docker Desktop: Settings > Resources > WSL integration > turn on $DistroName, then re-run." }
    Ok "docker works inside $DistroName"

    # pre-flight: make sure every compose include/build path exists
    if ((Invoke-Linux "cd ~/$RepoFolder && docker compose config -q" -AllowFail) -ne 0) {
        throw "docker compose config failed (see error above). Usually a folder in the 'include:' list or a build context is missing from the repo."
    }

    # 10 --------------------------------------------------------------
    Step 10 "docker compose pull"
    if ((Invoke-Linux "cd ~/$RepoFolder && docker compose pull --ignore-pull-failures" -AllowFail) -ne 0) {
        Warn "Some images did not pull (normal for locally built services). Continuing."
    } else { Ok "Images pulled" }

    # 11 --------------------------------------------------------------
    Step 11 "docker compose build"
    Invoke-Linux "cd ~/$RepoFolder && docker compose build" | Out-Null
    Ok "Images built"

    # 12 --------------------------------------------------------------
    Step 12 "docker compose up -d"
    Invoke-Linux "cd ~/$RepoFolder && docker compose up -d" | Out-Null
    Ok "Containers started"

    # 13 --------------------------------------------------------------
    Step 13 "Creating the Hermes desktop shortcut"
    $launcherDir  = Join-Path $env:LOCALAPPDATA "LocalHermes"
    $launcherPath = Join-Path $launcherDir "Start-Hermes.ps1"
    New-Item -ItemType Directory -Path $launcherDir -Force -ErrorAction Stop | Out-Null
    $q = { param($v) $v.Replace("'", "''") }   # escape for single-quoted PowerShell strings
    $launcher = $LauncherTemplate.
        Replace('__DISTRO__',    (& $q $DistroName)).
        Replace('__USER__',      (& $q $LinuxUser)).
        Replace('__REPO__',      (& $q $RepoFolder)).
        Replace('__URL__',       (& $q $DashboardUrl)).
        Replace('__DASHUSER__',  (& $q $DashboardUser)).
        Replace('__DASHPASS__',  (& $q $DashboardPassword)).
        Replace('__DOCKEREXE__', (& $q $DockerExe)).
        Replace('__DOCKERCLI__', (& $q $DockerCli))
    Set-Content -Path $launcherPath -Value $launcher -Encoding ASCII -ErrorAction Stop

    # The shortcut loads the launcher as text (same trick as the .cmd), so a school script
    # policy cannot block it the way it could block "-File Start-Hermes.ps1".
    try {
        $desktop = [Environment]::GetFolderPath("Desktop")
        $shell   = New-Object -ComObject WScript.Shell
        $lnk     = $shell.CreateShortcut((Join-Path $desktop "Hermes.lnk"))
        $lnk.TargetPath   = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
        $lnk.Arguments    = "-NoProfile -ExecutionPolicy Bypass -Command `"& ([scriptblock]::Create([IO.File]::ReadAllText('$(& $q $launcherPath)')))`""
        $lnk.IconLocation = "$DockerExe,0"
        $lnk.Description  = "Start Local Hermes and open the dashboard"
        $lnk.Save()
        Ok "Desktop shortcut 'Hermes' created"
    } catch {
        Warn "Could not create the desktop shortcut: $($_.Exception.Message)"
    }

    # 14 --------------------------------------------------------------
    Step 14 "Verifying Hermes and opening the dashboard"
    # Runs the exact same checks as the desktop shortcut, with a longer wait for the first model download.
    $env:HERMES_LAUNCHER = $launcherPath
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& ([scriptblock]::Create([IO.File]::ReadAllText(`$env:HERMES_LAUNCHER))) -ModelTimeoutMin $ModelTimeoutMin -DashboardTimeoutSec 300 -NoPause"
    if ($LASTEXITCODE -ne 0) {
        throw "Hermes did not pass the startup checks (see the red message above). Fix that, then double-click the Hermes shortcut. Setup does not need to run again."
    }

    Write-Host "`nSetup complete." -ForegroundColor Green
    Write-Host "  Next time  : double-click 'Hermes' on your desktop"
    Write-Host "  Dashboard  : $DashboardUrl   (sign in: $DashboardUser / $DashboardPassword)"
    Write-Host "  Browser VNC: http://127.0.0.1:6080/vnc.html"
    Write-Host "  Repo       : \\wsl$\$DistroName\home\$LinuxUser\$RepoFolder"
    Write-Host "  Shell      : wsl -d $DistroName   then   docker exec -it -u 1000:1000 hermes /bin/bash"
    Write-Host "  Log        : $logPath"
    Write-Host "  When done  : SIGN OUT of Windows (do not just close Remote Desktop)" -ForegroundColor Yellow
}
catch {
    Write-Host "`n  XX   $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "       Fix the issue above and re-run. Finished steps will be skipped." -ForegroundColor Red
    try { Stop-Transcript | Out-Null } catch {}
    Read-Host "Press Enter to exit"
    exit 1
}

try { Stop-Transcript | Out-Null } catch {}
Read-Host "Press Enter to exit"