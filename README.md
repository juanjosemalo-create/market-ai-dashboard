# Market AI / Semis Dashboard v5 + VIX/VIX3M

Aplicación Streamlit de sentimiento y riesgo de mercado con foco en IA, Nasdaq y semiconductores. Esta versión conserva íntegramente el dashboard v5 y agrega una segunda página estadística para VIX/VIX3M y SPX.

## Estructura

### Página principal — `app.py`

- General Risk, AI/Semis Risk, Market Stress, Options Sentiment y Capitulation.
- Semáforo único de entrada.
- Scoring por percentiles de aproximadamente dos años.
- Term structure VIX9D / VIX / VIX3M / VIX6M.
- Crédito, breadth, momentum, drawdown, relativos y opciones.
- Manual integrado.

### Página VIX/VIX3M — `pages/2_VIX_VIX3M_Probabilidades.py`

- Descarga histórica automática de VIX, VIX3M y SPX.
- Ocho regímenes: normal, transición, prealerta, continuación, inversión, pánico, rebote y recuperación.
- Probabilidad de nuevo mínimo y caídas adicionales en varios horizontes.
- Probabilidad de cierre positivo o negativo.
- Retorno y excursión adversa medianos.
- Probabilidad base, probabilidad condicionada y lift.
- Intervalo de confianza del 95% y límite conservador.
- Regla exacta y casos históricos análogos.
- Biblioteca comparativa y descarga CSV.

## Archivos principales

- `app.py` — dashboard principal.
- `data_sources.py` — datos y métricas del dashboard principal.
- `scoring.py` — composites y semáforos.
- `manual.py` — manual dentro de la aplicación.
- `vix_probability_engine.py` — descarga, escenarios y estadísticas históricas.
- `pages/2_VIX_VIX3M_Probabilidades.py` — interfaz del motor probabilístico.
- `config.py` — parámetros y tickers.
- `requirements.txt` — dependencias.

## Publicación en Streamlit Cloud

Subir todos los archivos y la carpeta `pages` al mismo repositorio. Mantener:

- **Main file path:** `app.py`

Streamlit detecta automáticamente la segunda página.

## Actualización desde una versión anterior

Reemplazar los archivos existentes por los de esta carpeta y agregar:

- `vix_probability_engine.py`
- la carpeta `pages`

No es necesario crear otra aplicación en Streamlit Cloud.

## Advertencia

Datos gratuitos y potencialmente demorados de Yahoo, Cboe y FRED. Las frecuencias históricas no garantizan resultados futuros y no constituyen recomendación de inversión.
