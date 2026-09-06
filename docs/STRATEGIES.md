# Hipótesis, estrategias y ablaciones

Momentum: retorno N, precio sobre VWAP opcional, volumen relativo y volatilidad admisible.
Breakout: cierre supera máximo **previo**, buffer bps y confirmación volumen/volatilidad.
Mean reversion: z-score negativo, RSI bajo, debajo VWAP y fuera de régimen TRENDING.
Buy & Hold: primera entrada válida, mantener. No tiene stops de estrategia, pero entradas
siguen cash/liquidez/riesgo. Las estrategias son long/cash; no presuponen rentabilidad.

Las features se calculan juntas y se separan de reglas: simple/log return, momentum,
SMA, EMA, VWAP de sesión, ATR de media simple de true ranges, desviación, volatilidad,
volumen relativo contra media anterior, extremos anteriores, distancia VWAP, RSI,
gap de apertura contra cierre anterior e intraday return. ATR incluye gaps.
Relative strength queda NaN hasta disponer de benchmark alineado: no se sustituye
silenciosamente por el retorno del propio activo.

Regímenes LOW/NORMAL/HIGH_VOL por umbrales configurables y TRENDING/RANGING por momentum
versus volatilidad. No hay clasificador RISK_ON/OFF ni factores externos implícitos.

H1: comparar momentum con benchmark. H2: volume_ratio_min=0 frente al valor base.
H3: require_above_vwap=false. H4: variar ventanas de minutos de sesión.
H5: tres escenarios de costes. H6: allowed_regimes y umbrales de volatilidad.
H7: repetir sobre identidades distintas. H8: listings UCITS comparables, sin afirmar
equivalencia, registrando horarios, FX y costes por separado.

Ablaciones reproducibles mediante archivos YAML: sin volumen (0), sin VWAP (false),
sin filtro volatilidad (min=0,max muy alto), sin stop (stop_atr_multiple=0, sizing fixed
o percentage para no depender de stop_distance). No cambiar varias cosas sin registrarlo.
No existe aún un comando automático de ablation. Los reportes exportan CSV descriptivos
por franjas horarias y gap/overnight/intradía de sesión; no confundir esas estadísticas
de barras con P&L de trades segmentado por hora de entrada. Cross-sectional es etapa 2.
