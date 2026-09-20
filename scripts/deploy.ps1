#Requires -Version 5.1
<#
.SYNOPSIS
  Deploy Serah to the shared DigitalOcean droplet (Compose + Caddy HTTPS).

.DESCRIPTION
  Packs this working tree, copies it to /opt/serah, creates the dedicated
  Postgres role/database on Shortlisted's instance, starts only Serah
  containers (backend, frontend, Qdrant), and reloads Caddy with the
  serah.useshortlisted.app site. Does not recreate Postgres, MinIO, Redis,
  or Caddy.

  Secrets stay on the VM. An existing infra/compose/.env is kept unless -SyncEnv.
  Prefer SSH keys so OpenSSH does not prompt for a password twice.

  Deploy Shortlisted infra first so the `shared` Docker network and Caddy
  import exist.

.PARAMETER Target
  SSH host (IP or DNS). Default: DEPLOY_HOST or 165.22.93.12.

.PARAMETER User
  SSH user. Default: DEPLOY_USER or root.

.PARAMETER RemoteRoot
  Directory on the VM. Default: /opt/serah.

.PARAMETER IdentityFile
  Optional private key (ssh -i). Default: DEPLOY_SSH_KEY.

.PARAMETER Port
  SSH port. Default: 22.

.PARAMETER SyncEnv
  Upload local infra/compose/.env and replace the remote file.

.PARAMETER NoCache
  Rebuild images with --no-cache.

.PARAMETER SkipUpload
  Do not pack or copy files; only run Compose on what is already on the VM.

.PARAMETER PackOnly
  Write the archive locally and stop (no SSH).

.PARAMETER Status
  Print remote Compose status and health, then exit.

.EXAMPLE
  .\scripts\deploy.ps1

.EXAMPLE
  .\scripts\deploy.ps1 -SyncEnv -NoCache
