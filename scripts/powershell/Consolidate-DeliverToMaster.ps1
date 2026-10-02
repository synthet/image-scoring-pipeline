#Requires -Version 5.1
<#
.SYNOPSIS
  Consolidate local commits on feat/scene-route-412 and finish delivery to master (PR #471 + sync).

.DESCRIPTION
  Dry-run by default. Pass -Execute to commit, push, and merge PR 471 when checks are green.
  See docs/reports/deliver-master-runbook-2026-10-02.md

.PARAMETER Execute
  Perform git commit, push, and gh pr merge (not dry-run).
#>
param(
    [switch]$Execute
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $RepoRoot

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

$Branch = 'feat/scene-route-412'
$PrSceneRoute = 471

Write-Step "Repository: $RepoRoot"
$current = git rev-parse --abbrev-ref HEAD
if ($current -ne $Branch) {
    Write-Warning "Expected branch $Branch; on $current. Checkout $Branch before -Execute."
}

Write-Step 'git fetch origin'
if ($Execute) { git fetch origin } else { Write-Host '(dry-run) git fetch origin' }

$dirty = @(git status --porcelain)
if ($dirty.Count -gt 0) {
    Write-Host "Dirty files: $($dirty.Count)" -ForegroundColor Yellow
    $dirty | Select-Object -First 40 | ForEach-Object { Write-Host "  $_" }
}

# Paths for consolidated commits (exclude generated bundles and local weights)
$Commit1 = @(
    'modules/score_analytics/model_selection.py',
    'modules/score_analytics/study.py',
    'modules/score_analytics/study_data.py',
    'modules/score_analytics/study_report.py',
    'modules/score_analytics/study_review.py',
    'scripts/analysis/model_selection_report.py',
    'scripts/analysis/model_selection_study.py',
    'tests/test_model_selection.py',
    'tests/test_model_selection_study.py',
    'tests/test_analyze_v1_failure_review.py',
    'tests/test_analyze_v1_owner_review.py',
    'tests/test_build_v1_failure_review.py',
    'tests/test_make_compare_label_page.py',
    'tests/test_score_compare_labels.py',
    'tests/test_visual_evidence.py',
    'modules/visual_evidence/',
    'tests/fixtures/evidence/'
) | Where-Object { Test-Path (Join-Path $RepoRoot $_) }

$Commit2 = @(
    'docs/reports/model-selection-codex-handoff-2026-10-02.md',
    'docs/reports/model-selection-findings-2026-10-02.md',
    'docs/reports/model_evaluation_and_curation_plan.md',
    'docs/reports/model-selection-session-2026-10-01.md',
    'docs/reports/deliver-master-runbook-2026-10-02.md',
    'docs/reports/INDEX.md',
    'docs/log.md',
    'docs/features/implemented/11-score-analytics-and-model-suitability.md',
    'docs/features/implemented/12-visual-evidence-overlays.md',
    'docs/features/planned/visual-evidence-stage6-persistence.md',
    'docs/guides/setup/SIBLING_ASSET_LINKS.md',
    'docs/planning/visual-evidence-api-and-grids.md',
    'docs/technical/VISUAL_EVIDENCE_API.md',
    'docs/features/implemented/INDEX.md',
    'docs/features/planned/INDEX.md',
    'docs/reports/model_evaluation_and_curation_plan.md',
    'scripts/analysis/model_selection_report.py',
    'scripts/powershell/Setup-SiblingAssetLinks.ps1',
    'AGENTS.md',
    '.gitignore'
) | Where-Object { Test-Path (Join-Path $RepoRoot $_) }

$Commit3 = @(
    'config.example.json',
    '.claude/settings.json'
) | Where-Object { Test-Path (Join-Path $RepoRoot $_) }

# Scene route / API / UI already on branch — stage remaining tracked mods if present
$Commit4 = @(
    'modules/api/',
    'modules/api/__init__.py',
    'modules/api/routers/data_query.py',
    'scripts/batch/docker_gpu_run.bat',
    'scripts/powershell/Invoke-GpuShell.ps1',
    'static/app/',
    'frontend/',
    'scripts/analysis/model_selection_study.py'
) | Where-Object { Test-Path (Join-Path $RepoRoot $_) }

function Invoke-Commit($paths, $message) {
    $existing = @($paths | Where-Object { Test-Path (Join-Path $RepoRoot $_) })
    if ($existing.Count -eq 0) {
        Write-Host "Skip commit (no paths): $message"
        return
    }
    if (-not $Execute) {
        Write-Host "(dry-run) git add + commit: $message"
        $existing | ForEach-Object { Write-Host "  + $_" }
        return
    }
    git add -- @existing
    $staged = git diff --cached --name-only
    if (-not $staged) {
        Write-Host "Nothing staged for: $message"
        return
    }
    git commit -m $message
}

Write-Step 'Pull latest feature branch'
if ($Execute) {
    git pull --ff-only origin $Branch
} else {
    Write-Host "(dry-run) git pull --ff-only origin $Branch"
}

Invoke-Commit $Commit1 @'
feat(analytics): label-free model selection and blind study harness

Composite ablation, within-stack consensus, report CLI, and frozen study
package (create/serve/explore). Statistical only; no fusion weight changes.
'@

Invoke-Commit $Commit2 @'
docs(reports): model selection handoff, findings, and deliver runbook

Wiki index, session summary, curation plan evidence sources, Codex _2 handoff.
'@

Invoke-Commit $Commit3 @'
chore(config): enable localization and scene_route in example config

Turn on localization phase and SigLIP2 bird route defaults (p>=0.065).
Fix Claude hook paths for Windows Cursor (absolute hook.py).
'@

Invoke-Commit $Commit4 @'
feat(scene-route): remaining API, UI assets, and shell helpers (#412)
'@

Write-Step 'Push and merge PR #471'
if ($Execute) {
    git push origin $Branch
    $prState = gh pr view $PrSceneRoute --json state,mergeable,statusCheckRollup 2>$null | ConvertFrom-Json
    if ($prState.state -eq 'OPEN') {
        Write-Host "Waiting for checks on PR $PrSceneRoute..."
        gh pr checks $PrSceneRoute --watch
        gh pr merge $PrSceneRoute --merge --delete-branch
    } else {
        Write-Host "PR $PrSceneRoute state: $($prState.state) (skip merge)"
    }
    git checkout master
    git pull --ff-only origin master
    Write-Host 'Done. master at:' (git log -1 --oneline)
} else {
    Write-Host "(dry-run) git push origin $Branch"
    Write-Host "(dry-run) gh pr checks $PrSceneRoute --watch; gh pr merge $PrSceneRoute --merge --delete-branch"
    Write-Host "(dry-run) git checkout master; git pull --ff-only origin master"
}

Write-Step 'Excluded from commits (add manually if intended)'
@(
    'models/*.pt',
    'reports/model_selection/',
    'reports/model-selection-2026-10-01/snapshot.json.gz',
    'reports/model_selection/',
    'reports/model-selection-2026-10-01/',
    '.agent/scratch/'
) | ForEach-Object { Write-Host "  $_" }
