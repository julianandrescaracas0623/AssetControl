<#
.SYNOPSIS
  Enciende AssetControl en modo desarrollo en tu PC, paso a paso, y dice qué falla.

.DESCRIPTION
  1. Revisa que estén Docker, uv, Node y el archivo .env.
  2. Enciende la base (Docker) y espera a que esté sana.
  3. Instala las dependencias del backend (uv sync).
  4. Aplica las migraciones pendientes (alembic upgrade head).
  5. Revisa las conexiones del .env (sin mostrar contraseñas).
  6. Construye y enciende la API (Docker) y espera a que responda.
  7. Instala las dependencias de la web si hace falta y abre Vite en http://localhost:5173.

  Guía completa: docs/10-entorno-local.md.

.EXAMPLE
  .\scripts\dev.ps1            # todo, y deja la web corriendo (Ctrl + C para salir)
  .\scripts\dev.ps1 -SinWeb    # solo base, migraciones y API
  .\scripts\dev.ps1 -Movil     # además, la web con HTTPS en tu red Wi-Fi para abrirla en el teléfono
  .\scripts\dev.ps1 -Parar     # apaga la base y la API (los datos se conservan)
#>
param(
  [switch]$SinWeb,
  [switch]$Movil,
  [switch]$Parar
)

$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

function Paso([string]$numero, [string]$texto) { Write-Host "`n[$numero] $texto" -ForegroundColor Cyan }
function Bien([string]$texto) { Write-Host "  OK  $texto" -ForegroundColor Green }
function Aviso([string]$texto) { Write-Host "  !   $texto" -ForegroundColor Yellow }
function Falla([string]$texto) {
  Write-Host "  MAL $texto" -ForegroundColor Red
  Write-Host "`nNo se completó. Revisa el mensaje de arriba y docs/10-entorno-local.md (sección 14)." -ForegroundColor Red
  exit 1
}

if ($Parar) {
  docker compose stop
  if ($LASTEXITCODE -ne 0) { Falla 'docker compose stop falló.' }
  Bien 'Base y API apagadas. Los datos se conservan.'
  exit 0
}

Paso '1/7' 'Programas y archivo .env'
foreach ($programa in 'docker', 'uv', 'node', 'npm') {
  if (-not (Get-Command $programa -ErrorAction SilentlyContinue)) { Falla "No está instalado «$programa» (docs/10, sección 1)." }
}
$nodeMayor = [int]((node --version).TrimStart('v').Split('.')[0])
if ($nodeMayor -lt 24) { Falla "La web pide Node 24 o más nuevo y tienes $(node --version): instala la versión LTS desde nodejs.org." }
if (-not (Test-Path (Join-Path $raiz '.env'))) { Falla 'No existe el archivo .env en la raíz del proyecto (docs/10, sección 2).' }
docker info *> $null
if ($LASTEXITCODE -ne 0) { Falla 'Docker Desktop no está encendido: ábrelo y espera a que diga «Engine running».' }
Bien 'Docker, uv, Node y .env listos.'

Paso '2/7' 'Base de datos (Docker)'
docker compose up -d db
if ($LASTEXITCODE -ne 0) { Falla 'No se pudo encender la base (docker compose up -d db).' }
$estado = ''
for ($i = 0; $i -lt 60; $i++) {
  $id = (docker compose ps -q db | Select-Object -First 1)
  if ($id) { $estado = (docker inspect --format '{{.State.Health.Status}}' $id 2>$null) }
  if ($estado -eq 'healthy') { break }
  Start-Sleep -Seconds 2
}
if ($estado -ne 'healthy') {
  docker compose logs db --tail 30
  Falla "La base no quedó sana (estado: «$estado»). Arriba están sus últimos mensajes."
}
Bien 'La base está sana.'

Paso '3/7' 'Dependencias del backend (uv sync)'
Push-Location (Join-Path $raiz 'backend')
try {
  uv sync
  if ($LASTEXITCODE -ne 0) { Falla 'uv sync falló.' }
  Bien 'Dependencias del backend instaladas.'

  Paso '4/7' 'Migraciones (alembic upgrade head)'
  uv run --env-file ../.env alembic upgrade head
  if ($LASTEXITCODE -ne 0) { Falla 'Las migraciones fallaron: revisa MIGRATION_DATABASE_URL y APP_DB_USER en .env.' }
  Bien 'La base está en la última migración.'

  Paso '5/7' 'Conexiones del .env'
  uv run --env-file ../.env flask --app app revisar-conexiones
  if ($LASTEXITCODE -ne 0) {
    # Supabase sin migrar o sin configurar no impide trabajar en local.
    Aviso 'Alguna conexión dice MAL (si es solo SUPABASE_*, puedes seguir en local).'
  } else {
    Bien 'Todas las conexiones configuradas responden.'
  }
} finally {
  Pop-Location
}

Paso '6/7' 'API (Docker)'
docker compose up -d --build api
if ($LASTEXITCODE -ne 0) { Falla 'No se pudo construir o encender la API (docker compose up -d --build api).' }
$lista = $false
for ($i = 0; $i -lt 45; $i++) {
  try {
    $respuesta = Invoke-WebRequest -Uri 'http://127.0.0.1:5000/ready' -UseBasicParsing -TimeoutSec 3
    if ($respuesta.StatusCode -eq 200) { $lista = $true; break }
  } catch { }
  Start-Sleep -Seconds 2
}
if (-not $lista) {
  docker compose logs api --tail 40
  Falla 'La API no respondió en http://127.0.0.1:5000/ready. Arriba están sus últimos mensajes.'
}
Bien 'La API responde en http://127.0.0.1:5000.'

if ($SinWeb) {
  Write-Host "`nListo: base y API encendidas. Para la web: cd web; npm run dev" -ForegroundColor Green
  exit 0
}

Paso '7/7' 'Web (Vite)'
Push-Location (Join-Path $raiz 'web')
try {
  $marca = Join-Path 'node_modules' '.package-lock.json'
  $instalar = -not (Test-Path $marca)
  if (-not $instalar) { $instalar = (Get-Item 'package-lock.json').LastWriteTime -gt (Get-Item $marca).LastWriteTime }
  if ($instalar) {
    npm ci
    if ($LASTEXITCODE -ne 0) { Falla 'npm ci falló.' }
  }
  Bien 'Dependencias de la web listas.'
  if ($Movil) {
    # La cámara del teléfono solo funciona con HTTPS: Vite usa un certificado de desarrollo
    # y se abre a la red local (spec 004, T10). Solo desarrollo.
    $env:VITE_HTTPS = '1'
    $ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
      Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.PrefixOrigin -ne 'WellKnown' } |
      Select-Object -ExpandProperty IPAddress
    Write-Host "`nEn el teléfono (mismo Wi-Fi), abre: " -ForegroundColor Green -NoNewline
    Write-Host (($ips | ForEach-Object { "https://$($_):5173" }) -join '  o  ') -ForegroundColor Green
    Write-Host 'Acepta el aviso del certificado. Si Windows pregunta por el firewall, permite «Redes privadas».' -ForegroundColor Green
  } else {
    Remove-Item Env:VITE_HTTPS -ErrorAction SilentlyContinue
  }
  Write-Host "`nAbre http://localhost:5173 (Ctrl + C aquí para apagar la web; la base y la API siguen: .\scripts\dev.ps1 -Parar)." -ForegroundColor Green
  npm run dev
} finally {
  Pop-Location
}