#>
[CmdletBinding()]
param(
    [string]$Target = $(if ($env:DEPLOY_HOST) { $env:DEPLOY_HOST } else { "165.22.93.12" }),
    [string]$User = $(if ($env:DEPLOY_USER) { $env:DEPLOY_USER } else { "root" }),
    [string]$RemoteRoot = $(if ($env:DEPLOY_REMOTE) { $env:DEPLOY_REMOTE } else { "/opt/serah" }),
    [string]$IdentityFile = $(if ($env:DEPLOY_SSH_KEY) { $env:DEPLOY_SSH_KEY } else { "" }),
    [int]$Port = 22,
    [switch]$SyncEnv,
    [switch]$NoCache,
    [switch]$SkipUpload,
    [switch]$PackOnly,
    [switch]$Status
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ComposeDir = Join-Path $RepoRoot "infra\compose"
$LocalEnv = Join-Path $ComposeDir ".env"
$TarPath = Join-Path $env:TEMP "serah-deploy.tar.gz"
$StageDir = Join-Path $env:TEMP "serah-deploy-stage"
$RemoteSh = Join-Path $env:TEMP "serah-hosted-up.sh"

function Test-Command([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-SshArgs {
    $sshArgs = @(
        "-p", "$Port",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=60"
    )
    if ($IdentityFile) {
        if (-not (Test-Path -LiteralPath $IdentityFile)) {
            throw "Identity file not found: $IdentityFile"
        }
        $sshArgs += @("-i", $IdentityFile)
    }
    return $sshArgs
}

function Invoke-Ssh([string]$RemoteCommand) {
    $sshArgs = Get-SshArgs
    & ssh @sshArgs "${User}@${Target}" $RemoteCommand
    if ($LASTEXITCODE -ne 0) {
        throw "ssh failed with exit code $LASTEXITCODE"
    }
}

function Send-File([string]$LocalPath, [string]$RemotePath) {
    $scpArgs = @(
        "-P", "$Port",
        "-o", "StrictHostKeyChecking=accept-new"
    )
    if ($IdentityFile) {
        $scpArgs += @("-i", $IdentityFile)
    }
    & scp @scpArgs $LocalPath "${User}@${Target}:$RemotePath"
    if ($LASTEXITCODE -ne 0) {
        throw "scp failed with exit code $LASTEXITCODE ($LocalPath)"
    }
}

function Copy-Tree {
    param(
        [Parameter(Mandatory)][string]$From,
        [Parameter(Mandatory)][string]$To,
        [string[]]$ExcludeDirs = @(),
        [string[]]$ExcludeFiles = @()
    )
    if (-not (Test-Path -LiteralPath $From)) {
        throw "Missing path: $From"
    }
    New-Item -ItemType Directory -Force -Path $To | Out-Null
    $robocopyArgs = @(
        $From, $To, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NC", "/NS", "/NP"
    )
    if ($ExcludeDirs.Count -gt 0) {
        $robocopyArgs += "/XD"
        $robocopyArgs += $ExcludeDirs
    }
    if ($ExcludeFiles.Count -gt 0) {
        $robocopyArgs += "/XF"
        $robocopyArgs += $ExcludeFiles
    }
    & robocopy @robocopyArgs | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed with exit code $LASTEXITCODE ($From -> $To)"
    }
}

function Write-UnixFile([string]$Path, [string]$Contents) {
    $unix = $Contents -replace "`r`n", "`n" -replace "`r", "`n"
    if (-not $unix.EndsWith("`n")) {
        $unix += "`n"
    }
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($Path, $unix, $utf8)
}

function Get-HostedUpScript {
    $script = @'
#!/bin/bash
# Applied on the VM by scripts/deploy.ps1.
set -euo pipefail
REMOTE_ROOT='__REMOTE_ROOT__'
NO_CACHE='__NO_CACHE__'
SYNC_ENV='__SYNC_ENV__'
SKIP_UPLOAD='__SKIP_UPLOAD__'
TAR=/tmp/serah-deploy.tar.gz
COMPOSE="$REMOTE_ROOT/infra/compose"
SHORTLISTED_COMPOSE=/opt/shortlisted/infra/compose

if [ "$SKIP_UPLOAD" != "1" ]; then
  if [ ! -f "$TAR" ]; then
    echo "Missing $TAR" >&2
    exit 1
  fi
  ENV_BAK=""
  if [ "$SYNC_ENV" != "1" ] && [ -f "$REMOTE_ROOT/infra/compose/.env" ]; then
    cp "$REMOTE_ROOT/infra/compose/.env" /tmp/serah.env.bak
    ENV_BAK=1
  fi
  rm -rf "$REMOTE_ROOT"
  mkdir -p "$REMOTE_ROOT"
  tar -xzf "$TAR" -C "$REMOTE_ROOT"
  rm -f "$TAR"
  if [ -n "$ENV_BAK" ]; then
    mkdir -p "$REMOTE_ROOT/infra/compose"
    mv /tmp/serah.env.bak "$REMOTE_ROOT/infra/compose/.env"
    echo "Kept existing infra/compose/.env on the VM."
  fi
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed. Deploy Shortlisted infra first." >&2
  exit 1
fi
docker --version
docker compose version

docker network inspect shared >/dev/null 2>&1 || docker network create shared
mkdir -p /opt/caddy/sites

if [ ! -d "$COMPOSE" ]; then
  echo "Missing $COMPOSE — upload the app first." >&2
  exit 1
fi
cd "$COMPOSE"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Set SECRET_KEY, SERAH_DB_PASSWORD, OPENROUTER_API_KEY."
fi

if [ ! -d "$SHORTLISTED_COMPOSE" ]; then
  echo "Shortlisted compose not found at $SHORTLISTED_COMPOSE. Deploy Shortlisted infra first." >&2
  exit 1
fi

load_env_var() {
  local name="$1"
  local line
  line=$(grep -E "^${name}=" .env | tail -n 1 || true)
  line="${line#${name}=}"
  line="${line%$'\r'}"
  case "$line" in
    \"*\") line="${line#\"}"; line="${line%\"}" ;;
    \'*\') line="${line#\'}"; line="${line%\'}" ;;
  esac
  printf '%s' "$line"
}

SERAH_DB_PASSWORD="$(load_env_var SERAH_DB_PASSWORD)"
if [ -z "$SERAH_DB_PASSWORD" ]; then
  echo "SERAH_DB_PASSWORD is empty in $COMPOSE/.env" >&2
  exit 1
fi
PASS_ESC=$(printf '%s' "$SERAH_DB_PASSWORD" | sed "s/'/''/g")

echo "Ensuring Postgres role serah and database applicant_companion..."
cd "$SHORTLISTED_COMPOSE"
docker compose -f docker-compose.yml -f docker-compose.hosted.yml exec -T postgres \
  psql -U shortlisted -d postgres -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'serah') THEN
    CREATE ROLE serah LOGIN PASSWORD '${PASS_ESC}';
  ELSE
    ALTER ROLE serah WITH LOGIN PASSWORD '${PASS_ESC}';
  END IF;
END
\$\$;
SQL
if ! docker compose -f docker-compose.yml -f docker-compose.hosted.yml exec -T postgres \
  psql -U shortlisted -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'applicant_companion'" | grep -q 1; then
  docker compose -f docker-compose.yml -f docker-compose.hosted.yml exec -T postgres \
    psql -U shortlisted -d postgres -v ON_ERROR_STOP=1 \
    -c "CREATE DATABASE applicant_companion OWNER serah;"
fi
docker compose -f docker-compose.yml -f docker-compose.hosted.yml exec -T postgres \
  psql -U shortlisted -d applicant_companion -v ON_ERROR_STOP=1 \
  -c "GRANT ALL ON SCHEMA public TO serah; ALTER SCHEMA public OWNER TO serah;"

cd "$COMPOSE"
if [ "$NO_CACHE" = "1" ]; then
  docker compose -f docker-compose.hosted.yml build --no-cache
fi
docker compose -f docker-compose.hosted.yml up --pull missing --build -d --remove-orphans

echo "Waiting for API health on loopback :8010..."
ok=0
for _ in {1..60}; do
  if curl -fsS --max-time 3 http://127.0.0.1:8010/api/health >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 5
done
if [ "$ok" != "1" ]; then
  echo "API did not become healthy. Recent backend logs:" >&2
  docker compose -f docker-compose.hosted.yml logs --tail=80 backend >&2
  exit 1
fi

echo "API http://127.0.0.1:8010/api/health OK"
docker compose -f docker-compose.hosted.yml ps

echo "Installing Caddy site serah.useshortlisted.app..."
cp "$COMPOSE/Caddyfile.serah" /opt/caddy/sites/serah.caddy
sed -i 's/\r$//' /opt/caddy/sites/serah.caddy
cd "$SHORTLISTED_COMPOSE"
docker compose -f docker-compose.yml -f docker-compose.hosted.yml exec -T caddy \
  caddy reload --config /etc/caddy/Caddyfile

curl -fsS --max-time 15 https://serah.useshortlisted.app/api/health || echo "Public HTTPS health not ready yet (cert or DNS). Loopback API is healthy."
echo "Product: https://serah.useshortlisted.app"
'@
    $noCache = $(if ($NoCache) { "1" } else { "0" })
    $sync = $(if ($SyncEnv) { "1" } else { "0" })
    $skip = $(if ($SkipUpload) { "1" } else { "0" })
    return $script.
        Replace("__REMOTE_ROOT__", $RemoteRoot).
        Replace("__NO_CACHE__", $noCache).
        Replace("__SYNC_ENV__", $sync).
        Replace("__SKIP_UPLOAD__", $skip)
}

function New-DeployArchive {
    Write-Host "Packing working tree (no node_modules, tests, or caches)..."
    if (Test-Path -LiteralPath $StageDir) {
        Remove-Item -LiteralPath $StageDir -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $StageDir | Out-Null

    Copy-Tree -From (Join-Path $RepoRoot "backend") -To (Join-Path $StageDir "backend") -ExcludeDirs @(
        ".venv", ".mypy_cache", ".ruff_cache", ".pytest_cache", "__pycache__", "tests"
    ) -ExcludeFiles @(".env", "dev.db")

    Copy-Tree -From (Join-Path $RepoRoot "frontend") -To (Join-Path $StageDir "frontend") -ExcludeDirs @(
        "node_modules", "dist", "tests"
    ) -ExcludeFiles @(".env", ".env.local", "tsconfig.tsbuildinfo")

    $envExclude = @()
    if (-not $SyncEnv) {
        $envExclude = @(".env")
    }
    Copy-Tree -From $ComposeDir -To (Join-Path $StageDir "infra\compose") -ExcludeFiles $envExclude

    if ($SyncEnv) {
        if (-not (Test-Path -LiteralPath $LocalEnv)) {
            throw "-SyncEnv requires $LocalEnv"
        }
        Copy-Item $LocalEnv (Join-Path $StageDir "infra\compose\.env") -Force
        Write-Host "Included local infra/compose/.env in the archive."
    }

    Write-UnixFile (Join-Path $StageDir ".hosted-up.sh") (Get-HostedUpScript)

    if (Test-Path -LiteralPath $TarPath) {
        Remove-Item -LiteralPath $TarPath -Force
    }
    & tar -czf $TarPath -C $StageDir .
    if ($LASTEXITCODE -ne 0) {
        throw "tar failed with exit code $LASTEXITCODE"
    }
    $sizeMb = [math]::Round((Get-Item $TarPath).Length / 1MB, 1)
    Write-Host "Archive: $TarPath ($sizeMb MB)"
}

if (-not (Test-Command "tar")) {
    throw "tar is required (bundled with Windows 10+)."
}
if (-not $PackOnly) {
    if (-not (Test-Command "ssh") -or -not (Test-Command "scp")) {
        throw "OpenSSH ssh/scp not found. Install the OpenSSH Client optional feature, or run with -PackOnly."
    }
}

Write-Host "Serah deploy  (repo: $RepoRoot)"
Write-Host "Target: ${User}@${Target}:${RemoteRoot}"

if ($Status) {
    Invoke-Ssh "cd '$RemoteRoot/infra/compose' && docker compose -f docker-compose.hosted.yml ps && curl -fsS http://127.0.0.1:8010/api/health && echo && curl -fsS --max-time 15 https://serah.useshortlisted.app/api/health || true"
    return
}

if (-not $SkipUpload) {
    New-DeployArchive
    if ($PackOnly) {
        Write-Host "Pack only. Archive is at $TarPath"
        return
    }
    Write-Host "Uploading archive..."
    Send-File $TarPath "/tmp/serah-deploy.tar.gz"
}

Write-UnixFile $RemoteSh (Get-HostedUpScript)
Send-File $RemoteSh "/tmp/serah-hosted-up.sh"
Write-Host "Building and starting hosted Compose (this can take several minutes)..."
Invoke-Ssh "bash /tmp/serah-hosted-up.sh && rm -f /tmp/serah-hosted-up.sh"

Write-Host ""
Write-Host "Deploy finished."
Write-Host "  URL     https://serah.useshortlisted.app"
Write-Host "  Health  https://serah.useshortlisted.app/api/health"
Write-Host "  Logins  SEED_USER_EMAIL from infra/compose/.env on the VM"
Write-Host "Re-run:   .\scripts\deploy.ps1"
Write-Host "Status:   .\scripts\deploy.ps1 -Status"
