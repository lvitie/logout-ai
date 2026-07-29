[CmdletBinding()]
param(
    [Parameter(Mandatory, Position = 0)]
    [string] $TargetPath,

    [Alias('dry-run')]
    [switch] $DryRun,

    [string[]] $Skill = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$templateRoot = Join-Path $repoRoot '.agents/skills/ai-project-manager/assets/project-docs'
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

function Copy-MissingFile {
    param(
        [Parameter(Mandatory)]
        [string] $Source,

        [Parameter(Mandatory)]
        [string] $Destination
    )

    if (Get-ExistingItem -LiteralPath $Destination) {
        Write-Output "kept existing: $Destination"
        $script:skippedCount++
        return
    }

    Ensure-Directory -LiteralPath (Split-Path -Parent $Destination)
    if ($DryRun) {
        Write-Output "+ Copy-Item -LiteralPath '$Source' -Destination '$Destination'"
    }
    else {
        Copy-Item -LiteralPath $Source -Destination $Destination
    }
    Write-Output "added: $Destination"
    $script:addedCount++
}

function Copy-MissingTree {
    param(
        [Parameter(Mandatory)]
        [string] $SourceRoot,

        [Parameter(Mandatory)]
        [string] $DestinationRoot
    )

    Ensure-Directory -LiteralPath $DestinationRoot

    Get-ChildItem -LiteralPath $SourceRoot -Directory -Recurse -Force |
        Sort-Object { $_.FullName.Length } |
        ForEach-Object {
            $relativePath = [System.IO.Path]::GetRelativePath($SourceRoot, $_.FullName)
            Ensure-Directory -LiteralPath (Join-Path $DestinationRoot $relativePath)
        }

    Get-ChildItem -LiteralPath $SourceRoot -File -Recurse -Force |
        ForEach-Object {
            $relativePath = [System.IO.Path]::GetRelativePath($SourceRoot, $_.FullName)
            Copy-MissingFile -Source $_.FullName -Destination (Join-Path $DestinationRoot $relativePath)
        }
}

if ($TargetPath -match '[\x00-\x1F\x7F]') {
    throw 'Target path contains unsupported control characters.'
}

if (-not (Test-Path -LiteralPath $templateRoot -PathType Container)) {
    throw "Project templates do not exist: $templateRoot"
}

$targetFullPath = [System.IO.Path]::GetFullPath($TargetPath)
$existingTarget = Get-ExistingItem -LiteralPath $targetFullPath
if ($existingTarget -and -not $existingTarget.PSIsContainer) {
    throw "Target exists and is not a directory: $targetFullPath"
}
if ($existingTarget -and $targetFullPath.TrimEnd('\', '/') -eq $repoRoot.TrimEnd('\', '/')) {
    throw 'Target cannot be the Logout AI repository.'
}

$skillsToCopy = [System.Collections.Generic.List[string]]::new()
foreach ($skillName in @('ai-project-manager', 'project-bootstrap') + $Skill) {
    if ($skillName -notmatch '^[a-z0-9][a-z0-9-]*$') {
        throw "Invalid skill name: $skillName"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $repoRoot ".agents/skills/$skillName") -PathType Container)) {
        throw "Skill does not exist in Logout AI: $skillName"
    }
    if (-not $skillsToCopy.Contains($skillName)) {
        $skillsToCopy.Add($skillName)
    }
}

Ensure-Directory -LiteralPath $targetFullPath

foreach ($document in @('AGENTS.md', 'SPEC.md', 'ROADMAP.md', 'TASKS.md')) {
    Copy-MissingFile `
        -Source (Join-Path $templateRoot $document) `
        -Destination (Join-Path $targetFullPath $document)
}

foreach ($skillName in $skillsToCopy) {
    Copy-MissingTree `
        -SourceRoot (Join-Path $repoRoot ".agents/skills/$skillName") `
        -DestinationRoot (Join-Path $targetFullPath ".agents/skills/$skillName")
}

if ($DryRun) {
    Write-Output (
        'dry run complete: {0} file(s) would be added, {1} existing file(s) kept' -f
        $script:addedCount, $script:skippedCount
    )
}
else {
    Write-Output (
        'project setup complete: {0} file(s) added, {1} existing file(s) kept' -f
        $script:addedCount, $script:skippedCount
    )
}
