# setup.ps1
# Script de PowerShell para instalar Docker Desktop y Docker Compose,
# luego construir y ejecutar el contenedor Docker.

# Ejecutar el script con privilegios de administrador
if (!([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "Este script debe ejecutarse como Administrador." -ForegroundColor Red
    Exit
}

# Configurar variables
$dockerInstaller = "$env:TEMP\DockerDesktopInstaller.exe"
$dockerUrl = "https://desktop.docker.com/win/stable/Docker%20Desktop%20Installer.exe"

# Función para verificar si Docker está instalado
function Test-DockerInstalled {
    try {
        docker --version | Out-Null
        return $true
    } catch {
        return $false
    }
}

# Función para descargar Docker Desktop
function Download-DockerDesktop {
    param (
        [string]$Url,
        [string]$OutputPath
    )
    Write-Host "Descargando Docker Desktop desde $Url..." -ForegroundColor Cyan
    try {
        Invoke-WebRequest -Uri $Url -OutFile $OutputPath -UseBasicParsing
        Write-Host "Descarga completada: $OutputPath" -ForegroundColor Green
    } catch {
        Write-Host "Error al descargar Docker Desktop: $_" -ForegroundColor Red
        Exit
    }
}

# Función para instalar Docker Desktop
function Install-DockerDesktop {
    param (
        [string]$InstallerPath
    )
    Write-Host "Instalando Docker Desktop..." -ForegroundColor Cyan
    try {
        Start-Process -FilePath $InstallerPath -ArgumentList "install", "--quiet" -Wait -PassThru
        Write-Host "Instalación de Docker Desktop completada." -ForegroundColor Green
    } catch {
        Write-Host "Error durante la instalación de Docker Desktop: $_" -ForegroundColor Red
        Exit
    }
}

# Función para esperar a que Docker esté listo
function Wait-DockerReady {
    Write-Host "Esperando a que Docker Desktop inicie..." -ForegroundColor Cyan
    $maxRetries = 60
    $retryCount = 0
    while ($retryCount -lt $maxRetries) {
        if (Test-DockerInstalled) {
            Write-Host "Docker Desktop está funcionando correctamente." -ForegroundColor Green
            return
        }
        Start-Sleep -Seconds 5
        $retryCount++
        Write-Host "Esperando... ($retryCount/$maxRetries)" -ForegroundColor Yellow
    }
    Write-Host "Tiempo de espera agotado. Docker Desktop no está respondiendo." -ForegroundColor Red
    Exit
}

# Función para construir y ejecutar Docker Compose
function Run-DockerCompose {
    Write-Host "Construyendo y ejecutando los servicios con Docker Compose..." -ForegroundColor Cyan
    try {
        docker-compose up --build -d
        Write-Host "Servicios iniciados exitosamente." -ForegroundColor Green
        Write-Host "Accede a http://localhost:5000 para ver tu aplicación Flask." -ForegroundColor Green
    } catch {
        Write-Host "Error al ejecutar Docker Compose: $_" -ForegroundColor Red
        Exit
    }
}

# Verificar si Docker está instalado
if (Test-DockerInstalled) {
    Write-Host "Docker ya está instalado. Version:" -ForegroundColor Green
    docker --version
} else {
    Write-Host "Docker no está instalado. Procediendo a la descarga e instalación..." -ForegroundColor Yellow
    Download-DockerDesktop -Url $dockerUrl -OutputPath $dockerInstaller
    Install-DockerDesktop -InstallerPath $dockerInstaller
    # Eliminar el instalador después de la instalación
    Remove-Item -Path $dockerInstaller -Force
}

# Esperar a que Docker esté listo
Wait-DockerReady

# Verificar si Docker Compose está instalado
try {
    docker-compose --version | Out-Null
    Write-Host "Docker Compose está instalado. Version:" -ForegroundColor Green
    docker-compose --version
} catch {
    Write-Host "Docker Compose no está instalado o no está en el PATH." -ForegroundColor Red
    Exit
}

# Navegar al directorio del script (asumiendo que docker-compose.yml está aquí)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location -Path $scriptDir

# Construir y ejecutar Docker Compose
Run-DockerCompose

Write-Host "Proceso completado." -ForegroundColor Green
