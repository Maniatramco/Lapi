#Requires -Version 5.1
# Run from an open PowerShell window. No credentials are stored here.
[CmdletBinding()]
param([string]$Inputs, [switch]$CommittedSource)
$ErrorActionPreference = 'Stop'
$lapiRepository = Split-Path -Parent $PSScriptRoot
$lapiLauncher = Join-Path $lapiRepository 'lapi_deploy\deploy.ps1'
if (-not $Inputs) { $Inputs = Join-Path $PSScriptRoot 'lapi-oci-inputs.json' }
# Resolve relative input paths before changing to the repository directory.
$lapiInputs = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Inputs)
try {
    if (-not (Test-Path -LiteralPath $lapiLauncher -PathType Leaf)) { throw "Deployment script not found: $lapiLauncher" }
    if (-not (Test-Path -LiteralPath $lapiInputs -PathType Leaf)) { throw "Target inputs not found: $lapiInputs" }
    Write-Host 'DEPLOYMENT: type CONNECT for preflight, then review the plan before typing PUBLISH.'
    Write-Host ('Selected destination inputs: ' + $lapiInputs)
    Push-Location -LiteralPath $lapiRepository
    try {
        & $lapiLauncher -Inputs $lapiInputs -CommittedSource:$CommittedSource
    }
    finally {
        Pop-Location
    }
}
catch {
    Write-Host ('Stopped: ' + $_.Exception.Message) -ForegroundColor Red
    throw
}
finally {
    if ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
        Read-Host 'Press Enter to finish' | Out-Null
    }
}