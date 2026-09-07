# FASE 1 — Correcciones del motor existente

Base auditada: `3fc921e09433e69bf2c5f34d80ab79cae7d63c9f`.
Alcance: correcciones de FASE 1 tras revisión de FASE 0; no empieza FASE 2.

## Diagnóstico y cambios

| Problema reproducido | Corrección | Regresión |
|---|---|---|
| Fills inválidos modificaban cash/cantidad | Modelo inmutable y validación antes de aplicar; rechaza ventas imposibles y overflow | `test_invalid_fill_rejected_without_mutation`, `test_overflowing_fill_and_unfunded_fees_are_atomic` |
| Cooldown global con contador local | Diccionario por instrumento y `record_loss`; frontera exacta y cero barras | `test_cooldown_scoped_and_boundary` |
| Primer valor del día ocultaba pérdidas/gaps | Zona configurable, referencia anterior y bloqueo diario enclavado | `test_daily_boundary_counts_gap_and_latches`, `test_first_loss_and_timezone_validation` |
| Marcas parciales causaban drawdown falso | Actualización conjunta por timestamp/etapa antes de riesgo | `test_simultaneous_marks_do_not_latch_false_drawdown` |
| Orden sin fill sobrevivía indefinidamente; señal caducada podía entrar | IOC en primer intento elegible; cancelación por reversión; latencia separada | `test_pending_ioc_expiry_and_latency`, `test_reversed_signal_cancels_delayed_entry` |
| Una salida parcial podía olvidar inventario | Conserva intención y emite otra orden; ninguna ejecución inventada | `test_partial_exit_keeps_intention_and_fills_use_next_open` |
| Distribución terminal no aparecía en curva; fracciones atrapadas | Snapshot terminal conciliado, ingreso separado y rechazo explícito de fracciones | `test_terminal_distribution_reconciles`, `test_fractional_reverse_split_rejected` |
| Acción dentro de una barra mezclaba unidades | Rechazo explícito hasta aportar datos de mayor resolución | `test_split_inside_bar_rejected` |
| P&L abierto omitía comisiones pendientes | Unrealized neto; retorno realizado, marcado, inventario y coste estimado separados | `test_open_fees_and_partial_cycle_reconcile`, `test_metrics_open_positions_and_first_intraday_day` |
| Primer retorno intradía ausente | Agregación UTC incluye tramo inicial; conserva convención diaria existente | `test_first_intraday_return_is_included` |
| Benchmark usaba composición futura; CLI sobrescribía riesgo BH | Universo inicial congelado, política en metadata y respeto a configuración del usuario | `test_benchmark_future_listing_does_not_change_prefix`, `test_cli_preserves_risk_and_rejects_adjusted` |
| Backtest/paper diferían en eventos corporativos | Ambos reciben actions-file; investigación rechaza esta opción explícitamente | `test_full_report_and_paper_actions_parity` |

Se conservan módulos, comandos, dependencias y aliases de métricas existentes. Reportes
añaden CSV de ciclos/eventos y JSON de pendientes. Los resultados históricos de ejemplo
no se regeneran ni se presentan como resultados de esta versión.

## Verificación

Se crearon y ejecutaron reproductores antes de sus correcciones: hubo fallos de assertions
por validación, cooldown, daily boundary, valoración simultánea, eventos terminales,
fracciones, pendientes, contabilidad abierta y configuración. Después se ejecutaron
los grupos corregidos y la suite completa en los puntos de integración.

Resultado final local: **84 tests aprobados**, incluidos los 54 casos originales.
Formato Ruff y lint aprobados; mypy aprobado sobre 36 archivos fuente.
La integración genera HTML/JSON/CSV en temporal y compara backtest realista con paper
para idénticos datos, configuración y distribución terminal.

Comandos de CI/aceptación:

```sh
uv run ruff format --check
uv run ruff check
uv run mypy src
uv run pytest
```

En esta sesión Windows se ejecutaron los equivalentes directamente desde `.venv/Scripts`
(`ruff`, `mypy`, `python -m pytest`): uv no está disponible como comando ejecutable.
No se afirma haber ejecutado el prefijo `uv run`. Cachés y temporales se dirigieron a
`work` por permisos del entorno; pytest usó `-p no:cacheprovider`. Ningún test se eliminó
ni se marcó xfail. No se midió un porcentaje de cobertura.

## Cambios de resultados esperados

El bloqueo diario ya incluye gaps; entradas demoradas con señal inválida se cancelan.
Esto puede modificar fills y retorno histórico. La valoración simultánea evita falsos
halts. Las comisiones de entrada reducen unrealized; distribuciones terminales aumentan
equity y realized income. El primer intervalo diario influye en volatilidad y ratios.
Un nuevo ETF tardío ya no reduce la asignación inicial del benchmark. Estas diferencias
son correcciones de contrato, no mejoras de rentabilidad garantizadas.

## Riesgos pendientes

- No idempotencia de fills externos, persistencia operativa ni recuperación tras reinicio:
  quedan para FASE 3–4. El mismo Fill válido aplicado dos veces sigue siendo dos aplicaciones.
- No broker conectado, reconciliación, scheduler ni safety controller. Live sigue rechazado.
- Stops al cierre; liquidez simulada desde volumen previo. Estimación de liquidación no
  garantiza capacidad futura y devuelve null si el snapshot no permite estimar todo.
- Buy & Hold conserva su contrato de mantenimiento: no convierte stops de estrategia en
  salidas automáticas. Los límites de riesgo bloquean entradas; no es un kill switch de broker.
- Benchmark inicial puede excluir mercados cuya primera apertura es posterior; no pretende
  representar un índice oficial ni eliminar survivorship bias. Warm-up y redondeo persisten.
- Optimización/walk-forward no aplican corporate actions por fold; rechazan actions-file.
- Curva intermedia valorada en cierres; terminal incluye acciones. No hay ledger intrabar
  de cada cambio de equity. Agregación estadística UTC independiente de risk_timezone.
- Caché mutable del calendario, integridad/provenance más amplia, TEST sellado y sesgos
  estadísticos siguen pendientes de las fases correspondientes. No hay evidencia nueva de edge.

FASE 1 entregada como unidad de corrección verificable. FASE 2 no iniciada.
