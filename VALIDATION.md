# Registro de validación

Este archivo evita reinterpretar resultados o reutilizar un tramo final después de verlo.
Un resultado positivo aislado no autoriza operaciones reales.

## 2026-09-04 — Línea base de operaciones PRACTICE

- 23 operaciones: 12 ganadas y 11 perdidas.
- Acierto: 52,17%; punto de equilibrio observado: 54,82%.
- PnL: -3,33; profit factor: 0,90; drawdown máximo: 13,62.
- Decisión: estrategias actuales no validadas; REAL bloqueado.

## 2026-09-04 — Velas de 5 minutos

- Cinco activos y 20.000 velas por activo.
- División temporal por activo: 0–60% desarrollo, 60–80% validación,
  80–100% test final sellado.
- Payout conservador evaluado: 0,82.
- Se compararon 27 variantes predefinidas de cuatro familias: giro RSI,
  rechazo de Bollinger, reversión de racha y momentum de tendencia.
- Ninguna variante tuvo esperanza positiva simultánea en desarrollo y validación.
- Decisión: ningún candidato; el test final no se reveló.

## 2026-09-04 — Velas de 15 minutos

- Cinco activos y 20.000 velas por activo.
- Misma división 60/20/20 y mismas 27 variantes.
- Payout conservador evaluado: 0,85; la consulta en vivo mostró 0,85–0,86
  para los OTC seleccionados.
- Ninguna variante tuvo esperanza positiva simultánea en desarrollo y validación.
- Decisión: ningún candidato; el test final no se reveló.

## Regla para el próximo experimento

No se probarán más ajustes sobre estos mismos tramos con el objetivo de rescatar el resultado.
Una hipótesis nueva debe justificarse antes de ejecutarse y usar datos posteriores o activos
no usados para su confirmación. Solo después de pasar desarrollo y validación se permite una
única apertura del test final.

## 2026-09-04 — Modelo logístico regularizado

- Variables fijadas antes de evaluar: separación y pendiente EMA normalizadas por ATR,
  RSI, cuerpo, rango, posición del cierre, retornos rezagados y hora UTC cíclica.
- Se probaron cuatro penalizaciones y cinco umbrales, usando 60% para entrenar y 20%
  para seleccionar. El 20% final no intervino en entrenamiento ni selección.
- En 15 minutos, el mejor modelo con muestra suficiente obtuvo esperanza -0,0045 en
  entrenamiento y +0,0018 en validación; Wilson 95% fue 48,27%, por debajo del equilibrio.
- En 5 minutos, los modelos con validación positiva tuvieron entrenamiento negativo o
  muestras demasiado pequeñas.
- Decisión: ningún modelo elegible; los tests finales de 5 y 15 minutos no se revelaron.
