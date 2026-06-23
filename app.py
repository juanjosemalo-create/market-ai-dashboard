from __future__ import annotations

import math
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from config import DEFAULT_REFRESH_MINUTES, OPTION_TICKERS
from data_sources import (
    fetch_cboe_put_call,
    fetch_options_summary,
    fetch_price_history,
    latest_market_row,
    load_snapshots,
    save_snapshot,
)
from scoring import compute_scores, tactical_probability, SCORE_RANGES, SCORE_EXPLANATIONS, INDICATOR_REFERENCE, indicator_signal

st.set_page_config(page_title="AI / Semis Market Sentiment", layout="wide")

st.title("AI / Semis Market Sentiment Dashboard")
st.caption("Datos automáticos con fuentes gratuitas/demoradas. No es tiempo real profesional ni recomendación de inversión.")

with st.sidebar:
    st.header("Configuración")
    auto_refresh = st.toggle("Auto-refrescar", value=True)
    refresh_minutes = st.slider("Refresco automático", min_value=1, max_value=30, value=DEFAULT_REFRESH_MINUTES, step=1)
    include_options = st.toggle("Incluir opciones básicas", value=True)
    save_history = st.toggle("Guardar snapshot", value=True)
    force = st.button("Actualizar ahora", use_container_width=True)

if auto_refresh:
    st_autorefresh(interval=refresh_minutes * 60 * 1000, key="market_refresh")

@st.cache_data(ttl=60 * 3, show_spinner=False)
def cached_prices():
    return fetch_price_history(period="5d", interval="5m")

@st.cache_data(ttl=60 * 30, show_spinner=False)
def cached_cboe():
    return fetch_cboe_put_call()

@st.cache_data(ttl=60 * 15, show_spinner=False)
def cached_options():
    return fetch_options_summary(OPTION_TICKERS, target_days=30)

if force:
    cached_prices.clear()
    cached_cboe.clear()
    cached_options.clear()

with st.spinner("Descargando datos..."):
    closes = cached_prices()
    row = latest_market_row(closes)
    row.update(cached_cboe())
    scores = compute_scores(row)
    row.update(scores)
    options_df = cached_options() if include_options else pd.DataFrame()

if save_history and row.get("timestamp_utc"):
    # avoid writing duplicate too often: only save when user forces or first run of script cache changes
    save_snapshot(row)

last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
st.caption(f"Última actualización local: {last_update} | Timestamp fuente app UTC: {row.get('timestamp_utc', 's/d')}")

c1, c2, c3, c4, c5 = st.columns(5)

def metric_card(col, title, value, subtitle=""):
    try:
        val = f"{float(value):.0f}/100" if value == value else "s/d"
    except Exception:
        val = "s/d"
    col.metric(title, val, subtitle)

metric_card(c1, "General Risk", row.get("general_risk_score"), f"{row.get('general_label', '')} | {row.get('general_bucket', '')}")
metric_card(c2, "AI/Semis Risk", row.get("ai_semis_stress_score"), f"{row.get('ai_semis_label', '')} | {row.get('ai_semis_bucket', '')}")
metric_card(c3, "Market Stress", row.get("market_stress_score"), f"{row.get('market_label', '')} | {row.get('market_bucket', '')}")
metric_card(c4, "Options Sentiment", row.get("options_sentiment_score"), f"{row.get('options_label', '')} | {row.get('options_bucket', '')}")
metric_card(c5, "Capitulation", row.get("capitulation_score"), f"{row.get('capitulation_label', '')} | {row.get('capitulation_bucket', '')}")

prob = tactical_probability(row.get("ai_semis_stress_score", math.nan), row.get("capitulation_score", math.nan))
st.info(f"Lectura táctica IA/Semis: {prob}")

with st.expander("Cómo leer los 5 scores principales", expanded=True):
    st.markdown("""
    Los scores van de **0 a 100**. No son una probabilidad matemática pura: son un **índice de presión/riesgo** construido con datos de volatilidad, opciones, precio relativo y macro.
    La probabilidad táctica se estima principalmente desde **AI/Semis Risk**, ajustada por **Capitulation**.
    """)
    st.dataframe(pd.DataFrame(SCORE_RANGES), use_container_width=True, hide_index=True)
    st.dataframe(pd.DataFrame(SCORE_EXPLANATIONS), use_container_width=True, hide_index=True)

