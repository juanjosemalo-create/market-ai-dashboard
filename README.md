# Market AI Dashboard v3

Dashboard Streamlit para medir sentimiento/riesgo de mercado con foco en IA, Nasdaq y semiconductores.

## Novedades v3

- Rangos explicativos para los 5 scores principales.
- Tabla didáctica: qué mide cada score, fórmula y uso.
- Indicadores principales con señal automática: bajo/normal, tensión, riesgo alto o extremo.
- Tabla de rangos y fundamentos de cada indicador.
- Descomposición de componentes internos de los scores.
- Explicación para métricas de opciones: ATM IV, expected move, put/call volume, open interest y skew.

## Deploy en Streamlit Cloud

Subir estos archivos a la raíz del repositorio GitHub:

- app.py
- data_sources.py
- scoring.py
- config.py
- requirements.txt
- README.md

En Streamlit Cloud elegir:

- Repository: tu_usuario/market-ai-dashboard
- Branch: main
- Main file path: app.py

## Nota

Los datos son gratuitos/demorados. El dashboard no reemplaza una plataforma profesional ni constituye recomendación de inversión.
