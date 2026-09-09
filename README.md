# Bot automático IQ Option — PRACTICE o REAL

Bot educativo para Windows. Lee velas cerradas, calcula EMA 20, EMA 50 y RSI 14,
genera señales por tendencia/retroceso y puede enviar operaciones binarias. La
integración usa una API comunitaria no oficial.

## Seguridad incorporada

- La cuenta predeterminada es `PRACTICE`.
- La ejecución empieza desactivada (`ENABLE_TRADING=false`).
- Operar en `REAL` exige cuatro controles simultáneos y valida el monto máximo.
- Máximo de operaciones, pérdidas consecutivas y pérdida diaria.
- Los límites diarios sobreviven a reinicios y se reinician por día UTC.
- Riesgo por operación y pérdida diaria limitados también como porcentaje del saldo.
- La cuenta REAL queda bloqueada hasta superar una puerta estadística.
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
- `IQ_STRATEGY=trend`: admite `trend`, `support_channel` o `bollinger_reversal`.
- `MAX_DAILY_LOSS=5`: pérdida máxima en la moneda de la cuenta seleccionada.
- `MAX_RISK_PER_TRADE_PCT=1`: riesgo máximo de una operación como porcentaje del saldo; admite valores mayores que 0 y hasta 100.
- `MAX_DAILY_LOSS_PCT=3`: segundo tope diario relativo al saldo; admite valores mayores que 0 y hasta 100, y se usa el más estricto.
- `VALIDATION_MIN_TRADES=200`: muestra mínima de la versión actual antes de habilitar REAL.
- `VALIDATION_MIN_EDGE=0.02`: margen exigido sobre el punto de equilibrio (2 puntos porcentuales).
- `MIN_PAYOUT=0.85`: omite automáticamente cualquier entrada que pague menos de 85% neto.
- `RISK_TIMEZONE=America/Bogota`: zona usada para reiniciar los límites de cada día.

Los resultados quedan en `trades.csv` y el detalle técnico en `bot.log`.
El bot recorre los pares en el orden configurado y mantiene una sola operación
abierta a la vez para no exceder los límites de riesgo.
Antes de cada orden consulta el payout vigente mediante una caché de un minuto. Si la
consulta falla o el payout está por debajo de `MIN_PAYOUT`, no opera; el fallo es seguro.
En `PRACTICE`, superar `MAX_RISK_PER_TRADE_PCT` genera una advertencia pero respeta el
`IQ_AMOUNT` elegido; también prevalece el `MAX_DAILY_LOSS` absoluto configurado. En `REAL`,
los porcentajes continúan siendo bloqueos obligatorios.

Los pares normales suelen estar disponibles durante el horario del mercado Forex; los pares `-OTC` dependen de la oferta de IQ Option. No se presupone que uno esté abierto por el hecho de que el otro lo esté. Cada par se valida directamente al solicitar sus velas. Si está cerrado, no existe
o no entrega datos, se omite durante cinco minutos sin detener los demás. El bot no
usa `get_all_open_time()`, porque en `iqoptionapi 7.1.1` esa consulta también inicia
el módulo digital y puede quedar esperando o lanzar errores internos.

## Proceso de validación profesional

No se considera rentable una estrategia por unas pocas victorias. El proceso es:

1. Definir las reglas y congelar su versión; no retocarlas después de mirar cada pérdida.
2. Probar con velas históricas en orden temporal, reservando el tramo final fuera de muestra.
3. Exigir una muestra amplia y medir payout, punto de equilibrio, esperanza, profit factor,
   drawdown y el límite inferior Wilson del acierto.
4. Confirmar la misma versión en `PRACTICE`, con payouts y rechazos reales de la plataforma.
5. Considerar `REAL` solo si fuera de muestra y `PRACTICE` permanecen validados.

Evalúa las operaciones de práctica registradas:

```powershell
python performance.py trades.csv --strategy trend --version trend-v2
```

El estado solo aparece como `VALIDADA` si el PnL es positivo, se alcanza la muestra mínima
y el límite inferior al 95% de la tasa de acierto supera el punto de equilibrio por el margen
configurado. La puerta de REAL usa las últimas 200 operaciones de la versión actual, para que
una ventaja antigua no oculte un deterioro reciente. Es más exigente que mirar únicamente el
porcentaje ganador.

Para el backtest, exporta velas cerradas con las columnas `from,open,close,min,max` e indica
el payout neto observado (0.82 significa ganar 0,82 por cada 1 arriesgado):

También puedes recolectar 5.000 velas directamente, sin enviar ninguna orden:

```powershell
python collect_history.py --assets EURUSD-OTC,NZDUSD-OTC --candles 5000
```

```powershell
python backtest.py data\EURUSD-OTC_5m.csv --strategy trend --payout 0.82 --split 0.70
```

La decisión debe basarse en `OUT-OF-SAMPLE`. El simulador entra en la apertura siguiente
a la señal, trata empates como pérdida y no usa velas futuras. Un CSV no reproduce latencia,
cambios de payout, rechazos ni diferencias de cotización, por lo que después sigue siendo
obligatoria la validación en `PRACTICE`.

`research.py` compara familias de reglas predefinidas. `model_research.py` evalúa un
modelo logístico regularizado. Ambos mantienen sellado el último 20% salvo que el candidato
cumpla primero los criterios de entrenamiento y validación. Los resultados y decisiones
quedan documentados en `VALIDATION.md`.

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

### Bollinger + Estocástico + CCI (`bollinger_reversal`)

Estrategia de reversión alineada con la tendencia para velas de un minuto:

- Bandas de Bollinger: período 6 y desviación poblacional 2.
- EMA 100: el precio debe estar arriba con pendiente alcista para CALL, o abajo con
  pendiente bajista para PUT.
- Estocástico 13,3,3: cruce de giro dentro de sobreventa (≤20) o sobrecompra (≥80).
- CCI 14: debe girar desde ≤−100 para CALL o desde ≥100 para PUT.
- La vela debe cerrar fuera de la banda exterior: debajo de la inferior para CALL o encima de la superior para PUT.
- Se descartan velas con rango superior a 2 ATR.
- Vencimiento automático de 3 minutos con pendiente EMA fuerte y 4 con pendiente moderada.

Configuración:

```dotenv
IQ_STRATEGY=bollinger_reversal
IQ_TIMEFRAME_MIN=1
IQ_EXPIRATION_MIN=3
MIN_CANDLES_BETWEEN_TRADES=5
```

`IQ_EXPIRATION_MIN` funciona como respaldo; las señales de esta estrategia incluyen
su vencimiento calculado de 3 o 4 minutos. La entrada se ejecuta en la apertura
posterior a la vela que cerró fuera de la banda y confirmó todas las condiciones.

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

La CFTC y la SEC advierten que la estructura de payout puede tener esperanza negativa
incluso con resultados cercanos a 50/50 y documentan riesgos de fraude en plataformas
no registradas:
https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/fraudadv_binaryoptions.html

La selección repetida de parámetros puede producir resultados históricos que desaparecen
fuera de muestra; por eso el flujo separa desarrollo y evaluación:
https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2308659
