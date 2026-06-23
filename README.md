# Market AI Dashboard v4

Dashboard Streamlit de sentimiento/riesgo de mercado con foco en IA, Nasdaq y semiconductores.

## Qué cambió vs v3 (lo importante)

El salto de v4 es **metodológico**, no cosmético:

1. **Scoring por percentil, no por umbral fijo.** Cada indicador se mide contra su
   propio régimen de ~2 años (`PCT_LOOKBACK = 504` ruedas). Un VIX de 20 ya no vale
   lo mismo siempre: vale según dónde esté respecto de su propia historia. Esto se
   alimenta de la historia diaria de Yahoo, así que funciona desde el primer arranque
   (no depende de acumular snapshots).

2. **Term structure de volatilidad (nuevo).** Se agregan `^VIX9D`, `^VIX3M`, `^VIX6M`.
   El ratio **VIX/VIX3M** es el núcleo del estrés sistémico: >1 (backwardation) =
   estrés agudo de corto plazo. Señal más limpia que SKEW/VVIX.

3. **Cambios (deltas), no solo niveles.** Salto de VXN 1d y cambio del 10Y entran por
   percentil del *cambio*. El sentimiento táctico vive en la velocidad del movimiento.

4. **Relativos multi-ventana.** SMH-QQQ, QQQ-SPY, NVDA-SMH a 5 y 20 días (no 1 día).
   Mide momentum relativo, no una sola rueda ruidosa.

5. **Breadth (amplitud).** % de nombres del universo por encima de su MA50, total y
   sectorial (semis). Capta el deterioro interno que los índices concentrados esconden.

6. **Momentum / sobreventa.** RSI(14) de SMH/QQQ y drawdown vs máximo de 52 semanas,
   alimentando el score de Capitulation.

7. **Crédito mejor aislado.** HYG vs IEF (high yield vs Treasuries) en vez de HYG vs LQD,
   que mezclaba duración.

8. **Lectura táctica honesta.** Se eliminaron los porcentajes inventados
   (tipo "60-70%"). Hasta tener un backtest real, es una lectura cualitativa de postura,
   no una probabilidad calibrada.

9. **Avisos de cobertura.** Si el put/call de CBOE (scraping frágil) no llega, el tablero
   avisa que Options/Capitulation están parciales en vez de mostrar números a medias.

## Archivos

- `app.py` — UI
- `data_sources.py` — descarga + cálculo de métricas y scores por percentil
- `scoring.py` — agregación en 5 composites + lectura táctica + tablas de referencia
- `config.py` — tickers y parámetros
- `requirements.txt`

## Deploy en Streamlit Cloud

Subir todos los archivos a la raíz del repo. En Streamlit Cloud:
- Main file path: `app.py`

Sin dependencias ni API keys nuevas respecto de v3.

## Pendiente (no incluido a propósito)

- **FRED (HY OAS)**: mejor que HYG/IEF pero requiere API key + secrets → fricción de deploy.
- **Backtest de calibración**: validar pesos y umbrales contra retornos forward del SMH.
  Meter números "calibrados" sin esto sería sobreajuste. Es el siguiente paso natural.

## Nota

Datos gratuitos/demorados (Yahoo + CBOE). No reemplaza una plataforma profesional ni
constituye recomendación de inversión.
