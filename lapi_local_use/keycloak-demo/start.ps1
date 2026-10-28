# Starts the local Keycloak demo. Creates .env with a random Lapi master key the first time.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$envFile = Join-Path $here '.env'
if (-not (Test-Path $envFile)) {
  $bytes = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  $key = [Convert]::ToBase64String($bytes).Replace('+','-').Replace('/','_')
  Set-Content -Path $envFile -Value "LAPI_MASTER_KEY=$key" -Encoding ascii
}
docker compose -f (Join-Path $here 'compose.yaml') --env-file $envFile up -d
Write-Host 'Waiting for Lapi on http://localhost:3100 ...'
for ($i = 0; $i -lt 60; $i++) {
  try { if ((Invoke-WebRequest -UseBasicParsing http://localhost:3100/api/auth/status -TimeoutSec 3).StatusCode -eq 200) { Write-Host 'Ready: open http://localhost:3100'; exit 0 } } catch {}
  Start-Sleep -Seconds 3
}
Write-Host 'Not ready yet; check: docker compose -f compose.yaml logs api keycloak'
