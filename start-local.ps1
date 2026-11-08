param([switch]$Test)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$runtime = Join-Path $PSScriptRoot '.runtime'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
$envFile = Join-Path $runtime 'local.env'
$env:TEMP=Join-Path $runtime 'tmp'
$env:TMP=$env:TEMP
$env:npm_config_cache=Join-Path $runtime 'cache/npm'
foreach ($folder in @('tmp','cache/m2','cache/npm','cache/pip','local-data')) {
    New-Item -ItemType Directory -Force -Path (Join-Path $runtime $folder) | Out-Null
}
$env:HTTP_PROXY = ''
$env:HTTPS_PROXY = ''
$env:ALL_PROXY = ''
$env:NO_PROXY = 'localhost,127.0.0.1,::1'
$env:DOCKER_HOST = 'npipe:////./pipe/dockerDesktopLinuxEngine'

function Compose {
    & docker compose --project-name baoyan-local --env-file $envFile -f deploy/compose.yml -f deploy/compose.local.yml @args
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose failed: $args" }
}

if (!(Test-Path -LiteralPath $envFile)) {
    $rootPath = $PSScriptRoot.Replace('\', '/')
    $secret = [guid]::NewGuid().ToString('N')
    $content = @"
APP_DIR=$rootPath
RUNTIME_DIR=$rootPath/.runtime/local-data
BAOYAN_CACHE_DIR=$rootPath/.runtime/cache
HOST_GID=10001
M2_CACHE_DIR=$rootPath/.runtime/cache/m2
NPM_CACHE_DIR=$rootPath/.runtime/cache/npm
PIP_CACHE_DIR=$rootPath/.runtime/cache/pip
POSTGRES_USER=baoyan
POSTGRES_DB=baoyan
POSTGRES_PASSWORD=$secret
REDIS_PASSWORD=$secret
RABBITMQ_USER=baoyan
RABBITMQ_PASSWORD=$secret
MINIO_ROOT_USER=baoyan
MINIO_ROOT_PASSWORD=$secret
BAOYAN_ADMIN_PASSWORD=baoyan-local-demo
OPENHANDS_LOCAL_BACKEND_API_KEY=$secret
OPENHANDS_SECRET_KEY=$secret
NAPCAT_WEBUI_TOKEN=$secret
"@
    [IO.File]::WriteAllText($envFile, $content, [Text.UTF8Encoding]::new($false))
}

$webPath=Join-Path $PSScriptRoot 'services/web'
$webBundle=Join-Path $webPath 'public/ui-shell.js'
$webSources=@(Get-ChildItem (Join-Path $webPath 'src') -Recurse -File)+@(Get-Item (Join-Path $webPath 'build.mjs'),(Join-Path $webPath 'package-lock.json'))
$needsWeb=!(Test-Path -LiteralPath $webBundle)
if (!$needsWeb) { $bundleTime=(Get-Item -LiteralPath $webBundle).LastWriteTimeUtc; $needsWeb=@($webSources | Where-Object {$_.LastWriteTimeUtc -gt $bundleTime}).Count -gt 0 }
if ($needsWeb) {
    $env:npm_config_cache=Join-Path $runtime 'cache/npm'
    $env:TEMP=Join-Path $runtime 'tmp'
    $env:TMP=$env:TEMP
    New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
    if (!(Test-Path -LiteralPath (Join-Path $webPath 'node_modules/.package-lock.json'))) {
        & npm ci --prefix $webPath --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'Web dependency installation failed' }
    }
    & npm run build --prefix $webPath
    if ($LASTEXITCODE -ne 0) { throw 'Web build failed' }
}

