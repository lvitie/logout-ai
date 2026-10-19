[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) "logout-ai-agent-team-test-$([guid]::NewGuid())"
$setup = Join-Path $repoRoot 'scripts/setup-agent-team.ps1'
$savedEnvironment = @{}
foreach ($name in @('PATH', 'TEAM_CONFIG', 'XDG_STATE_HOME', 'XDG_CACHE_HOME', 'CODEX_HOME', 'GIT_CONFIG_GLOBAL', 'GIT_CONFIG_NOSYSTEM')) {
    $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name)
}

function Assert-Condition {
    param(
        [Parameter(Mandatory)]
        [bool] $Condition,

        [Parameter(Mandatory)]
        [string] $Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

try {
    $project = Join-Path $testRoot 'My Project'
    $bin = Join-Path $testRoot 'bin'
    $fake = Join-Path $testRoot 'fakebin'
    New-Item -ItemType Directory -Path $fake -Force | Out-Null
    # Fake agent CLIs exit 99 so a task run fails loudly instead of reaching a real agent.
    foreach ($cli in @('claude', 'codex')) {
        [System.IO.File]::WriteAllText((Join-Path $fake "$cli.cmd"), "@echo off`r`necho fake $cli 1>&2`r`nexit /b 99`r`n")
    }
    $env:PATH = $fake + [System.IO.Path]::PathSeparator + $bin + [System.IO.Path]::PathSeparator + $env:PATH
    $env:XDG_STATE_HOME = Join-Path $testRoot 'state'
    $env:XDG_CACHE_HOME = Join-Path $testRoot 'cache'
    $env:CODEX_HOME = Join-Path $testRoot 'codex'
    $env:GIT_CONFIG_GLOBAL = Join-Path $testRoot 'gitconfig'
    $env:GIT_CONFIG_NOSYSTEM = '1'
    Remove-Item Env:TEAM_CONFIG -ErrorAction SilentlyContinue

    $dryOutput = (& $setup $project -DryRun -BinDir $bin -Agents codex -Vcs git) -join "`n"
    Assert-Condition ($dryOutput -match 'dry run complete') 'Dry run did not finish'
    Assert-Condition (-not (Test-Path -LiteralPath $project) -and -not (Test-Path -LiteralPath $bin)) 'Dry run created files'

    & $setup $project -BinDir $bin -Agents codex -Vcs git | Out-Null
    foreach ($file in @('team.toml', 'team.ps1')) {
        Assert-Condition (Test-Path -LiteralPath (Join-Path $project $file) -PathType Leaf) "$file was not created"
    }
    foreach ($file in @('team.cmd', 'team', 'team-up.cmd')) {
        Assert-Condition (Test-Path -LiteralPath (Join-Path $bin $file) -PathType Leaf) "$file shim was not created"
    }
    $parseErrors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile((Join-Path $project 'team.ps1'), [ref]$null, [ref]$parseErrors)
    Assert-Condition ($parseErrors.Count -eq 0) 'team.ps1 has invalid syntax'
    $helpOutput = (& (Join-Path $project 'team.ps1') --help) -join "`n"
    Assert-Condition ($helpOutput -match 'Missing dependencies') 'Launcher help failed'
    $config = [System.IO.File]::ReadAllText((Join-Path $project 'team.toml'))
    Assert-Condition ($config -match '(?m)^name = "My-Project"\r?$') 'Project name was not substituted'
    Assert-Condition ($config -notmatch 'cli = "claude"') 'codex preset still uses claude'

    $second = (& $setup $project -BinDir $bin -Agents codex) -join "`n"
    Assert-Condition ($second -match '0 item\(s\) added') 'Second run was not idempotent'
    [System.IO.File]::AppendAllText((Join-Path $project 'team.ps1'), "# preserved launcher`r`n")
    & $setup $project -BinDir $bin | Out-Null
    Assert-Condition (([System.IO.File]::ReadAllLines((Join-Path $project 'team.ps1')))[-1] -eq '# preserved launcher') 'Existing launcher overwritten'

    $rejected = $false
    try {
        & $setup (Join-Path $testRoot 'other') -BinDir $bin -Agents gemini | Out-Null
    }
    catch {
        $rejected = $true
    }
    Assert-Condition $rejected 'Unknown -Agents value accepted'
    $rejected = $false
    try {
        & $setup (Join-Path $testRoot 'other') -BinDir $bin -Vcs svn | Out-Null
    }
    catch {
        $rejected = $true
    }
    Assert-Condition $rejected 'Unknown -Vcs value accepted'

    # The installed shim creates and lists a task; running it reaches the fake Codex through the coordinator.
    & git -C $project init -q
    Assert-Condition ($LASTEXITCODE -eq 0) 'git init failed'
    Push-Location -LiteralPath $project
    try {
        & (Join-Path $bin 'team.cmd') new --no-run 'setup check' | Out-Null
        Assert-Condition ($LASTEXITCODE -eq 0) 'team new failed'
        $status = (& (Join-Path $bin 'team.cmd') status) -join "`n"
        Assert-Condition ($status -match 'chg:t001') 'Installed team command did not list the task'
        & (Join-Path $bin 'team.cmd') run t001 | Out-Null
        $state = Get-Content -LiteralPath (Join-Path $project '.agent-team/t001/state.json') -Raw | ConvertFrom-Json
        Assert-Condition ($state.status -eq 'failed' -and $state.reason -match 'exited 99') "Task run did not fail through the fake agent: $($state.reason)"

        $guard = Join-Path $project '.agent-team/guard-bin'
        Assert-Condition (Test-Path -LiteralPath (Join-Path $guard 'git.cmd') -PathType Leaf) 'git guard shim was not created'
        $env:TEAM_CONFIG = Join-Path $project 'team.toml'
        & (Join-Path $guard 'git.cmd') commit -m 'blocked' 2>$null | Out-Null
        Assert-Condition ($LASTEXITCODE -ne 0) 'Guard allowed git commit'
        $forwarded = (& (Join-Path $guard 'git.cmd') status --porcelain) -join "`n"
        Assert-Condition ($LASTEXITCODE -eq 0 -and $forwarded -match 'team\.toml') 'Guard did not forward git status'
        Remove-Item Env:TEAM_CONFIG
    }
    finally {
        Pop-Location
    }
    $repo = Join-Path $testRoot 'repo'
    & git init -q $repo
    & $setup $repo -BinDir $bin -Agents both -Vcs git | Out-Null
    & $setup $repo -BinDir $bin | Out-Null
    $entries = @([System.IO.File]::ReadAllLines((Join-Path $repo '.git/info/exclude')) | Where-Object { $_ -eq '/.agent-team/' })
    Assert-Condition ($entries.Count -eq 1) 'State dir exclude entry missing or duplicated'

    # Perforce: the p4 adapter and guard are configured and no git exclude entry is written.
    $p4Repo = Join-Path $testRoot 'repo-p4'
    & git init -q $p4Repo
    & $setup $p4Repo -BinDir $bin -Agents claude -Vcs p4 | Out-Null
    $p4Config = [System.IO.File]::ReadAllText((Join-Path $p4Repo 'team.toml'))
    Assert-Condition ($p4Config -match '(?m)^kind = "p4"' -and $p4Config -match '(?m)^git = \["\*"\]') 'p4 preset was not written'
    Assert-Condition (-not ([System.IO.File]::ReadAllLines((Join-Path $p4Repo '.git/info/exclude')) -contains '/.agent-team/')) 'git exclude written for a p4 project'

    Write-Output 'agent team PowerShell setup test passed'
}
finally {
    foreach ($name in $savedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name])
    }
    if ($testRoot.StartsWith([System.IO.Path]::GetTempPath()) -and (Test-Path -LiteralPath $testRoot)) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}
