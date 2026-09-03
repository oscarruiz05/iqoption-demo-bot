# Bot automático IQ Option — solo PRACTICE

Bot educativo para Windows. Lee velas cerradas, calcula EMA 20, EMA 50 y RSI 14,
genera señales por tendencia/retroceso y puede enviar operaciones binarias a la
cuenta de práctica. La integración usa una API comunitaria no oficial.

## Seguridad incorporada

- Selecciona `PRACTICE` directamente en el código; no existe opción configurable para REAL.
- La ejecución empieza desactivada (`ENABLE_TRADING=false`).
- Máximo de operaciones, pérdidas consecutivas y pérdida diaria.
- Una sola operación por vela y por activo; sin martingala.
- Varios pares configurables mediante una lista separada por comas.
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

- `IQ_ASSETS=AUDCAD-OTC,EURUSD-OTC,GBPUSD-OTC,EURGBP-OTC,EURJPY-OTC,GBPJPY-OTC,USDJPY-OTC,AUDUSD-OTC,NZDUSD-OTC,USDCAD-OTC`: pares separados por comas,
  escritos como los espera la API. Se eliminan espacios, vacíos y duplicados.
- `IQ_TIMEFRAME_MIN=5`: velas de cinco minutos.
- `IQ_EXPIRATION_MIN=5`: vencimiento de cinco minutos.
- `MAX_DAILY_LOSS=5`: pérdida máxima en la moneda mostrada por la cuenta demo.

Los resultados quedan en `trades.csv` y el detalle técnico en `bot.log`.
El bot recorre los pares en el orden configurado y mantiene una sola operación
abierta a la vez para no exceder los límites de riesgo.

Antes de analizarlos, consulta cuáles están abiertos para opciones turbo/binarias.
Los cerrados o no disponibles se omiten y la lista se actualiza cada 30 minutos.
La consulta completa de mercados es deliberadamente poco frecuente porque es una
operación pesada en la API comunitaria.

## Filtros de entrada

Una señal necesita confluencia de todas estas condiciones:

- EMA 20 y EMA 50 separadas y con pendiente consistente durante varias velas.
- Retroceso de la vela anterior hasta la zona de EMA 20.
- Confirmación que cierre de nuevo del lado de la tendencia.
- Cuerpo de confirmación de al menos 55% del rango y cierre cerca del extremo.
- RSI avanzando a favor, entre 48–62 para CALL o 38–52 para PUT.
- Rango de confirmación no superior a 1,8 veces la mediana reciente.

Estos filtros reducen la frecuencia de entradas; no garantizan mayor rentabilidad.
Deben evaluarse con una muestra amplia en PRACTICE.

## Pruebas

```powershell
python -m unittest -v
```

## Advertencias

La API puede dejar de funcionar cuando IQ Option cambie su plataforma. Nunca
compartas el `.env`, no reutilices esa contraseña en otros servicios y no ejecutes
robots desconocidos. Que funcione técnicamente no demuestra que la estrategia sea
rentable; evalúa al menos 100–200 operaciones demo y el payout antes de modificarla.
