from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from config import DEFAULT_REFRESH_MINUTES, OPTION_TICKERS, PCT_LOOKBACK
from data_sources import (
    fetch_daily_history, fetch_intraday, fetch_cboe_put_call,
    fetch_options_summary, build_metrics, save_snapshot, load_snapshots,
)
from scoring import (
    compute_composites, tactical_reading,
    SCORE_RANGES, SCORE_EXPLANATIONS, INDICATOR_REFERENCE,
)

st.set_page_config(page_title="AI / Semis Market Sentiment v4", layout="wide")
st.title("AI / Semis Market Sentiment Dashboard · v4")
st.caption("Scoring por percentil sobre ~2 años de historia (no umbrales fijos). "
           "Datos gratuitos/demorados (Yahoo + CBOE). No es tiempo real profesional ni recomendación de inversión.")

with st.sidebar:
    st.header("Configuración")
    auto_refresh = st.toggle("Auto-refrescar", value=True)
    refresh_minutes = st.slider("Refresco automático (min)", 1, 30, DEFAULT_REFRESH_MINUTES, 1)
    include_options = st.toggle("Incluir opciones (Yahoo)", value=True)
    include_cboe = st.toggle("Incluir put/call CBOE (frágil)", value=True)
    save_history = st.toggle("Guardar snapshot", value=True)
    force = st.button("Actualizar ahora", use_container_width=True)
    st.caption(f"Ventana de percentil: {PCT_LOOKBACK} ruedas (~2 años).")

if auto_refresh:
    st_autorefresh(interval=refresh_minutes * 60 * 1000, key="market_refresh")


@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)
def cached_daily():
    return fetch_daily_history(period="2y", interval="1d")


@st.cache_data(ttl=60 * 3, show_spinner=False)
def cached_intraday():
    return fetch_intraday(period="5d", interval="5m")


@st.cache_data(ttl=60 * 30, show_spinner=False)
def cached_cboe():
    return fetch_cboe_put_call()


@st.cache_data(ttl=60 * 15, show_spinner=False)
def cached_options():
    return fetch_options_summary(OPTION_TICKERS, target_days=30)


if force:
    cached_daily.clear(); cached_intraday.clear()
    cached_cboe.clear(); cached_options.clear()

with st.spinner("Descargando datos..."):
    daily = cached_daily()
    intraday = cached_intraday()
    cboe = cached_cboe() if include_cboe else {}
    metrics = build_metrics(daily, intraday, cboe)
    metrics.update(compute_composites(metrics))
    options_df = cached_options() if include_options else pd.DataFrame()

if save_history and metrics.get("timestamp_utc"):
    save_snapshot(metrics)

st.caption(f"Última actualización local: {datetime.now():%Y-%m-%d %H:%M:%S} | "
           f"Timestamp fuente UTC: {metrics.get('timestamp_utc', 's/d')}")

# ---------------------------------------------------------------------
# 5 scores principales
# ---------------------------------------------------------------------
c1, c2, c3, c4, c5 = st.columns(5)


def metric_card(col, title, value, subtitle=""):
    try:
        val = f"{float(value):.0f}/100" if value == value else "s/d"
    except Exception:
        val = "s/d"
    col.metric(title, val, subtitle)


metric_card(c1, "General Risk", metrics.get("general_risk_score"),
            f"{metrics.get('general_label','')} | {metrics.get('general_bucket','')}")
metric_card(c2, "AI/Semis Risk", metrics.get("ai_semis_stress_score"),
            f"{metrics.get('ai_semis_label','')} | {metrics.get('ai_semis_bucket','')}")
metric_card(c3, "Market Stress", metrics.get("market_stress_score"),
            f"{metrics.get('market_label','')} | {metrics.get('market_bucket','')}")
metric_card(c4, "Options Sentiment", metrics.get("options_sentiment_score"),
            f"{metrics.get('options_label','')} | {metrics.get('options_bucket','')}")
metric_card(c5, "Capitulation", metrics.get("capitulation_score"),
            f"{metrics.get('capitulation_label','')} | {metrics.get('capitulation_bucket','')}")

# Avisos de cobertura parcial
warns = []
if metrics.get("cov_options", 1) < 0.5:
    warns.append("Options Sentiment está con datos parciales (put/call CBOE no disponible).")
if metrics.get("cov_market", 1) < 0.7:
    warns.append("Market Stress con cobertura parcial (revisar term structure / crédito).")
