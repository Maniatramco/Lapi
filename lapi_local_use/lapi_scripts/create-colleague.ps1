param([string]$Username, [string]$EnvFile = '.env.oracle')
$ErrorActionPreference = 'Stop'
if (-not $Username) { $Username = Read-Host 'Colleague Lapi username' }
$taskSecurePassword = Read-Host 'Colleague Lapi password (12–200 characters)' -AsSecureString
$taskPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($taskSecurePassword)
Push-Location -LiteralPath (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
try {
    $taskPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($taskPointer)
    $taskPayload = @{ username = $Username; password = $taskPassword } | ConvertTo-Json -Compress
    $taskPayload | & docker compose --project-directory . --env-file $EnvFile -f lapi_local_use/compose.oracle.yaml exec -T api python -m lapi_app.provision_account
    if ($LASTEXITCODE -ne 0) { throw 'Account provisioning did not complete. Existing accounts were not changed.' }
} finally {
    $taskPassword = $null; $taskPayload = $null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($taskPointer)
    $taskSecurePassword.Dispose()
    Pop-Location
}
