# Metodología y límites

## Reloj y fills

Señal en cierre T; primer fill posible en una apertura >= T+latencia.
IDEAL usa latencia cero, pudiendo usar el open de la vela siguiente en el mismo instante
de frontera; nunca el close de la vela que genera señal. REALISTIC/PESSIMISTIC con
250 ms pierden esa frontera y esperan otra apertura. Es una discretización conservadora,
no una simulación de 250 ms dentro de la vela. No se interpolan precios futuros.

Bid/ask de cierre anterior estiman spread de la próxima apertura. Si faltan, se usa
spread configurado. Volumen anterior limita participación; no se utiliza volumen total
de una vela aún desconocida. Esto es una hipótesis de liquidez, no un límite de volumen
real ejecutado. No modela cola, profundidad, halts, NBBO ni auction fills.

| Supuesto experimental | REALISTIC | PESSIMISTIC | IDEAL |
|---|---:|---:|---:|
| Spread completo fallback | 4 bps | 8 bps | 0 |
| Slippage | 2 bps | 4 bps | 0 |
| Impacto | 2 bps × participación | doble | 0 |
| Comisión | max(1 base, 1 bp × notional base) | doble | 0 |
| FX en compra/venta entre divisas | 5 bps | 10 bps | 0 |
| Participación del volumen anterior | 5% | 5% | 5% |

No son tarifas observadas ni parámetros óptimos. Spread se carga medio por lado;
slippage/spread están incorporados al fill y sólo se desglosan para atribución, sin
restarlos dos veces. Comisión/FX se restan del cash. TER ya incorporado a precios del
fondo no se vuelve a deducir. Órdenes con fill parcial cancelan resto (IOC); si no hay
capacidad permanecen pendientes hasta siguiente apertura. Las salidas pueden repetirse
si hay remanente. No hay capital infinito. Se revalida riesgo al abrir después de gaps.

Stops, take profit y trailing se observan al cierre y generan salida posterior; no son
órdenes stop nativas ni se garantiza limitar la pérdida al umbral. Fin de día solicita
salida dos velas antes del cierre; baja liquidez o huecos pueden dejar overnight.
Posiciones finales se valoran, no se liquidan a un precio ficticio. Sus costes de futura
salida no están incluidos. Revisar open_positions y fills antes de interpretar métricas.

## Precio, dividendos, splits y FX

Sólo raw OHLC en motor. Rechaza `adjustment != raw` al importar.
Acciones JSON: instrument_id, kind (split/distribution), value, effective_at, known_at.
Un split divide coste unitario/stops/marca y multiplica participaciones; reinicia warm-up
de indicadores. Acciones conocidas después de effective_at se rechazan. Distribuciones
se reconocen como efectivo al ex-date, sin retención ni lag de pago. Ese modelo permite
retorno económico con distribuciones registradas; sin eventos el resultado es price
return. No se reinvierten automáticamente. Reverse splits que originan fracciones
requieren cash-in-lieu externo: no investigarlos con este MVP sin normalización.

EUR es base por defecto. FX disponible <= evento, stale guard 96h. Cada transacción
convierte base/local; cash permanece base. P&L de una salida se descompone en movimiento
local al FX de entrada más movimiento FX aplicado al valor local de salida, menos fees.
La interacción queda en el componente FX. `return_attribution` muestra también interacción
separada: (1+asset_return)(1+FX_return)-1. +5% local y −3% FX = +1.85% base.

## Validación y métricas

Split por sesiones 60/20/20, sin shuffle. Optimización usa TRAIN/VALIDATION;
TEST se consulta sólo con --evaluate-test. Repetir esa opción convierte el test en
parte del proceso de investigación; no hay bloqueo físico contra el investigador.
Máximo 100 combinaciones. Score transparente combina retorno validation, drawdown,
divergencia train/validation y escasez de trades; no estima significancia estadística.

Walk-forward 12/3/3 meses, selección interna en cada train y evaluación en outer test.
Ventanas OOS no se solapan. Cada fold empieza con cash y warm-up propio; no se arrastran
posiciones. La composición geométrica es un resumen de folds, no curva ejecutable.

Sharpe/Sortino con retornos diarios, 252 observaciones por año, rf=0; no anualizar
velas de 5m como observaciones independientes. Se suprimen con <30 retornos diarios.
CAGR sólo con >=1 año. Datos de distintos mercados se agrupan por día UTC: un portfolio
global complejo requerirá otra convención de valoración. Volatilidad no descuenta festivos
globales ni días sin observación. Alpha/beta aproximadas OLS sin factores adicionales.

Trades cuenta fills de salida, no ciclos agregados. Cash usage/exposure son medias
por evento de cierre (no ponderadas por tiempo de reloj). Bootstrap circular de bloques
diarios requiere >=30 observaciones; no corrige múltiples comparaciones. No hay prueba
concluyente de edge. Benchmark ideal sirve como hurdle exigente; la CLI también permite
Buy & Hold con tres escenarios de costes, para comparación homogénea.

## Sesgos

Survivorship: catálogo actual no reconstruye ETFs cerrados; known_from/listing/inception
impiden retroceder existencia automáticamente. Look-ahead: datos, volumen, FX y acciones
deben estar disponibles antes de decisiones. Overfitting: seleccionar reglas que explican
ruido histórico. Data snooping: muchas variantes elevan falsos descubrimientos incluso
con OOS reutilizado. Registrar todos los intentos y reservar un test final nuevo.