st.subheader("Indicadores principales")
main_cols = [
    "VIX", "VXN", "VVIX", "SKEW", "VXN/VIX", "US10Y_TNX", "DXY",
    "QQQ_ret_1d", "SPY_ret_1d", "SMH_ret_1d", "NVDA_ret_1d",
    "QQQ_vs_SPY_1d", "SMH_vs_QQQ_1d", "NVDA_vs_SMH_1d",
    "total_put_call", "equity_put_call", "index_put_call", "etf_put_call", "spx_put_call", "vix_put_call"
]
rows = []
for k in main_cols:
    signal, interpretation = indicator_signal(k, row.get(k))
    display_name = {
        "QQQ_vs_SPY_1d": "QQQ vs SPY",
        "SMH_vs_QQQ_1d": "SMH vs QQQ",
        "NVDA_vs_SMH_1d": "NVDA vs SMH",
        "total_put_call": "Total Put/Call",
        "equity_put_call": "Equity Put/Call",
        "index_put_call": "Index Put/Call",
        "etf_put_call": "ETF Put/Call",
        "spx_put_call": "SPX Put/Call",
        "vix_put_call": "VIX Put/Call",
        "US10Y_TNX": "US10Y / TNX",
    }.get(k, k)
    rows.append({"Indicador": display_name, "Valor": row.get(k), "Señal": signal, "Interpretación": interpretation})
main_table = pd.DataFrame(rows)
st.dataframe(main_table, use_container_width=True, hide_index=True)

with st.expander("Rangos y fundamentos de cada indicador", expanded=False):
    st.markdown("Estos umbrales son **guías iniciales**, no leyes fijas. Sirven para transformar datos dispersos en una lectura homogénea de riesgo.")
    st.dataframe(pd.DataFrame(INDICATOR_REFERENCE), use_container_width=True, hide_index=True)

with st.expander("Descomposición de los scores", expanded=False):
    component_rows = [
        {"Componente": "VIX", "Score interno": row.get("score_vix"), "Entra en": "Market Stress"},
        {"Componente": "VXN", "Score interno": row.get("score_vxn"), "Entra en": "AI/Semis Risk"},
        {"Componente": "VVIX", "Score interno": row.get("score_vvix"), "Entra en": "Market Stress"},
        {"Componente": "SKEW", "Score interno": row.get("score_skew"), "Entra en": "Market Stress"},
        {"Componente": "VXN/VIX", "Score interno": row.get("score_vxn_vix"), "Entra en": "AI/Semis Risk"},
        {"Componente": "QQQ vs SPY", "Score interno": row.get("score_qqq_spy"), "Entra en": "AI/Semis Risk"},
        {"Componente": "SMH vs QQQ", "Score interno": row.get("score_smh_qqq"), "Entra en": "AI/Semis Risk"},
        {"Componente": "NVDA vs SMH", "Score interno": row.get("score_nvda_smh"), "Entra en": "AI/Semis Risk"},
        {"Componente": "Total Put/Call", "Score interno": row.get("score_total_pc"), "Entra en": "Options Sentiment"},
        {"Componente": "Equity Put/Call", "Score interno": row.get("score_equity_pc"), "Entra en": "Options Sentiment / Capitulation"},
        {"Componente": "Index Put/Call", "Score interno": row.get("score_index_pc"), "Entra en": "Options Sentiment"},
        {"Componente": "ETF Put/Call", "Score interno": row.get("score_etf_pc"), "Entra en": "Options Sentiment / Capitulation"},
        {"Componente": "SPX Put/Call", "Score interno": row.get("score_spx_pc"), "Entra en": "Options Sentiment"},
        {"Componente": "VIX Put/Call", "Score interno": row.get("score_vix_pc"), "Entra en": "Options Sentiment"},
    ]
    comp_df = pd.DataFrame(component_rows)
    st.dataframe(comp_df, use_container_width=True, hide_index=True)
    st.caption("Cada componente se normaliza de 0 a 100 con umbrales definidos en scoring.py. Luego se pondera según la fórmula de cada score.")