& docker info --format '{{.ServerVersion}}'
if ($LASTEXITCODE -ne 0) { throw 'Cannot access the Docker API. Check the exact Docker error above; the engine may be running but access may be denied.' }
& docker image inspect baoyan-minio:local-verified *> $null
if ($LASTEXITCODE -eq 0) { $env:BAOYAN_MINIO_IMAGE = 'baoyan-minio:local-verified' }
& docker image inspect baoyan-python:local-verified *> $null
if ($LASTEXITCODE -eq 0) { $env:BAOYAN_PYTHON_IMAGE = 'baoyan-python:local-verified' }
& docker image inspect baoyan-nginx:local-verified *> $null
if ($LASTEXITCODE -eq 0) { $env:BAOYAN_NGINX_IMAGE = 'baoyan-nginx:local-verified' }
foreach ($entry in @(@('jre','BAOYAN_JRE_IMAGE'),@('openhands','BAOYAN_OPENHANDS_IMAGE'),@('napcat','BAOYAN_NAPCAT_IMAGE'))) {
    $tag='baoyan-'+$entry[0]+':local-verified'
    & docker image inspect $tag *> $null
    if ($LASTEXITCODE -eq 0) { Set-Item -Path ('Env:'+$entry[1]) -Value $tag }
}
Compose config --quiet
Compose up -d --wait --wait-timeout 240 postgres rabbitmq nacos minio
& node deploy/seed-local.mjs
if ($LASTEXITCODE -ne 0) { throw 'Local Nacos initialization failed' }
$gatewayJar=Join-Path $PSScriptRoot 'services/gateway/target/gateway.jar'
$gatewaySources=@(Get-ChildItem services/gateway/src -Recurse -File)+@(Get-Item services/gateway/pom.xml)
$needsGateway=!(Test-Path -LiteralPath $gatewayJar)
if (!$needsGateway) { $jarTime=(Get-Item -LiteralPath $gatewayJar).LastWriteTimeUtc; $needsGateway=@($gatewaySources | Where-Object {$_.LastWriteTimeUtc -gt $jarTime}).Count -gt 0 }
if ($needsGateway) {
    $mavenImage=$env:BAOYAN_MAVEN_IMAGE
    if (!$mavenImage) {
        $mavenImage='maven:3.9-eclipse-temurin-17'
        & docker image inspect baoyan-maven:local-verified *> $null
        if ($LASTEXITCODE -eq 0) { $mavenImage='baoyan-maven:local-verified' }
    }
    & docker run --rm --mount "type=bind,source=$PSScriptRoot,target=/workspace" --mount "type=bind,source=$PSScriptRoot/.runtime/cache/m2,target=/root/.m2" -w /workspace -e HTTP_PROXY= -e HTTPS_PROXY= -e ALL_PROXY= $mavenImage mvn -f services/gateway/pom.xml '-Dmaven.repo.local=/root/.m2' -B package
    if ($LASTEXITCODE -ne 0) { throw 'Gateway build or tests failed' }
}
Compose build task-api platform-api gateway xhs
if ($Test) {
    foreach ($image in @('baoyan-tasks:local','baoyan-platform-api:local','baoyan-local-xhs:latest')) {
        & docker run --rm --network none $image python -m pytest -q -p no:cacheprovider
        if ($LASTEXITCODE -ne 0) { throw "Tests failed: $image" }
    }
}
Compose up -d --wait --wait-timeout 240 task-api platform-api task-worker task-scheduler task-supervisor reminder-worker gateway xhs local-web openhands napcat
Compose restart gateway
Compose up -d --wait --wait-timeout 120 gateway
& docker run --rm --network baoyan-local-appnet --env-file $envFile -e NACOS_URL=http://nacos:8848/nacos -e OPENHANDS_URL=http://local-web/agent --mount "type=bind,source=$PSScriptRoot/deploy,target=/scripts,readonly" baoyan-tasks:local python /scripts/configure-openhands.py
if ($LASTEXITCODE -ne 0) { Write-Warning 'Core services are running; configure LLM in Settings to finish Agent setup.' }
Write-Host 'URL: http://localhost:18081'
Write-Host 'Initial local password: baoyan-local-demo (unless changed in Nacos Settings)'
Write-Host 'QQ requires the account owner to scan the login QR code; XHS requires a valid personal Cookie.'
