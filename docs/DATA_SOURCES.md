# Fuentes y contratos de datos

Investigación consultada: 2026-09-06. No se incluye ningún adaptador remoto ni API key.

| Fuente oficial | Capacidades consideradas | Límites y decisión |
|---|---|---|
| [Alpha Vantage documentación](https://www.alphavantage.co/documentation/) | EOD, intradía, series ajustadas, eventos | Diferenciar OHLC raw, adjusted close y eventos; intradía/tiempo real pueden requerir premium. Cobertura por listing UE debe verificarse. |
| [Alpha Vantage planes](https://www.alphavantage.co/premium/) | Desarrollo con endpoints gratuitos | Límite estándar publicado: 25 peticiones/día; funciones premium aparte. No seleccionado. |
| [Databento documentación](https://databento.com/docs) y [licencias/precios](https://databento.com/pricing/) | Histórico, live, referencia y acciones corporativas según dataset | Derechos de uso y redistribución específicos de mercado/dataset; verificar cobertura UE y entitlement. No se presume un feed global gratuito. |
| [BCE tipos de cambio](https://data.ecb.europa.eu/key-figures/ecb-interest-rates-and-exchange-rates/exchange-rates) | Referencias FX diarias | Publicación aproximadamente 16:00 CET en días hábiles; para información, no precios ejecutables. As-of debe ser publicación, no medianoche de la fecha. |
| [iShares](https://www.ishares.com/uk/individual/en/products/253743/ishares-sp-500-b-ucits-etf-acc-fund) | Identidad, clase y listings | Ficha actual, no security master histórico ni evidencia de disponibilidad del broker. |
| [exchange_calendars](https://github.com/gerrymanoim/exchange_calendars) | Calendarios, festivos y sesiones cortas | Librería de código abierto mantenida por comunidad; versión fijada en uv.lock. No sustituye anuncios de bolsa, suspensiones ni subastas. |

CSV y Parquet son la fuente elegida para el MVP: funcionan sin claves y conservan
procedencia aportada por el usuario. No se garantiza precisión de un CSV ni se asigna
un retraso artificial. Las fixtures propias son sintéticas y reproducibles.
No hay rate limit de red ni licencia externa para ellas. Para datos importados, conservar
contrato/licencia del proveedor y permisos de uso; el programa no concede redistribución.
Los planes externos pueden cambiar: comprobar documentación antes de conectar un adaptador.

## Esquema

Obligatorio: `timestamp, open, high, low, close, volume, instrument_id`.
Alternativa a instrument_id: `symbol` con `mic,currency` cuando haga falta desambiguar.
Opcionales: `bid,ask` juntos, observados al cierre. Timestamp **al cierre** con offset UTC
explícito; intervalos desde apertura de sesión, última vela corta si es necesario.
OHLC sin ajustar y volumen en participaciones, no notional. No se adivina timezone,
ajuste o convención de timestamp. `--mapping` recibe JSON source-column → canonical-column.

El validador rechaza duplicados, orden incorrecto por instrumento, precios no positivos,
no finitos, OHLC imposible, cotizaciones cruzadas, barras fuera de calendario, identidad
desconocida y datos anteriores a known_from/listing/inception o posteriores a delisting.
Huecos generan WARN y **no se rellenan**. Cobertura se calcula para sesiones completas
entre primera y última fecha local: fragmentos de sesión se señalan como incompletos.
Outliers >20% por barra son avisos; revisar eventos, no borrarlos automáticamente.

Cache de importación: hash de bytes fuente, mapping, timeframe, ajuste y registro.
Parquet inmutable por clave, sidecar JSON y metadata SQLite. La reimportación no añade
duplicados. `MarketDataProvider` abstrae lectura; `FileProvider` implementa CSV/Parquet.
`download` y `record` explican ausencia del proveedor y salen con código 2.
No se presentan como descargas o grabación live implementadas.

FX CSV: `timestamp,currency,base,rate`, tasa unidades base por una unidad local.
Timestamp es disponibilidad. Se rechaza ausencia/futuro o antigüedad >96h por defecto.
No se rellena con datos futuros. EUR/EUR=1. Los tipos BCE tendrían que convertirse
a esta convención y respetar la publicación. FX intradía debe provenir de fuente adecuada.
