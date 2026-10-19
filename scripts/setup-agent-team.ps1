[CmdletBinding()]
param(
    [Parameter(Mandatory, Position = 0)]
    [string] $TargetPath,

    [Alias('dry-run')]
    [switch] $DryRun,

    [string] $BinDir = (Join-Path $HOME '.local/bin'),

    [ValidateSet('claude', 'codex', 'both')]
    [string] $Agents = '',

    [ValidateSet('git', 'p4')]
    [string] $Vcs = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$teamRoot = Join-Path $repoRoot 'agent-team'
$script:addedCount = 0
$script:skippedCount = 0

function Get-ExistingItem {
    param(
        [Parameter(Mandatory)]
        [string] $LiteralPath
    )

    Get-Item -LiteralPath $LiteralPath -Force -ErrorAction SilentlyContinue
}

function Ensure-Directory {
    param(
        [Parameter(Mandatory)]
        [string] $LiteralPath
    )

    $existing = Get-ExistingItem -LiteralPath $LiteralPath
    if ($existing) {
        if (-not $existing.PSIsContainer) {
            throw "Path exists and is not a directory: $LiteralPath"
        }
        return
    }

    if ($DryRun) {
        Write-Output "+ New-Item -ItemType Directory -Path '$LiteralPath'"
    }
    else {
        New-Item -ItemType Directory -Path $LiteralPath -Force | Out-Null
    }
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

function Test-OnPath {
    param(
        [Parameter(Mandatory)]
        [string] $Name
    )

    [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-DetectedAgents {
    $hasClaude = Test-OnPath 'claude'
    $hasCodex = Test-OnPath 'codex'
    if ($hasClaude -and $hasCodex) { return 'both' }
    if ($hasCodex) { return 'codex' }
    return 'claude'
}

function Read-Agents {
    $default = Get-DetectedAgents
    if ([Console]::IsInputRedirected -or -not [Environment]::UserInteractive) {
        Write-Host "agents: $default (detected on PATH; pass -Agents to choose)"
        return $default
    }

    Write-Host 'Which agent CLIs should the team use?'
    Write-Host '  1) claude  Claude Code for every role'
    Write-Host '  2) codex   Codex CLI for every role'
    Write-Host '  3) both    mixed roles: Claude and Codex review each other'
    while ($true) {
        $reply = Read-Host "Choice [$default]"
        if (-not $reply) { $reply = $default }
        switch ($reply) {
            { $_ -in '1', 'claude' } { return 'claude' }
            { $_ -in '2', 'codex' } { return 'codex' }
            { $_ -in '3', 'both' } { return 'both' }
        }
        Write-Host 'enter 1, 2, 3, claude, codex or both'
    }
}

# git for an existing git repository, else Perforce when p4 is installed, else git.
function Get-DetectedVcs {
    param(
        [Parameter(Mandatory)]
        [string] $ProjectPath
    )

    if ((Test-OnPath 'git') -and (Test-Path -LiteralPath $ProjectPath -PathType Container)) {
        & git -C $ProjectPath rev-parse --git-dir 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { return 'git' }
    }
    if (Test-OnPath 'p4') { return 'p4' }
    return 'git'
}

function Read-Vcs {
    param(
        [Parameter(Mandatory)]
        [string] $ProjectPath
    )

    $default = Get-DetectedVcs -ProjectPath $ProjectPath
    if ([Console]::IsInputRedirected -or -not [Environment]::UserInteractive) {
        Write-Host "vcs: $default (detected; pass -Vcs to choose)"
        return $default
    }

    Write-Host 'Which version control does the project use?'
    Write-Host '  1) git  tasks share the working tree; agents never stage or commit'
    Write-Host '  2) p4   Perforce: each task gets its own changelist; agents never submit'
    while ($true) {
        $reply = Read-Host "Choice [$default]"
        if (-not $reply) { $reply = $default }
        switch ($reply) {
            { $_ -in '1', 'git' } { return 'git' }
            { $_ -in '2', 'p4', 'perforce' } { return 'p4' }
        }
        Write-Host 'enter 1, 2, git or p4'
    }
}

# Writes a generated launcher unless the path exists; Windows symlinks need Developer Mode or admin rights.
function Write-MissingFile {
    param(
        [Parameter(Mandatory)]
        [string] $Destination,

        [Parameter(Mandatory)]
        [string] $Content,

        [Parameter(Mandatory)]
        [string] $Description
    )

    $existing = Get-ExistingItem -LiteralPath $Destination
    if ($existing) {
        if (-not $existing.PSIsContainer -and [System.IO.File]::ReadAllText($Destination) -eq $Content) {
            Write-Output "kept existing: $Destination"
        }
        else {
            Write-Output "kept existing (different content): $Destination"
        }
        $script:skippedCount++
        return
    }

    Ensure-Directory -LiteralPath (Split-Path -Parent $Destination)
    if ($DryRun) {
        Write-Output "+ write '$Destination' ($Description)"
    }
    else {
        [System.IO.File]::WriteAllText($Destination, $Content)
    }
    Write-Output "added: $Destination"
    $script:addedCount++
}

# Keeps the state dir out of `git add -A` when the project is already a git repository.
$script:stateExcluded = $false
function Add-StateDirExclude {
    param(
        [Parameter(Mandatory)]
        [string] $ProjectPath
    )

    if (-not (Test-OnPath 'git') -or -not (Test-Path -LiteralPath $ProjectPath -PathType Container)) {
        return
    }
    & git -C $ProjectPath rev-parse --git-dir 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        return
    }
    $script:stateExcluded = $true
    $exclude = [System.IO.Path]::GetFullPath((& git -C $ProjectPath rev-parse --path-format=absolute --git-path info/exclude))
    $pattern = "/$(& git -C $ProjectPath rev-parse --show-prefix).agent-team/"
    if ((Test-Path -LiteralPath $exclude -PathType Leaf) -and
        ([System.IO.File]::ReadAllLines($exclude) | Where-Object { $_.TrimEnd("`r") -ceq $pattern })) {
        Write-Output "kept existing: $pattern in $exclude"
        $script:skippedCount++
        return
    }
    if ($DryRun) {
        Write-Output "+ append $pattern to '$exclude'"
    }
    else {
        New-Item -ItemType Directory -Path (Split-Path -Parent $exclude) -Force | Out-Null
        [System.IO.File]::AppendAllText($exclude, "$pattern`n")
    }
    Write-Output "added: $pattern to $exclude"
    $script:addedCount++
}

if ($TargetPath -match '[\x00-\x1F\x7F]') {
    throw 'Project path contains unsupported control characters.'
}
if (-not (Test-Path -LiteralPath (Join-Path $teamRoot 'templates/team.toml') -PathType Leaf)) {
    throw "Agent team templates do not exist: $(Join-Path $teamRoot 'templates')"
}
$python = Find-Python
if (-not $python) {
    throw 'Python 3.11 or newer is required (tomllib). Install it, for example: winget install Python.Python.3.13'
}

$targetFullPath = [System.IO.Path]::GetFullPath($TargetPath)
$existingTarget = Get-ExistingItem -LiteralPath $targetFullPath
if ($existingTarget -and -not $existingTarget.PSIsContainer) {
    throw "Project path exists and is not a directory: $targetFullPath"
}
if ($existingTarget -and $targetFullPath.TrimEnd('\', '/') -eq $repoRoot.TrimEnd('\', '/')) {
    throw 'Project path cannot be the Logout AI repository.'
}
$BinDir = [System.IO.Path]::GetFullPath($BinDir)

Ensure-Directory -LiteralPath $targetFullPath

$config = Join-Path $targetFullPath 'team.toml'
if (Get-ExistingItem -LiteralPath $config) {
    Write-Output "kept existing: $config"
    $script:skippedCount++
}
else {
    $projectName = (Split-Path -Leaf $targetFullPath.TrimEnd('\', '/')) -replace '[^A-Za-z0-9._-]', '-'
    if (-not $Agents) {
        $Agents = Read-Agents
    }
    if (-not $Vcs) {
        $Vcs = Read-Vcs -ProjectPath $targetFullPath
    }
    foreach ($cli in @('claude', 'codex')) {
        if (($Agents -eq $cli -or $Agents -eq 'both') -and -not (Test-OnPath $cli)) {
            Write-Warning "$cli is not on PATH; team.ps1 installs it, or install it before running the team"
        }
    }
    if ($Vcs -eq 'p4' -and -not (Test-OnPath 'p4')) {
        Write-Warning 'p4 is not on PATH; install the Perforce CLI before running the team'
    }
    if ($DryRun) {
        Write-Output "+ write '$config' (name=$projectName, agents=$Agents, vcs=$Vcs)"
    }
    else {
        & $python -I (Join-Path $teamRoot 'write_config.py') (Join-Path $teamRoot 'templates/team.toml') $config $projectName $Agents $Vcs
        if ($LASTEXITCODE -ne 0) {
            throw "Could not write $config"
        }
    }
    Write-Output "added: $config"
    $script:addedCount++
}

if ($Vcs -eq 'p4') {
    $stateHint = ", add .agent-team/ to the project's P4IGNORE file"
}
else {
    Add-StateDirExclude -ProjectPath $targetFullPath
    $stateHint = if ($script:stateExcluded) { '' } else { ', add .agent-team/ to the project ignore list' }
}

$launcherTemplate = [System.IO.File]::ReadAllText((Join-Path $teamRoot 'templates/team.ps1'))
Write-MissingFile `
    -Destination (Join-Path $targetFullPath 'team.ps1') `
    -Content $launcherTemplate.Replace("'@@LOGOUT_AI_ROOT@@'", "'$($repoRoot.Replace("'", "''"))'") `
    -Description 'project launcher'

# team.cmd serves PowerShell and cmd; the extensionless sh shim serves Git Bash, which agents use for shell commands.
$teamScript = Join-Path $teamRoot 'team.py'
$teamUpScript = Join-Path $teamRoot 'bin/team-up'
Write-MissingFile `
    -Destination (Join-Path $BinDir 'team.cmd') `
    -Content "@echo off`r`n`"$python`" -X utf8 `"$teamScript`" %*`r`nexit /b %errorlevel%`r`n" `
    -Description 'team command'
Write-MissingFile `
    -Destination (Join-Path $BinDir 'team') `
    -Content "#!/bin/sh`nexec `"$($python.Replace('\', '/'))`" -X utf8 `"$($teamScript.Replace('\', '/'))`" `"`$@`"`n" `
    -Description 'team command for Git Bash'
Write-MissingFile `
    -Destination (Join-Path $BinDir 'team-up.cmd') `
    -Content "@echo off`r`n`"$python`" -X utf8 `"$teamUpScript`" %*`r`nexit /b %errorlevel%`r`n" `
    -Description 'dashboard command'

$pathEntries = @($env:PATH -split [System.IO.Path]::PathSeparator | ForEach-Object { $_.TrimEnd('\', '/') })
if ($pathEntries -notcontains $BinDir.TrimEnd('\', '/')) {
    Write-Warning "$BinDir is not on PATH; add it so agents and the coordinator find 'team'"
}

if ($DryRun) {
    Write-Output "dry run complete: $($script:addedCount) item(s) would be added, $($script:skippedCount) existing item(s) kept"
}
else {
    Write-Output "agent team setup complete: $($script:addedCount) item(s) added, $($script:skippedCount) existing item(s) kept"
}
Write-Output "next: review $config$stateHint, run .\team.ps1 from the project"
