# etf-quant-lab

Plataforma Python para investigar ETFs desde España: **RESEARCH ONLY / BACKTESTING /
SIMULATED PAPER REPLAY**. Implementa un motor propio, importación offline, riesgo,
costes, benchmark y validación temporal. No envía órdenes reales ni solicita credenciales.

Historical performance does not guarantee future results.

## Instalar y ejecutar

Requiere Python 3.12+ y uv. Desde la raíz del repositorio:

```sh
uv sync
uv run etf-lab doctor
uv run etf-lab instruments
uv run etf-lab import data/sample.csv
uv run etf-lab doctor-data
uv run etf-lab backtest --strategy momentum
uv run etf-lab backtest --strategy buy-and-hold
uv run etf-lab paper --strategy momentum
uv run etf-lab walkforward --strategy momentum
uv run etf-lab report
uv run etf-lab experiments --sort expectancy
```

`uv run` evita depender de activar el entorno. También se pueden activar `.venv` y
usar `etf-lab` directamente. Las fixtures ya están incluidas; regenerar con
`uv run etf-lab fixtures`. Son sintéticas, nunca cotizaciones descargadas.
Walkforward sin argumentos usa explícitamente sample_daily.parquet, dos años sintéticos;
no pretende validar el ejemplo 5m corto. Para otros datos indicar --dataset y --config.

```sh
uv run etf-lab import data/sample_daily.parquet --timeframe 1d
uv run etf-lab optimize --evaluate-test
uv run etf-lab backtest --config config/breakout.yaml --strategy breakout
uv run ruff format --check
uv run ruff check
uv run mypy src
uv run pytest
```

Importar de nuevo sample.csv antes de usar config/breakout.yaml (5m). `--fx-file rates.csv`
para activos en otra divisa; `--actions-file actions.json` para backtest con eventos.
`--mapping mapping.json` admite nombres de columnas del usuario. Consultar esquemas
en [DATA_SOURCES](docs/DATA_SOURCES.md). No se rellenan huecos ni se arregla OHLC en silencio.

## Qué incluye

Registro ISIN/MIC/divisa y validación checksum; calendario NYSE/NASDAQ/LSE/Xetra/Euronext,
DST y medias sesiones; CSV/Parquet, metadatos/cache SQLite; features causales; momentum,
breakout, mean reversion y Buy & Hold; cash EUR, FX as-of, splits/distribuciones explícitos;
riesgo de exposición/posición/sector/pérdida diaria/drawdown; sizing fijo/%/ATR/volatilidad;
fills parciales con costes; tres escenarios por backtest; optimización temporal acotada,
walk-forward y reportes HTML/JSON/CSV con gráficos. Paper es replay histórico offline.

`data/reports/<run_id>/report.html` contiene resultados y supuestos. Junto al HTML se
guardan curva, decisiones, fills, trades, métricas y metadata con hash de dataset/config,
config benchmark, FX/eventos, versión y git commit cuando existe. `data/results.sqlite`
conserva experimentos. Exportaciones de optimization/walkforward van a data/backtests.

## Lectura responsable del resultado

El ejemplo responde si el software funciona, no si existe expectativa real positiva.
Comparar estrategia con Buy & Hold del mismo período y revisar costes y exposición.
El benchmark del reporte es ideal y con mayor asignación; para comparar costes homogéneos,
ejecutar Buy & Hold por separado. Pocos trades no prueban nada; ratios no definidos son null.
No se deducen impuestos. Una estrategia puede perder después de spread/comisiones aunque
la señal bruta parezca útil. Los defaults son supuestos experimentales no calibrados.

El catálogo actual introduce survivorship bias sin componentes históricos. Look-ahead
introduce información del futuro. Overfitting ajusta ruido, y data snooping multiplica
intentos hasta encontrar azar favorable. OOS reutilizado deja de ser final. Las pruebas
de causalidad y particiones ayudan, pero no eliminan sesgos de datos de origen.

## Documentación

- [Arquitectura](docs/ARCHITECTURE.md)
- [España/UE y documentos PRIIPs/UCITS](docs/SPAIN_AND_EU_ETFS.md)
- [Fuentes, importación, FX y calendarios](docs/DATA_SOURCES.md)
- [Backtesting, costes y límites](docs/BACKTESTING.md)
- [Estrategias y ablaciones](docs/STRATEGIES.md)
- [Notas fiscales](docs/TAX_NOTES.md)

## Límites expresos del MVP

Sin feed live/delayed, download remoto, recorder, broker real, short, leverage,
optimización masiva, ranking cross-sectional ni impuestos. `download`/`record` dan un
diagnóstico de proveedor ausente. `live` devuelve el rechazo deliberado solicitado.
Los stops se observan al cierre, no simulan órdenes intrabar. Fracciones por reverse
split, cash-in-lieu, pago diferido, microestructura y desconexiones quedan fuera.
Hay CSV descriptivos por franjas/gap; no hay atribución de trades por franja ni momentum beta.
Esta entrega prioriza el MVP offline; no declara implementadas todas las extensiones.

Resultados y comprobaciones de esta entrega: [DELIVERY.md](docs/DELIVERY.md).
