# Bot automático IQ Option — solo PRACTICE

Bot educativo para Windows. Lee velas cerradas, calcula EMA 20, EMA 50 y RSI 14,
genera señales por tendencia/retroceso y puede enviar operaciones binarias a la
cuenta de práctica. La integración usa una API comunitaria no oficial.

## Seguridad incorporada

- Selecciona `PRACTICE` directamente en el código; no existe opción configurable para REAL.
- La ejecución empieza desactivada (`ENABLE_TRADING=false`).
- Máximo de operaciones, pérdidas consecutivas y pérdida diaria.
- Una sola operación por vela; sin martingala.
- Credenciales en `.env`, excluidas de Git.

## Instalación en Windows (PowerShell)

```powershell
cd iqoption-demo-bot
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

La dependencia comunitaria de IQ Option instala por sí misma la versión antigua
`websocket-client==0.56` que necesita. No la actualices de forma independiente,
porque impediría resolver o podría romper la conexión de esta API no oficial.

Completa tu correo y contraseña en `.env`. Para la primera conexión deja:

```dotenv
ENABLE_TRADING=false
```

Ejecuta en modo observación:

```powershell
python main.py
```

Cuando veas `Conectado exclusivamente a PRACTICE`, detén con `Ctrl+C`, cambia a
`ENABLE_TRADING=true` y vuelve a ejecutar. Empieza con `IQ_AMOUNT=1`.

## Configuración inicial

- `IQ_ASSET=AUDCAD-OTC`: nombre del activo tal como lo espera la API.
- `IQ_TIMEFRAME_MIN=5`: velas de cinco minutos.
- `IQ_EXPIRATION_MIN=5`: vencimiento de cinco minutos.
- `MAX_DAILY_LOSS=5`: pérdida máxima en la moneda mostrada por la cuenta demo.

Los resultados quedan en `trades.csv` y el detalle técnico en `bot.log`.

## Pruebas

```powershell
python -m unittest -v
```

## Advertencias

La API puede dejar de funcionar cuando IQ Option cambie su plataforma. Nunca
compartas el `.env`, no reutilices esa contraseña en otros servicios y no ejecutes
robots desconocidos. Que funcione técnicamente no demuestra que la estrategia sea
rentable; evalúa al menos 100–200 operaciones demo y el payout antes de modificarla.
