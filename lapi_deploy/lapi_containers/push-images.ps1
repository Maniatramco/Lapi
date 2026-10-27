# Build Lapi's two images for x86 and push them to OCIR.
#   .\push-images.ps1 -Tag 26.1.16.0
# Needs Docker and an OCI auth token (Console: Profile > Auth tokens). Docker asks
# for the token once; it is not stored by this script.
param(
    [Parameter(Mandatory = $true)][string]$Tag,
    [string]$Username
)
$ErrorActionPreference = 'Stop'
# A shell opened before Terraform was installed with winget has an old PATH.
$terraform = (Get-Command terraform -ErrorAction SilentlyContinue).Source
if (-not $terraform) {
    $terraform = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Links\terraform.exe", "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Hashicorp.Terraform*\terraform.exe" -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $terraform) { throw 'Terraform not found. Install it (winget install Hashicorp.Terraform) or open a new terminal.' }
Push-Location $PSScriptRoot
try {
    $registry = & $terraform output -raw registry
    if (-not $registry) { throw 'Run terraform apply first so the registry and repositories exist.' }
    $registryHost = $registry.Split('/')[0]
    $namespace = $registry.Split('/')[1]
    if (-not $Username) { $Username = Read-Host "OCI username (as in the Console, e.g. you@example.com)" }
    docker login $registryHost -u "$namespace/$Username"
    if ($LASTEXITCODE -ne 0) { throw 'docker login failed.' }

    $root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
    $repositories = & $terraform output -json image_repositories | ConvertFrom-Json
    $api = "$($repositories.api):$Tag"
    $web = "$($repositories.web):$Tag"
    docker build --platform linux/amd64 -t $api `
        --build-arg INSTALL_ORACLE=true --build-arg INSTALL_OCI=true `
        --build-arg INSTALL_CLOUD_MODELS=true --build-arg INSTALL_LOCAL_EMBEDDINGS=false `
        (Join-Path $root 'lapi_backend')
    if ($LASTEXITCODE -ne 0) { throw 'API image build failed.' }
    docker build --platform linux/amd64 -t $web (Join-Path $root 'lapi_frontend')
    if ($LASTEXITCODE -ne 0) { throw 'Web image build failed.' }
    docker push $api; if ($LASTEXITCODE -ne 0) { throw 'API image push failed.' }
    docker push $web; if ($LASTEXITCODE -ne 0) { throw 'Web image push failed.' }
    Write-Host "Pushed $api and $web. Now run: terraform apply -var image_tag=$Tag"
} finally {
    Pop-Location
}
