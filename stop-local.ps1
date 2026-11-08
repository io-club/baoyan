$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
$env:DOCKER_HOST='npipe:////./pipe/dockerDesktopLinuxEngine'
docker compose --project-name baoyan-local --env-file .runtime/local.env -f deploy/compose.yml -f deploy/compose.local.yml --profile integrations stop
if ($LASTEXITCODE -ne 0) { throw 'Could not stop the local project' }
