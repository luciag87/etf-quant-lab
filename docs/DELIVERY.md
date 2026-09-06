# Entrega verificada: etf-quant-lab

Implementación del MVP offline, con extensiones breakout/mean reversion y optimización acotada. No representa la totalidad de las extensiones propuestas. No hay trading real ni feed live.

## Arquitectura y archivos

CSV/Parquet → validación/calendarios → features → Strategy → Signal → RiskManager → OrderIntent → PaperBroker → Portfolio → Analytics/reportes. Backtest y paper replay comparten motor.

```text
etf-quant-lab/
  pyproject.toml, uv.lock, README.md, .env.example, .gitignore
  config/          universo y 5 configuraciones
  docs/            arquitectura, fuentes, España/UE, metodología, estrategias, fiscalidad
  src/etf_lab/
    cli.py, config.py, models.py
    instruments/   registro/resolución
    data/          providers, importación, validación, calendarios, FX, eventos, fixtures
    features/      pipeline causal e HistoryView
    strategies/    momentum, Buy & Hold, breakout, mean reversion
    execution/     protocolo y PaperBroker
    portfolio/     posición, ledger, P&L
    risk/          sizing y límites
    backtest/      motor, optimizador, walk-forward
    analytics/     métricas, bootstrap, gaps/franjas, reportes
    storage/       SQLite
  tests/           unit, integration, fixtures (8 Parquet)
  scripts/verify.py
  data/            CSV 5m y Parquet diario sintéticos; ejecuciones de ejemplo
```

## Fuentes y España/UE

Investigados Alpha Vantage, Databento, BCE, iShares y exchange_calendars. Fuentes oficiales enlazadas en DATA_SOURCES.md y SPAIN_AND_EU_ETFS.md. Seleccionado CSV/Parquet porque permite funcionar sin claves, con procedencia controlada. No se inventan endpoints ni se presenta una fuente gratuita como feed ejecutable.

PRIIPs exige documentación aplicable; UCITS no determina por sí mismo disponibilidad. researchable está separado de potentially_tradeable=unknown. CSPX USD/LSE y SXR8 EUR/Xetra se registran con ISIN IE00B5BMR087 a partir del emisor. Identidad ISIN:MIC:currency; ticker sólo alias. known_from limita uso histórico del catálogo actual. DEMO es un instrumento sintético.

## Comandos

Desde la carpeta del proyecto (Python 3.12+ y uv):

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
uv run etf-lab optimize --dataset data/sample_daily.parquet --config config/daily.yaml --evaluate-test
uv run etf-lab report
uv run etf-lab experiments
uv run python scripts/verify.py
```

Paper es replay histórico offline, no streaming. Walkforward por defecto usa dos años diarios sintéticos, distinto dataset del ejemplo 5m. Para series propias usar --dataset y --config.

## Verificación ejecutada

uv sync: correcto, lock incluido. Ruff format/check: correcto. mypy: correcto en 36 archivos fuente. pytest: **54 passed**, offline. Log: data/backtests/quality-gates.txt. Incluye pruebas de calendario/DST/media sesión, seis timeframes, ISIN, duplicados/OHLC, features, fills/latencia/cash, stops/profit, FX futuro, splits/distribuciones, causalidad de precios/volumen, multiinstrumento, split temporal, aislamiento TEST, determinismo y CLI sin live.

## Ejemplo intradía: sólo datos sintéticos

DEMO EUR; 918 barras 5m; 02–12 enero 2024; 10.000 EUR iniciales. La fixture trending_up tiene tendencia deliberada y no estima comportamiento real.

| Estrategia / escenario | Retorno | Max drawdown | Costes estimados EUR |
|---|---:|---:|---:|
| Momentum ideal | +1.0612% | -0.0371% | 0.00 |
| Momentum realistic | -0.1012% | -0.2043% | 120.96 |
| Momentum pessimistic | -1.2500% | -1.2660% | 214.13 |
| Buy & Hold ideal | +33.6815% | -0.4431% | 0.00 |
| Buy & Hold realistic | +33.6222% | -0.4433% | 4.97 |
| Buy & Hold pessimistic | +33.5725% | -0.4435% | 9.94 |

Momentum realistic: equity final 9989.88 EUR; 44 fills de salida; expectativa -0.2300 EUR por fill de salida. Sharpe/Sortino/CAGR suprimidos por muestra corta.

Buy & Hold tiene asignación cercana al 100%; momentum máximo 10% por posición. No son exposiciones equivalentes. Buy & Hold acaba con posición abierta: incluye valoración a mercado pero no costes de una liquidación futura. El benchmark del gráfico es ideal.

Costes experimentales realistic: spread 4 bps completo (o quote previo), slippage 2 bps, impacto 2 bps × participación; comisión max(1 EUR, 1 bp notional); FX 5 bps por conversión cuando divisas difieren; participación 5% del volumen anterior; latencia 250 ms discretizada a aperturas. Pessimistic duplica costes; ideal los elimina. No son tarifas reales verificadas.

## In-sample / validation / final test / walk-forward

Dataset diario sintético 2023–2024, split por sesiones 60/20/20. Selección final: {"lookback": 12, "momentum_threshold": 0.001}.

- TRAIN: +0.0192%.
- VALIDATION: -0.0015%.
- TEST apartado hasta evaluación final: -0.0388%.
- Max drawdown TEST: -0.0764%.
- Walk-forward 12/3/3 meses: 3 folds completos; resumen geométrico OOS -0.0393%.

Los folds reinician cash y warm-up; la composición geométrica no es una curva de portfolio continuo ejecutable. Muy pocos trades; ninguna conclusión de edge. El último tramo sin ventana completa queda fuera. Ver JSON con cada fold y parámetros.

## Limitaciones y siguiente etapa

No hay datos reales descargados, feeds live/delayed, recorder remoto ni conexión de broker. No hay ranking/rebalanceo cross-sectional, factor momentum beta o atribución de trades por hora; sí CSV descriptivos de retornos por franja/gap y función de correlación. Stops observados al cierre, ejecución posterior, sin microestructura. Acciones corporativas exigen archivo raw coherente; no cash-in-lieu ni fiscalidad. Constituyentes históricos deben aportarse; no se resuelve survivorship con un catálogo actual.

Antes de considerar un broker real: verificar disponibilidad legal de broker/cliente/producto y documentos vigentes; contratar datos apropiados; calibrar spreads/costes/latencia; validación OOS independiente con históricos point-in-time; reconciliación y persistencia de órdenes, idempotencia, recuperación, límites/kill switch y revisión independiente. Esta entrega no habilita ese paso automáticamente.

Historical performance does not guarantee future results.
