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
    One-shot setup for Local Hermes on Windows: WSL2 + Ubuntu + Docker Desktop + docker compose stack.

.DESCRIPTION
    Steps:
      1.  Verify WSL2 is installed (installs it if missing, then asks for a reboot)
      2.  Set WSL2 memory (55 GB) and swap (8 GB) in %USERPROFILE%\.wslconfig
      3.  Create the Ubuntu distro and a Linux user (password = "password")
      4.  apt update / upgrade
      5.  apt install gedit htop git
      6.  git clone local_hermes
      7.  git submodule update --init --recursive
      8.  Verify Docker Desktop is installed and running
      9.  Turn on Docker Desktop WSL integration for the distro
      10. docker compose pull
      11. docker compose build
      12. docker compose up -d
      13. Create a "Hermes" desktop shortcut and open the dashboard in the browser

    Safe to re-run: every step checks what is already done and skips it.
    Shared PCs: each Windows user who runs this gets their OWN Ubuntu, repo and containers.
    The Linux username defaults to the Windows username (lowercase).
    Runs as the CURRENT user on purpose. WSL distros, .wslconfig and Docker settings
    are per-user, so only the WSL feature install asks for admin.

HOW TO USE
    Double-click Setup-LocalHermes.cmd. That is it: this one file is the whole setup.
    Each person runs it while signed in to their own Windows profile.
    Afterwards, use the "Hermes" desktop shortcut to start Hermes after each sign-in.
    To change settings, edit the default values in the param() block below.
#>
[CmdletBinding()]
param(
    [string]$DistroName          = "Ubuntu",
    [string]$LinuxUser           = "",     # "" = Windows username, lowercase
    [string]$LinuxPassword       = "password",
    [int]   $MemoryGB            = 55,
    [int]   $SwapGB              = 8,
    [string]$RepoUrl             = "https://github.com/antmedellin/local_hermes.git",
    [string]$RepoFolder          = "local_hermes",
    [string]$DashboardUrl        = "http://localhost:9119",
    [int]   $DockerTimeoutSec    = 300,
    [int]   $DashboardTimeoutSec = 900
)

$ErrorActionPreference = "Continue"   # native tools are checked via $LASTEXITCODE
$env:WSL_UTF8 = "1"                   # makes wsl.exe print UTF-8 instead of UTF-16
$TotalSteps = 13

if (-not $LinuxUser) {
    $LinuxUser = ($env:USERNAME.ToLower() -replace '[^a-z0-9_-]', '')
    if ($LinuxUser -notmatch '^[a-z_][a-z0-9_-]{0,31}$') { $LinuxUser = "hermes" }
}

$setupDir = if ($env:HERMES_SETUP_DIR) { $env:HERMES_SETUP_DIR } else { $env:USERPROFILE }
$logPath = Join-Path $setupDir "setup-localhermes.log"
try { Start-Transcript -Path $logPath -Append | Out-Null } catch {}

# ---------------------------------------------------------------- helpers
function Step([int]$n, [string]$msg) { Write-Host "`n[$n/$TotalSteps] $msg" -ForegroundColor Cyan }
function Ok([string]$msg)            { Write-Host "  OK   $msg" -ForegroundColor Green }
function Warn([string]$msg)          { Write-Host "  !!   $msg" -ForegroundColor Yellow }

function Get-Distros {
    (wsl.exe --list --quiet 2>$null) -replace "`0", "" |
        ForEach-Object { $_.Trim() } | Where-Object { $_ }
}

# Runs a bash command inside the distro. Use single quotes inside $Command (never double quotes).
function Invoke-Linux {
    param([Parameter(Mandatory)][string]$Command, [switch]$AsRoot, [switch]$AllowFail)
    $user = if ($AsRoot) { "root" } else { $LinuxUser }
    wsl.exe -d $DistroName -u $user -- bash -lc $Command
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
    Get-Process -Name "Docker Desktop", "com.docker.backend", "com.docker.build" -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 8
}

