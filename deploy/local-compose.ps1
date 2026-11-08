param([ValidateSet('ps','logs')][string]$Action='ps')
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$envFile=Join-Path (Get-Location) '.runtime/local.env'
if (!(Test-Path -LiteralPath $envFile)) { throw 'Run start-local.ps1 first.' }
$env:DOCKER_HOST='npipe:////./pipe/dockerDesktopLinuxEngine'
$composeArgs=@('compose','--project-name','baoyan-local','--env-file',$envFile,'-f','deploy/compose.yml','-f','deploy/compose.local.yml','--profile','integrations')
if ($Action -eq 'logs') { & docker @composeArgs logs --tail 150 } else { & docker @composeArgs ps -a }
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose command failed.' }
