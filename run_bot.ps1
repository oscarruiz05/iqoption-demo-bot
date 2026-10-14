# Ejecuta el bot y lo reinicia si el vigilante lo terminó por un bloqueo de la API
# (código de salida 3). Cualquier otro final, incluido Ctrl+C, detiene el script.
#   powershell -ExecutionPolicy Bypass -File .\run_bot.ps1

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
Push-Location $PSScriptRoot
try {
    do {
        & $python (Join-Path $PSScriptRoot "main.py")
        $code = $LASTEXITCODE
        if ($code -eq 3) {
            Write-Host "$(Get-Date -Format s) | Bot reiniciado por el vigilante; nuevo intento en 10 s"
            Start-Sleep -Seconds 10
        }
    } while ($code -eq 3)
}
finally {
    Pop-Location
}
