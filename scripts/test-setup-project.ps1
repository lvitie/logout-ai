[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskTestRoot = Join-Path ([System.IO.Path]::GetTempPath()) "logout-ai-project-setup-test-$([guid]::NewGuid())"

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
    $newProject = Join-Path $taskTestRoot 'new project'
    & (Join-Path $repoRoot 'scripts/setup-project.ps1') $newProject -Skill rust-cli | Out-Null

    foreach ($document in @('AGENTS.md', 'SPEC.md', 'ROADMAP.md', 'TASKS.md')) {
        Assert-Condition `
            (Test-Path -LiteralPath (Join-Path $newProject $document) -PathType Leaf) `
            "Missing seeded document: $document"
    }

    foreach ($skillName in @('ai-project-manager', 'project-bootstrap', 'rust-cli')) {
        $skillFile = Join-Path $newProject ".agents/skills/$skillName/SKILL.md"
        Assert-Condition (Test-Path -LiteralPath $skillFile -PathType Leaf) "Missing seeded skill: $skillName"
    }

    $existingProject = Join-Path $taskTestRoot 'existing project'
    $existingSkill = Join-Path $existingProject '.agents/skills/ai-project-manager'
    New-Item -ItemType Directory -Path $existingSkill -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $existingProject 'AGENTS.md') -Value 'custom project instructions'
    Set-Content -LiteralPath (Join-Path $existingSkill 'SKILL.md') -Value 'custom skill instructions'

    & (Join-Path $repoRoot 'scripts/setup-project.ps1') $existingProject | Out-Null

    Assert-Condition `
        ((Get-Content -LiteralPath (Join-Path $existingProject 'AGENTS.md') -Raw).Trim() -eq 'custom project instructions') `
        'Existing project instructions were overwritten'
    Assert-Condition `
        ((Get-Content -LiteralPath (Join-Path $existingSkill 'SKILL.md') -Raw).Trim() -eq 'custom skill instructions') `
        'Existing skill instructions were overwritten'
    Assert-Condition `
        (Test-Path -LiteralPath (Join-Path $existingProject 'SPEC.md') -PathType Leaf) `
        'Missing document added to existing project'
    Assert-Condition `
        (Test-Path -LiteralPath (Join-Path $existingSkill 'agents/openai.yaml') -PathType Leaf) `
        'Missing skill content was not merged'

    & (Join-Path $repoRoot 'scripts/setup-project.ps1') $existingProject | Out-Null
    Assert-Condition `
        ((Get-Content -LiteralPath (Join-Path $existingProject 'AGENTS.md') -Raw).Trim() -eq 'custom project instructions') `
        'Idempotent setup changed existing project instructions'

    $dryRunProject = Join-Path $taskTestRoot 'dry run project'
    & (Join-Path $repoRoot 'scripts/setup-project.ps1') $dryRunProject -DryRun | Out-Null
    Assert-Condition (-not (Test-Path -LiteralPath $dryRunProject)) 'Dry run created the target project'

    $fileTarget = Join-Path $taskTestRoot 'file target'
    Set-Content -LiteralPath $fileTarget -Value 'not a directory'
    $fileTargetFailed = $false
    try {
        & (Join-Path $repoRoot 'scripts/setup-project.ps1') $fileTarget | Out-Null
    }
    catch {
        $fileTargetFailed = $true
    }
    Assert-Condition $fileTargetFailed 'Setup accepted a file as the target'

    $missingSkillProject = Join-Path $taskTestRoot 'missing skill project'
    $missingSkillFailed = $false
    try {
        & (Join-Path $repoRoot 'scripts/setup-project.ps1') `
            $missingSkillProject -Skill does-not-exist | Out-Null
    }
    catch {
        $missingSkillFailed = $true
    }
    Assert-Condition $missingSkillFailed 'Setup accepted a missing skill'
    Assert-Condition `
        (-not (Test-Path -LiteralPath $missingSkillProject)) `
        'Missing-skill failure created the target project'

    Write-Output 'project setup integration test passed'
}
finally {
    $tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    $normalizedTestRoot = [System.IO.Path]::GetFullPath($taskTestRoot)
    if (
        $normalizedTestRoot.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -and
        (Split-Path -Leaf $normalizedTestRoot).StartsWith('logout-ai-project-setup-test-')
    ) {
        Remove-Item -LiteralPath $normalizedTestRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
