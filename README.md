# Bot automático IQ Option — PRACTICE o REAL

Bot educativo para Windows. Lee velas cerradas, calcula EMA 20, EMA 50 y RSI 14,
genera señales por tendencia/retroceso y puede enviar operaciones binarias. La
integración usa una API comunitaria no oficial.

## Seguridad incorporada

- La cuenta predeterminada es `PRACTICE`.
- La ejecución empieza desactivada (`ENABLE_TRADING=false`).
- Operar en `REAL` exige cuatro controles simultáneos y valida el monto máximo.
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

## Cuenta PRACTICE

Para observar señales sin enviar órdenes:

```dotenv
IQ_ACCOUNT=PRACTICE
ENABLE_TRADING=false
```

Para operar únicamente con saldo de práctica:

```dotenv
IQ_ACCOUNT=PRACTICE
ENABLE_TRADING=true
```

Ejecuta con `python main.py`. El registro debe mostrar `Conectado a PRACTICE`.

## Cambio protegido a cuenta REAL

Primero prueba la conexión real sin enviar órdenes:

```dotenv
IQ_ACCOUNT=REAL
ENABLE_TRADING=false
ENABLE_REAL_TRADING=false
REAL_TRADING_CONFIRMATION=
MAX_REAL_AMOUNT=1
```

Para permitir órdenes reales deben coincidir todos estos valores:

```dotenv
IQ_ACCOUNT=REAL
IQ_AMOUNT=1
ENABLE_TRADING=true
ENABLE_REAL_TRADING=true
REAL_TRADING_CONFIRMATION=ACEPTO_RIESGO_REAL
MAX_REAL_AMOUNT=1
```

`IQ_AMOUNT` nunca puede superar `MAX_REAL_AMOUNT` en modo real. Si falta un
control, la frase no coincide o el monto excede el límite, el bot termina antes
de conectarse. Al arrancar en REAL muestra una advertencia visible. Para volver
a demo cambia `IQ_ACCOUNT=PRACTICE`; conviene además restaurar
`ENABLE_REAL_TRADING=false` y borrar la confirmación.

## Configuración inicial

- `IQ_ASSETS`: admite simultáneamente pares normales y OTC; por ejemplo, `EURUSD,EURUSD-OTC,GBPUSD,GBPUSD-OTC`.
- `IQ_TIMEFRAME_MIN=5`: velas de cinco minutos.
- `IQ_EXPIRATION_MIN=5`: vencimiento de cinco minutos.
- `IQ_STRATEGY=trend`: admite `trend` o `support_channel`.
- `MAX_DAILY_LOSS=5`: pérdida máxima en la moneda de la cuenta seleccionada.

Los resultados quedan en `trades.csv` y el detalle técnico en `bot.log`.
El bot recorre los pares en el orden configurado y mantiene una sola operación
abierta a la vez para no exceder los límites de riesgo.

Los pares normales suelen estar disponibles durante el horario del mercado Forex; los pares `-OTC` dependen de la oferta de IQ Option. No se presupone que uno esté abierto por el hecho de que el otro lo esté. Cada par se valida directamente al solicitar sus velas. Si está cerrado, no existe
o no entrega datos, se omite durante cinco minutos sin detener los demás. El bot no
usa `get_all_open_time()`, porque en `iqoptionapi 7.1.1` esa consulta también inicia
el módulo digital y puede quedar esperando o lanzar errores internos.

## Filtros de entrada

Una señal de tendencia necesita confluencia de todas estas condiciones:

- ADX 14 de al menos 22 y dirección DI coherente con CALL o PUT.
- Separación EMA 20/50 y pendiente EMA 20 normalizadas mediante ATR 14.
- Retroceso hasta EMA 20 mediante una vela contraria a la tendencia.
- Confirmación que recupere la apertura del retroceso y cierre nuevamente del lado de EMA 20.
- Cuerpo de confirmación de al menos 60% y cierre en el 20% extremo de la vela.
- RSI avanzando a favor, entre 52–60 para CALL o 40–48 para PUT.
- Rango entre 0,55 y 1,60 veces la mediana, evitando velas sin movimiento o explosivas.
- Precio no extendido más de 0,8 ATR respecto a EMA 20.

Después de completar una operación, el mismo par espera
`MIN_CANDLES_BETWEEN_TRADES=5` antes de poder volver a entrar. Estos filtros
reducen considerablemente la frecuencia; no garantizan rentabilidad y deben
evaluarse con una muestra amplia en PRACTICE.

### Soportes y canales (`support_channel`)

Esta estrategia busca rebotes, no rupturas. Requiere:

- Soporte o resistencia formado por al menos dos pivotes históricos cercanos.
- Contacto simultáneo con el nivel y el límite del canal de regresión.
- Canal estable, sin una pendiente extrema.
- Vela de rechazo con mecha de al menos 1,2 veces el cuerpo.
- Cierre nuevamente dentro del nivel para descartar una ruptura.
- RSI girando arriba entre 30–50 para CALL o abajo entre 50–70 para PUT.
- Vela no superior a 1,8 veces el rango mediano reciente.

Para probarla:

```dotenv
IQ_STRATEGY=support_channel
IQ_TIMEFRAME_MIN=5
IQ_EXPIRATION_MIN=5
IQ_AMOUNT=1
```

`trades.csv` incluye la columna `strategy`. Si ya existe un archivo antiguo,
se migra automáticamente y sus operaciones anteriores se marcan como `trend`.

## Pruebas

```powershell
python -m unittest -v
```

## Advertencias

La API puede dejar de funcionar cuando IQ Option cambie su plataforma. Nunca
compartas el `.env`, no reutilices esa contraseña y no ejecutes robots desconocidos.
Las opciones binarias pueden causar la pérdida total de cada operación. Que el bot
funcione técnicamente no demuestra que la estrategia sea rentable; valida una
muestra amplia en PRACTICE antes de considerar dinero real.