if warns:
    st.warning(" ".join(warns))

st.info("Lectura táctica IA/Semis: " + tactical_reading(
    metrics.get("ai_semis_stress_score"),
    metrics.get("capitulation_score"),
    metrics.get("s_term"),
))

with st.expander("Cómo leer los 5 scores", expanded=True):
    st.markdown(
        "Los scores van de **0 a 100** y representan el **percentil** del estado actual "
        "frente a su propio régimen de ~2 años. 50 = mediana histórica; 80+ = cuasi-máximos. "
        "No es una probabilidad: es un índice de presión contextualizado."
    )
    st.dataframe(pd.DataFrame(SCORE_RANGES), use_container_width=True, hide_index=True)
    st.dataframe(pd.DataFrame(SCORE_EXPLANATIONS), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------
# Term structure de volatilidad (NUEVO)
# ---------------------------------------------------------------------
st.subheader("Estructura temporal de volatilidad")
ts_cols = st.columns(4)
ts_cols[0].metric("VIX9D", f"{metrics.get('VIX9D', float('nan')):.1f}" if metrics.get("VIX9D") == metrics.get("VIX9D") else "s/d")
ts_cols[1].metric("VIX (30d)", f"{metrics.get('VIX', float('nan')):.1f}" if metrics.get("VIX") == metrics.get("VIX") else "s/d")
ts_cols[2].metric("VIX3M", f"{metrics.get('VIX3M', float('nan')):.1f}" if metrics.get("VIX3M") == metrics.get("VIX3M") else "s/d")
vv = metrics.get("VIX/VIX3M")
estado = "s/d"
if vv == vv:
    estado = "BACKWARDATION (estrés)" if vv > 1 else "Contango (normal)"
ts_cols[3].metric("VIX/VIX3M", f"{vv:.2f}" if vv == vv else "s/d", estado)
st.caption("VIX/VIX3M > 1 (backwardation) = el mercado paga más por volatilidad inmediata que a 3 meses → estrés agudo de corto plazo. "
           "Es la señal de estrés más limpia del tablero.")

# ---------------------------------------------------------------------
# Indicadores con percentil y señal
# ---------------------------------------------------------------------
st.subheader("Indicadores principales (valor + score percentil)")
indic_rows = [
    ("VIX", "VIX", "s_vix"),
    ("VXN", "VXN", "s_vxn"),
    ("VVIX", "VVIX", "s_vvix"),
    ("SKEW", "SKEW", "s_skew"),
    ("VXN/VIX", "VXN/VIX", "s_vxn_vix"),
    ("VIX/VIX3M (term)", "VIX/VIX3M", "s_term"),
    ("Salto VXN 1d", "VXN_chg_1d", "s_vxn_chg"),
    ("Cambio 10Y 1d", "US10Y_chg_1d", "s_rates"),
    ("SMH-QQQ 5d %", "smh_qqq_5d", "s_smh_qqq_5"),
    ("SMH-QQQ 20d %", "smh_qqq_20d", "s_smh_qqq_20"),
    ("QQQ-SPY 20d %", "qqq_spy_20d", "s_qqq_spy_20"),
    ("NVDA-SMH 20d %", "nvda_smh_20d", "s_nvda_smh_20"),
    ("Crédito HYG-IEF 20d %", "HYG_IEF_20d", "s_credit"),
    ("Breadth % > MA50", "breadth_pct", "s_breadth"),
    ("Breadth semis %", "breadth_semis_pct", None),
    ("RSI SMH", "RSI_smh", "s_rsi_smh"),
    ("RSI QQQ", "RSI_qqq", "s_rsi_qqq"),
    ("Drawdown SMH 52w %", "DD_smh_52w", "s_dd_smh"),
]


def fmt(v):
    try:
        return f"{float(v):.2f}" if v == v else "s/d"
    except Exception:
        return "s/d"


rows = []
for name, vkey, skey in indic_rows:
    score = metrics.get(skey) if skey else None
    rows.append({
        "Indicador": name,
        "Valor": fmt(metrics.get(vkey)),
        "Score (0-100)": (f"{float(score):.0f}" if (score is not None and score == score) else "s/d"),
    })
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with st.expander("Rangos y fundamentos de cada indicador", expanded=False):
    st.markdown("En v4 casi todos los indicadores se miden por **percentil sobre ~2 años**: "
                "no hay umbral fijo, se compara contra el propio régimen del indicador.")
    st.dataframe(pd.DataFrame(INDICATOR_REFERENCE), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------
# Opciones (Yahoo)
# ---------------------------------------------------------------------
if include_options:
    st.subheader("Opciones · vencimiento cercano a 30 días")
    if options_df.empty:
        st.warning("No se pudieron descargar opciones en esta actualización.")
    else:
        disp = options_df.copy()
        ok = int((disp.get("status") == "OK").sum()) if "status" in disp else 0
        st.caption(f"Opciones: {ok} OK / {len(disp) - ok} con error. Fuente: Yahoo Finance (demorada).")
        for col in ["atm_iv", "put_skew_95_105"]:
            if col in disp.columns:
                disp[col] = disp[col] * 100
        cols = [c for c in ["ticker", "status", "spot", "expiration", "days_to_exp", "atm_iv",
                            "expected_move_%", "put_call_volume_ratio", "put_call_oi_ratio",
                            "put_skew_95_105", "error"] if c in disp.columns]
        st.dataframe(disp[cols], use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------
# Gráficos intradía
# ---------------------------------------------------------------------
st.subheader("Gráficos intradía")
if intraday.empty:
    st.warning("No se descargaron precios intradía.")
else:
    df = intraday.copy().ffill()
    tabs = st.tabs(["Volatilidad", "Term structure", "Relativos", "Semis / IA"])
    with tabs[0]:
        vols = [c for c in ["^VIX", "^VXN", "^VVIX", "^SKEW"] if c in df.columns]
        if vols:
            st.plotly_chart(px.line(df[vols].reset_index(), x=df.index.name or "Datetime",
                                    y=vols, title="VIX / VXN / VVIX / SKEW"), use_container_width=True)
    with tabs[1]:
        ts = [c for c in ["^VIX9D", "^VIX", "^VIX3M", "^VIX6M"] if c in df.columns]
        if ts:
            st.plotly_chart(px.line(df[ts].reset_index(), x=df.index.name or "Datetime",
                                    y=ts, title="Term structure VIX"), use_container_width=True)
    with tabs[2]:
        rel = pd.DataFrame(index=df.index)
        if "QQQ" in df and "SPY" in df:
            rel["QQQ/SPY"] = df["QQQ"] / df["SPY"]
        if "SMH" in df and "QQQ" in df:
            rel["SMH/QQQ"] = df["SMH"] / df["QQQ"]
        if "NVDA" in df and "SMH" in df:
            rel["NVDA/SMH"] = df["NVDA"] / df["SMH"]
        if not rel.empty:
            rel = rel / rel.iloc[0] * 100
            st.plotly_chart(px.line(rel.reset_index(), x=rel.index.name or "Datetime",
                                    y=rel.columns, title="Relativos normalizados = 100"), use_container_width=True)
    with tabs[3]:
        names = [c for c in ["QQQ", "SMH", "SOXX", "NVDA", "AMD", "AVGO", "MU", "MRVL"] if c in df.columns]
        norm = df[names].dropna(how="all").ffill()
        if not norm.empty:
            norm = norm / norm.iloc[0] * 100
            st.plotly_chart(px.line(norm.reset_index(), x=norm.index.name or "Datetime",
                                    y=names, title="IA/Semis normalizado = 100"), use_container_width=True)

# ---------------------------------------------------------------------
# Histórico de snapshots
# ---------------------------------------------------------------------
st.subheader("Histórico de scores")
hist = load_snapshots()
if hist.empty:
    st.caption("Todavía no hay histórico guardado.")
else:
    cols = [c for c in ["timestamp_utc", "general_risk_score", "ai_semis_stress_score",
                        "market_stress_score", "options_sentiment_score", "capitulation_score"]
            if c in hist.columns]
    last_hist = hist.tail(300)[cols].copy()
    st.dataframe(last_hist.tail(20), use_container_width=True, hide_index=True)
    if "timestamp_utc" in last_hist:
        last_hist["timestamp_utc"] = pd.to_datetime(last_hist["timestamp_utc"], errors="coerce")
        ycols = [c for c in cols if c != "timestamp_utc"]
        st.plotly_chart(px.line(last_hist, x="timestamp_utc", y=ycols, title="Scores guardados"),
                        use_container_width=True)

st.caption("Advertencia: Yahoo/CBOE pueden tener datos demorados, incompletos o cambiar estructura. Validar antes de operar.")
