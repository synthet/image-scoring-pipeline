$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot '../powershell/Backup-Postgres.ps1'
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path $scriptPath).Path, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
$guard = $ast.Find({ param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
    $node.Name -eq 'Assert-RealDirectory'
}, $true)
Invoke-Expression $guard.Extent.Text

# Isolate filesystem probes; no database, copy, or retention operation runs.
function Test-Path { param($LiteralPath) return $true }
function Get-Item {
    param($LiteralPath, [switch]$Force)
    $isLink = $LiteralPath -eq $script:linkedPath
    return [pscustomobject]@{
        LinkType = if ($isLink) { 'Junction' } else { $null }
        Target = @('D:\outside')
        Attributes = if ($isLink) { [IO.FileAttributes]::ReparsePoint } else { [IO.FileAttributes]::Directory }
        PSIsContainer = $true
    }
}
$script:linkedPath = $null
Assert-RealDirectory 'D:\mirrors\real'
foreach ($linked in @('D:\mirrors\linked', 'D:\mirrors')) {
    $script:linkedPath = $linked
    $refused = $false
    try { Assert-RealDirectory 'D:\mirrors\linked' } catch { $refused = $true }
    if (-not $refused) { throw "Guard accepted reparse point: $linked" }
}
Write-Output 'PASS: real mirror accepted; direct and ancestor reparse points refused'
