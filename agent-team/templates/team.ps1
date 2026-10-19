# Start the development team on Windows, installing missing dependencies.
# Usage: .\team.ps1 ["task request"]
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = $PSScriptRoot
$env:TEAM_CONFIG = Join-Path $projectRoot 'team.toml'
$defaultLogoutRoot = '@@LOGOUT_AI_ROOT@@'
$logoutRoot = if ($env:LOGOUT_AI_ROOT) { $env:LOGOUT_AI_ROOT } else { $defaultLogoutRoot }
$userBin = Join-Path $HOME '.local/bin'
# Official Zellij v0.45.1 x86_64 Windows release asset SHA-256 digest, pinned at implementation.
$zellijUrl = 'https://github.com/zellij-org/zellij/releases/download/v0.45.1/zellij-x86_64-pc-windows-msvc.zip'
$zellijSha256 = 'b854e7b223e67d0705c5f685ef50541c38a57981b13624d09c92bed419b6f80d'

function Fail {
    param([string] $Message)

    [Console]::Error.WriteLine("team.ps1: $Message")
    exit 1
}

function Update-SessionPath {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = (@($userBin, $user, $machine, $env:Path) | Where-Object { $_ }) -join [System.IO.Path]::PathSeparator
}

function Test-OnPath {
    param([string] $Name)

    [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

# The Microsoft Store python/python3 aliases exist on PATH but do not run, so each candidate is tried.
function Find-Python {
    foreach ($candidate in @(@('py', '-3'), @('python'), @('python3'))) {
        if (-not (Get-Command $candidate[0] -CommandType Application -ErrorAction SilentlyContinue)) {
            continue
        }
        $arguments = @($candidate | Select-Object -Skip 1) + @(
            '-c', 'import sys; print(sys.executable) if sys.version_info >= (3, 11) else sys.exit(1)')
        $executable = & $candidate[0] @arguments 2>$null
        if ($LASTEXITCODE -eq 0 -and $executable) {
            return ([string]$executable).Trim()
        }
    }
    return $null
}

function Install-WingetPackage {
    param([string] $Id)

    if (-not (Test-OnPath 'winget')) {
        Fail "winget is required to install $Id. Install it manually and retry."
    }
    Write-Output "Installing missing dependency with winget: $Id"
    & winget install --id $Id --exact --source winget --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        Fail "winget could not install $Id (exit $LASTEXITCODE)."
    }
    Update-SessionPath
}

if ($args.Count -gt 0 -and $args[0] -in @('--help', '-h', '-Help')) {
    Write-Output "Usage: .\team.ps1 [`"task request`"]"
    Write-Output 'Starts the dashboard; a request starts a team task instead.'
    Write-Output 'Missing dependencies are installed automatically (winget may prompt for elevation).'
    exit 0
}
if ($PSVersionTable.PSEdition -eq 'Core' -and -not $IsWindows) {
    Fail 'Run this script on Windows; use team.sh on Linux or WSL.'
}
if (-not (Test-Path -LiteralPath $env:TEAM_CONFIG -PathType Leaf)) {
    Fail "Missing config: $env:TEAM_CONFIG"
}
if (-not (Test-Path -LiteralPath (Join-Path $logoutRoot 'agent-team/bin/team-up') -PathType Leaf)) {
    Fail 'Logout AI checkout missing. Set LOGOUT_AI_ROOT to its location.'
}
$env:Path = $userBin + [System.IO.Path]::PathSeparator + $env:Path

$python = Find-Python
if (-not $python) {
    Install-WingetPackage 'Python.Python.3.13'
    $python = Find-Python
    if (-not $python) {
        Fail 'Python 3.11+ is required. Installation did not provide it on PATH.'
    }
}
if (-not (Test-OnPath 'git')) {
    # Git for Windows also provides Git Bash, which Claude Code uses for shell commands.
    Install-WingetPackage 'Git.Git'
}
& git --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    Fail 'Git is not working.'
}

if (-not (Test-OnPath 'zellij')) {
    if ($env:PROCESSOR_ARCHITECTURE -notin @('AMD64', 'ARM64')) {
        Fail 'Automatic Zellij installation supports x64 Windows (ARM64 runs it under emulation).'
    }
    $temporary = Join-Path ([System.IO.Path]::GetTempPath()) "agent-team-zellij-$([guid]::NewGuid())"
    New-Item -ItemType Directory -Path $temporary | Out-Null
    try {
        Write-Output 'Installing Zellij 0.45.1 from its verified upstream release for this user.'
        $archive = Join-Path $temporary 'zellij.zip'
        Invoke-WebRequest -Uri $zellijUrl -OutFile $archive -UseBasicParsing -TimeoutSec 180
        $actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $zellijSha256) {
            Fail "Zellij download checksum mismatch ($actual)."
        }
        Expand-Archive -LiteralPath $archive -DestinationPath $temporary
        New-Item -ItemType Directory -Path $userBin -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $temporary 'zellij.exe') -Destination (Join-Path $userBin 'zellij.exe')
    }
    finally {
        Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$readClis = 'import sys; sys.path.insert(0, sys.argv[1]); import teamcfg; ' +
    'print("\n".join(sorted({r["cli"] for r in teamcfg.load(sys.argv[2])["roles"].values()})))'
$agentClis = @(& $python -I -B -c $readClis (Join-Path $logoutRoot 'agent-team') $env:TEAM_CONFIG)
if ($LASTEXITCODE -ne 0) {
    Fail "Could not read $env:TEAM_CONFIG"
}
foreach ($cli in $agentClis) {
    if (Test-OnPath $cli) {
        continue
    }
    $package = switch ($cli) {
        'codex' { '@openai/codex' }
        'claude' { '@anthropic-ai/claude-code' }
        default { Fail "Unsupported agent CLI: $cli" }
    }
    if (-not (Test-OnPath 'npm') -or -not (Test-OnPath 'node')) {
        Install-WingetPackage 'OpenJS.NodeJS.LTS'
    }
    Write-Output "Installing missing agent CLI for this user: $cli"
    & npm install --global $package
    if ($LASTEXITCODE -ne 0) {
        Fail "npm could not install $package (exit $LASTEXITCODE)."
    }
    Update-SessionPath
    if (-not (Test-OnPath $cli)) {
        Fail "Installation did not provide $cli on PATH."
    }
}

foreach ($dependency in @('git', 'zellij')) {
    if (-not (Test-OnPath $dependency)) {
        Fail "Installation did not provide $dependency on PATH."
    }
}
Set-Location -LiteralPath $projectRoot
& $python -X utf8 (Join-Path $logoutRoot 'agent-team/bin/team-up') @args
exit $LASTEXITCODE
