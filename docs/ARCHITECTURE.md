# Arquitectura

Python 3.12+, Pydantic, pandas/NumPy, PyArrow, SQLite, Typer/Rich, matplotlib.
Se evita DuckDB adicional porque Parquet + SQLite cubren el MVP. No hay framework
externo de backtesting ni dependencia del broker.

```
FileProvider → validación/calendario → Parquet + metadata SQLite
                 ↓
features causales → Strategy → Signal → RiskManager → OrderIntent
                                                       ↓
                                                   PaperBroker
                                                       ↓
                                                    Portfolio
                                                       ↓
                           métricas / costes / benchmark / HTML+JSON+CSV
```

Backtester ordena eventos globalmente: cierre completado, acciones corporativas, apertura siguiente
cuando coinciden timestamps. Cada decisión recibe únicamente la fila completada, sin
referencia al dataset. HistoryView ofrece copias limitadas a as-of para extensiones.
Features vectorizadas causales pasan pruebas de invariancia al modificar el futuro.
Paper replay usa la misma clase Backtester y por tanto exactamente las mismas reglas.

ExecutionBroker es un protocolo desacoplado. No existe LiveBroker; el comando oculto
live rechaza siempre. Configuraciones no aceptan campos desconocidos, apalancamiento,
short ni cobertura ficticia. Las posiciones se compran con efectivo base convertido
en cada transacción, sin préstamo ni subcuenta persistente en divisa.

El motor acepta múltiples instrumentos con reloj común y límites conjuntos. El baseline
de CLI asigna fracciones iguales del capital inicial por listing con redondeo entero.
Ranking/rebalanceo cross-sectional queda para etapa 2, separado del MVP validado.

Extensión externa futura: añadir adapter MarketDataProvider y adaptador de ejecución
sin modificar Strategy/Portfolio/RiskManager/Analytics. Antes de cualquier operación real
harían falta autorización expresa, evaluación normativa del broker/cliente/producto,
contratos de datos, feed de quotes, reconciliación de órdenes y fills, idempotencia,
persistencia/recuperación, kill switch y validación independiente. Este proyecto no los
implementa ni está preparado para recibir credenciales bancarias.