# ---------------------------------------------------------------- main
try {
    Write-Host "Local Hermes setup  |  distro: $DistroName  |  user: $LinuxUser" -ForegroundColor White

    # 1 ---------------------------------------------------------------
    Step 1 "Verifying WSL2"
    $wslReady = $false
    if (Get-Command wsl.exe -ErrorAction SilentlyContinue) {
        wsl.exe --status *> $null
        if ($LASTEXITCODE -eq 0) { $wslReady = $true }
    }
    if (-not $wslReady) {
        Warn "WSL is not installed. Installing now (an admin prompt will appear)..."
        Start-Process wsl.exe -ArgumentList "--install", "--no-distribution" -Verb RunAs -Wait
        Warn "WSL installed. REBOOT Windows, then run this script again."
        Read-Host "Press Enter to exit"
        exit 0
    }
    wsl.exe --version *> $null
    if ($LASTEXITCODE -ne 0) {
        Warn "Old inbox WSL detected. Updating to the current WSL (admin prompt)..."
        Start-Process wsl.exe -ArgumentList "--update" -Verb RunAs -Wait
    }
    wsl.exe --set-default-version 2 *> $null
    Ok "WSL2 is installed"

    # 2 ---------------------------------------------------------------
    Step 2 "Setting WSL2 memory ($MemoryGB GB) and swap ($SwapGB GB)"
    $totalGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
    if ($totalGB -le $MemoryGB + 4) {
        Warn "This PC has $totalGB GB of RAM. memory=${MemoryGB}GB leaves Windows almost nothing; WSL may fail to start or the PC may freeze."
    }
    $cfgPath = Join-Path $env:USERPROFILE ".wslconfig"
    $lines = New-Object System.Collections.Generic.List[string]
    if (Test-Path $cfgPath) {
        Copy-Item $cfgPath "$cfgPath.bak" -Force
        foreach ($l in (Get-Content $cfgPath)) { $lines.Add($l) }
    }
    Set-WslConfigKey $lines "memory" "${MemoryGB}GB"
    Set-WslConfigKey $lines "swap"   "${SwapGB}GB"
    Set-Content -Path $cfgPath -Value $lines -Encoding ASCII
    wsl.exe --shutdown
    Ok "memory=${MemoryGB}GB, swap=${SwapGB}GB written to $cfgPath (WSL restarted to apply it)"

    # 3 ---------------------------------------------------------------
    Step 3 "Creating $DistroName distro"
    if ((Get-Distros) -notcontains $DistroName) {
        wsl.exe --install -d $DistroName --no-launch
        if ((Get-Distros) -notcontains $DistroName) {
            # older Store-style distros need one registration run (Ubuntu -> ubuntu.exe, Ubuntu-24.04 -> ubuntu2404.exe)
            $launcher = ($DistroName.ToLower() -replace '[^a-z0-9]', '') + ".exe"
            if (Get-Command $launcher -ErrorAction SilentlyContinue) { & $launcher install --root }
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
    if (-not (Test-Path $DockerExe)) {
        Warn "Docker Desktop not found. Installing with winget (admin prompt)..."
        winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
        if (-not (Test-Path $DockerExe)) { throw "Docker Desktop install failed. Install it manually, then re-run." }
        Warn "Docker Desktop installed. If it will not start, sign out and back in (docker-users group), then re-run."
    }
    $mySession = [System.Diagnostics.Process]::GetCurrentProcess().SessionId
    $others = Get-Process -Name "Docker Desktop", "com.docker.backend" -ErrorAction SilentlyContinue |
        Where-Object { $_.SessionId -ne $mySession }
    if ($others) {
        Warn "Another user's session on this PC is still running Docker Desktop."
        Warn "This usually means someone closed Remote Desktop without SIGNING OUT, so their session is still open in the background."
        Warn "Both Hermes stacks need ports 9119, 11434 and 6080, so only one can run at a time."
        $ans = Read-Host "  Ask them to sign in and SIGN OUT (or ask IT to log off their session), then press Enter (or type Q to stop)"
        if ($ans -match '^[Qq]') { throw "Stopped: another user is running Docker Desktop on this PC." }
    }
    if (-not (Start-DockerDesktop)) { throw "Docker engine did not come up within $DockerTimeoutSec s. Open Docker Desktop, finish any first-run prompts, then re-run." }
    if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
        Warn "nvidia-smi not found. The compose file uses 'gpus: all' for Ollama; it will fail without an NVIDIA GPU + driver."
    }
    Ok "Docker Desktop installed and running"

    # 9 ---------------------------------------------------------------
    Step 9 "Docker Desktop WSL integration for $DistroName"
    $settingsPath = @("$env:APPDATA\Docker\settings-store.json", "$env:APPDATA\Docker\settings.json") |
        Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $settingsPath) { throw "Docker settings file not found in $env:APPDATA\Docker. Open Docker Desktop once, then re-run." }
    $pascal = $settingsPath -like "*settings-store.json"

    $settings = Get-Content $settingsPath -Raw | ConvertFrom-Json
    $kDistros = if ($pascal) { "IntegratedWslDistros" } else { "integratedWslDistros" }
    $kEngine  = if ($pascal) { "WslEngineEnabled" }     else { "wslEngineEnabled" }
    $current  = @($settings.PSObject.Properties | Where-Object { $_.Name -ieq $kDistros } | ForEach-Object { $_.Value }) | Where-Object { $_ }
    $engineOn = ($settings.PSObject.Properties | Where-Object { $_.Name -ieq $kEngine } | ForEach-Object { $_.Value }) -eq $true

    if (($current -contains $DistroName) -and $engineOn) {
        Ok "Already enabled"
    } else {
        Stop-DockerDesktop   # Docker overwrites its settings file on exit, so edit while it is stopped
        $settings = Get-Content $settingsPath -Raw | ConvertFrom-Json
        Copy-Item $settingsPath "$settingsPath.bak" -Force
        Set-JsonProp $settings $kEngine $true
        Set-JsonProp $settings $kDistros ([string[]]@(@($current) + $DistroName | Select-Object -Unique))
        $json = $settings | ConvertTo-Json -Depth 50
        [System.IO.File]::WriteAllText($settingsPath, $json, (New-Object System.Text.UTF8Encoding($false)))
        if (-not (Start-DockerDesktop)) { throw "Docker did not restart after enabling WSL integration." }
        Ok "Integration enabled (backup: $settingsPath.bak)"
    }

    # confirm docker works from inside the distro
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
    Invoke-Linux "cd ~/$RepoFolder && docker compose ps" -AllowFail | Out-Null
    Ok "Stack started"

    # 13 --------------------------------------------------------------
    Step 13 "Creating Hermes desktop shortcut and opening the dashboard"
    try {
        $launcherDir  = Join-Path $env:LOCALAPPDATA "LocalHermes"
        $launcherPath = Join-Path $launcherDir "Start-Hermes.ps1"
        New-Item -ItemType Directory -Path $launcherDir -Force | Out-Null
        $launcher = @"
# Created by Setup-LocalHermes.cmd. Starts Docker Desktop, brings the Hermes stack up, opens the dashboard.
Write-Host 'Starting Hermes...'
if (-not (Get-Process -Name 'Docker Desktop' -ErrorAction SilentlyContinue)) { Start-Process -FilePath '$DockerExe' }
for (`$i = 0; `$i -lt 60; `$i++) { & '$DockerCli' info *> `$null; if (`$LASTEXITCODE -eq 0) { break }; Start-Sleep -Seconds 5 }
for (`$i = 0; `$i -lt 12; `$i++) {
    wsl.exe -d $DistroName -u $LinuxUser -- bash -lc 'cd ~/$RepoFolder && docker compose up -d'
    if (`$LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 5
}
Start-Process '$DashboardUrl'
"@
        Set-Content -Path $launcherPath -Value $launcher -Encoding ASCII
        $desktop = [Environment]::GetFolderPath("Desktop")
        $shell   = New-Object -ComObject WScript.Shell
        $lnk     = $shell.CreateShortcut((Join-Path $desktop "Hermes.lnk"))
        $lnk.TargetPath   = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
        $lnk.Arguments    = "-NoProfile -ExecutionPolicy Bypass -File `"$launcherPath`""
        $lnk.IconLocation = "$DockerExe,0"
        $lnk.Description  = "Start Local Hermes and open the dashboard"
        $lnk.Save()
        Ok "Desktop shortcut 'Hermes' created (use it after each sign-in)"
    } catch {
        Warn "Could not create the desktop shortcut: $($_.Exception.Message)"
    }

    Write-Host "  ..   waiting for $DashboardUrl (first run can take a while: Ollama is pulling models)"
    $up = $false
    $deadline = (Get-Date).AddSeconds($DashboardTimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            Invoke-WebRequest -Uri $DashboardUrl -UseBasicParsing -TimeoutSec 5 | Out-Null
            $up = $true; break
        } catch {
            if ($_.Exception.Response) { $up = $true; break }   # any HTTP reply (401, 302...) means it is up
        }
        Start-Sleep -Seconds 5
    }
    if (-not $up) { Warn "Dashboard did not answer within $DashboardTimeoutSec s. Opening it anyway; refresh in a minute." }
    Start-Process $DashboardUrl
    Ok "Browser opened"

    Write-Host "`nDone." -ForegroundColor Green
    Write-Host "  Next time : double-click 'Hermes' on your desktop"
    Write-Host "  Dashboard : $DashboardUrl   (login admin / password)"
    Write-Host "  Browser VNC: http://127.0.0.1:6080/vnc.html"
    Write-Host "  Repo      : \\wsl$\$DistroName\home\$LinuxUser\$RepoFolder"
    Write-Host "  Shell     : wsl -d $DistroName   then   docker exec -it -u 1000:1000 hermes /bin/bash"
    Write-Host "  Log       : $logPath"
    Write-Host "  When done : SIGN OUT of Windows (do not just close Remote Desktop)" -ForegroundColor Yellow
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