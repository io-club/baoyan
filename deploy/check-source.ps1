$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
foreach ($file in @('start-local.ps1','stop-local.ps1','deploy/local-compose.ps1','deploy/check-source.ps1')) {
    $parseErrors=$null; $tokens=$null
    [void][Management.Automation.Language.Parser]::ParseFile((Join-Path (Get-Location) $file),[ref]$tokens,[ref]$parseErrors)
    if ($parseErrors.Count -gt 0) { throw ($parseErrors | Out-String) }
}
$env:DOCKER_HOST='npipe:////./pipe/dockerDesktopLinuxEngine'
& docker compose --project-name baoyan-local --env-file deploy/local.env.example -f deploy/compose.yml -f deploy/compose.local.yml --profile integrations config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Compose validation failed.' }
Write-Host 'PowerShell syntax and Compose configuration are valid.'
