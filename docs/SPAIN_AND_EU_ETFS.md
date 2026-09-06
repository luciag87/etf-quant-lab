# ETFs desde España y la UE

Fuentes consultadas el 6 de septiembre de 2026. Este catálogo sirve para investigación;
no determina elegibilidad de compra ni sustituye la verificación del intermediario.

El Reglamento PRIIPs 1286/2014 exige al fabricante elaborar el KID antes de poner
el producto a disposición de minoristas y al vendedor/asesor entregarlo con antelación
suficiente (artículos 5 y 13). Véase el [texto oficial EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/ALL/?uri=celex%3A32014R1286).
El nombre del ETF o disponer de una cotización no acreditan cumplimiento documental.
No se establece aquí una prohibición universal de todos los ETFs estadounidenses:
la documentación, el cliente, la distribución y el broker importan.

UCITS es un marco europeo de organismos de inversión colectiva, regulado por la
[Directiva 2009/65/CE](https://eur-lex.europa.eu/eli/dir/2009/65/oj/eng), con requisitos
de organización y protección del inversor. No significa ausencia de riesgo ni habilita
por sí solo una compra concreta. ETF describe la negociación en bolsa; UCITS describe
un marco regulatorio. Un ETP de cripto u oro no debe clasificarse automáticamente UCITS.

Desde enero de 2023 el KID PRIIPs reemplaza el KIID UCITS para el contexto minorista
UE aplicable. La [pregunta consolidada de ESMA sobre fondos](https://www.esma.europa.eu/sites/default/files/2023-05/JC_2023_22_-_Consolidated_JC_PRIIPs_Q_As.pdf)
distingue situaciones en que el fondo no se pone a disposición de minoristas UE y
puede seguir siendo pertinente el KIID. Las [FAQ PRIIPs de CNMV](https://www.cnmv.es/docportal/Legislacion/FAQ/FAQ_PRIIPS.pdf)
explican la transición. Guías antiguas sobre DFI de dos páginas no deben confundirse
con el régimen PRIIPs posterior. Verificar siempre el documento vigente del producto.

## Representación en software

`researchable` controla inclusión en investigación. `potentially_tradeable` comienza
en `unknown`, incluso para UCITS. Sólo permite `externally_verified` con evidencia
aportada expresamente; el motor nunca la deduce de ISIN, país, UCITS o ticker.
La evidencia debería incluir broker, fecha, clasificación del cliente y documentación.
Ningún estado permite enviar órdenes reales en esta versión.

`ISIN:MIC:currency` identifica una línea de negociación; ISIN identifica la clase de
participaciones y MIC/divisa distinguen líneas. El ticker es un alias resoluble sólo
si no hay ambigüedad. Algunas bolsas negocian la misma clase en varias monedas.
Una cotización en EUR no elimina la exposición económica a USD de los activos subyacentes.
La divisa del fondo, de cotización y del inversor son conceptos diferentes.
Los ficheros deben normalizar GBX a GBP antes de importarse; GBX no se interpreta como GBP.

El catálogo incluye CSPX, ISIN IE00B5BMR087, listado USD en LSE según el
[emisor iShares](https://www.ishares.com/uk/individual/en/products/253743/ishares-sp-500-b-ucits-etf-acc-fund).
También se registra SXR8 EUR en Xetra (listing 26/05/2010), de la misma clase ISIN.
Es un UCITS acumulativo irlandés que sigue S&P 500. No se afirma identidad de rendimiento
con SPY/VOO: costes, réplica, horarios, dividendos y mercado difieren. La ficha actual no
prueba membresía histórica: `known_from` es la fecha de consulta, separada de nacimiento
y fecha de listing. El usuario necesita fuentes point-in-time para retroceder ese campo.

SPY/QQQ/VOO/IWM pueden importarse tras registrar identidad y procedencia fiables.
No se incluyen equivalencias automáticas ni se asume acceso minorista español.
El instrumento DEMO y su ISIN ZZ son sintéticos, no títulos adquiribles.