if include_options:
    st.subheader("Opciones básicas - vencimiento cercano a 30 días")
    if options_df.empty:
        st.warning("No se pudieron descargar opciones en esta actualización.")
    else:
        display_options = options_df.copy()
        ok_count = int((display_options.get("status") == "OK").sum()) if "status" in display_options else 0
        err_count = len(display_options) - ok_count
        st.caption(f"Opciones descargadas: {ok_count} OK / {err_count} con error. Fuente gratuita/demorada: Yahoo Finance vía yfinance.")
        for col in ["atm_iv", "put_skew_95_105"]:
            if col in display_options.columns:
                display_options[col] = display_options[col] * 100
        preferred_cols = [
            "ticker", "status", "spot", "expiration", "days_to_exp", "atm_iv",
            "expected_move_%", "put_call_volume_ratio", "put_call_oi_ratio",
            "put_skew_95_105", "error"
        ]
        display_cols = [c for c in preferred_cols if c in display_options.columns]
        st.dataframe(display_options[display_cols], use_container_width=True, hide_index=True)
        st.markdown("""
        **Cómo leer opciones básicas:**
        - **ATM IV**: volatilidad implícita aproximada de la opción más cercana al precio actual. Más alta = mercado espera más movimiento.
        - **Expected move %**: movimiento esperado aproximado hasta el vencimiento elegido. No indica dirección.
        - **Put/Call Volume Ratio**: volumen de puts dividido calls. Alto = más demanda de protección bajista en el día.
        - **Put/Call OI Ratio**: open interest de puts dividido calls. Alto = más posicionamiento bajista/protectivo acumulado.
        - **Put Skew 95/105**: IV de puts cerca de 95% del spot contra calls cerca de 105%. Positivo = protección bajista más cara que calls alcistas.
        """)
        if ok_count == 0:
            st.warning("Yahoo/yfinance no está devolviendo cadenas de opciones desde esta ejecución. Revisá la columna 'error'. Puede ser bloqueo temporal, ticker sin datos o limitación de Streamlit Cloud.")

st.subheader("Gráficos intradiarios")
if closes.empty:
    st.warning("No se descargaron precios. Revisar conexión o tickers.")
else:
    chart_df = closes.copy().ffill()
    tabs = st.tabs(["Volatilidad", "Precio relativo", "Semis / IA"])
    with tabs[0]:
        vols = [c for c in ["^VIX", "^VXN", "^VVIX", "^SKEW"] if c in chart_df.columns]
        if vols:
            fig = px.line(chart_df[vols].reset_index(), x=chart_df.index.name or "Datetime", y=vols, title="VIX / VXN / VVIX / SKEW")
            st.plotly_chart(fig, use_container_width=True)
    with tabs[1]:
        rel = pd.DataFrame(index=chart_df.index)
        if "QQQ" in chart_df and "SPY" in chart_df:
            rel["QQQ/SPY"] = chart_df["QQQ"] / chart_df["SPY"]
        if "SMH" in chart_df and "QQQ" in chart_df:
            rel["SMH/QQQ"] = chart_df["SMH"] / chart_df["QQQ"]
        if "NVDA" in chart_df and "SMH" in chart_df:
            rel["NVDA/SMH"] = chart_df["NVDA"] / chart_df["SMH"]
        if not rel.empty:
            rel = rel / rel.iloc[0] * 100
            fig = px.line(rel.reset_index(), x=rel.index.name or "Datetime", y=rel.columns, title="Relativos normalizados = 100")
            st.plotly_chart(fig, use_container_width=True)
    with tabs[2]:
        names = [c for c in ["QQQ", "SMH", "SOXX", "NVDA", "AMD", "AVGO", "MU", "MRVL"] if c in chart_df.columns]
        norm = chart_df[names].dropna(how="all").ffill()
        if not norm.empty:
            norm = norm / norm.iloc[0] * 100
            fig = px.line(norm.reset_index(), x=norm.index.name or "Datetime", y=names, title="IA/Semis normalizado = 100")
            st.plotly_chart(fig, use_container_width=True)

st.subheader("Histórico de snapshots")
hist = load_snapshots()
if hist.empty:
    st.caption("Todavía no hay histórico guardado.")
else:
    last_hist = hist.tail(300).copy()
    cols = [c for c in ["timestamp_utc", "general_risk_score", "ai_semis_stress_score", "market_stress_score", "options_sentiment_score", "capitulation_score"] if c in last_hist.columns]
    st.dataframe(last_hist[cols].tail(20), use_container_width=True, hide_index=True)
    if "timestamp_utc" in last_hist and "ai_semis_stress_score" in last_hist:
        plot_hist = last_hist[cols].copy()
        plot_hist["timestamp_utc"] = pd.to_datetime(plot_hist["timestamp_utc"], errors="coerce")
        ycols = [c for c in cols if c != "timestamp_utc"]
        fig = px.line(plot_hist, x="timestamp_utc", y=ycols, title="Scores guardados")
        st.plotly_chart(fig, use_container_width=True)

st.caption("Advertencia: yfinance/Yahoo y scraping web pueden tener datos demorados, incompletos o cambiar estructura. Validar antes de operar.")
