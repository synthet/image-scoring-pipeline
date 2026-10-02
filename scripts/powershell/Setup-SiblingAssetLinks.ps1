#Requires -Version 5.1
<#
.SYNOPSIS
  Link pipeline model paths to a single copy in the image-scoring-model sibling checkout.

.DESCRIPTION
  Uses hard links on the same NTFS volume (no Developer Mode). Safe to re-run.
  Does not link Python virtualenvs — use ~/.venvs/tf or repo-root .venv per ENVIRONMENTS.md.

.PARAMETER PipelineRoot
  Pipeline repo root (default: two levels above this script).

.PARAMETER ModelRepoRoot
  Sibling model repo (default: ../image-scoring-model next to pipeline).
#>
param(
    [string]$PipelineRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$ModelRepoRoot = ""
)

$ErrorActionPreference = "Stop"

if (-not $ModelRepoRoot) {
    $parent = (Resolve-Path (Join-Path $PipelineRoot "..")).Path
    $ModelRepoRoot = Join-Path $parent "image-scoring-model"
}

$links = @(
    @{
        Name = "bird_detect_v0.pt"
        PipelineRel = "models\bird_detect_v0.pt"
        ModelRel    = "models\bird_detect_v0.pt"
    },
    @{
        Name = "eye_pose_v0.pt"
        PipelineRel = "models\eye_pose_v0.pt"
        ModelRel    = "models\eye_pose_v0.pt"
    }
)

function Ensure-HardLink {
    param([string]$LinkPath, [string]$TargetPath)
    if (-not (Test-Path -LiteralPath $TargetPath)) {
        Write-Host "[skip] target missing: $TargetPath"
        return
    }
    $dir = Split-Path -Parent $LinkPath
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    if (Test-Path -LiteralPath $LinkPath) {
        $item = Get-Item -LiteralPath $LinkPath -Force
        if ($item.LinkType -eq "HardLink") {
            Write-Host "[ok]   $LinkPath (hard link exists)"
            return
        }
        if ($item.LinkType -eq "") {
            $h1 = (Get-FileHash -LiteralPath $LinkPath -Algorithm SHA256).Hash
            $h2 = (Get-FileHash -LiteralPath $TargetPath -Algorithm SHA256).Hash
            if ($h1 -eq $h2) {
                Write-Host "[ok]   $LinkPath (same file as sibling)"
                return
            }
        }
        Write-Warning "Refusing to replace non-link file: $LinkPath"
        return
    }
    New-Item -ItemType HardLink -Path $LinkPath -Target $TargetPath | Out-Null
    Write-Host "[link] $LinkPath -> $TargetPath"
}

Write-Host "Pipeline: $PipelineRoot"
Write-Host "Model:    $ModelRepoRoot"
Write-Host ""

foreach ($entry in $links) {
    $target = Join-Path $ModelRepoRoot $entry.ModelRel
    $link = Join-Path $PipelineRoot $entry.PipelineRel
    Ensure-HardLink -LinkPath $link -TargetPath $target
}

Write-Host ""
Write-Host "Set config bird_detection.local_path / localization.keypoints.bird_head.local_path to these paths if you prefer explicit config over models/*.pt in repo root."
