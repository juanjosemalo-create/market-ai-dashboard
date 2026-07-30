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
    compute_composites, tactical_reading, traffic_light, term_traffic, indicator_light,
    entry_signal,
    SCORE_RANGES, SCORE_EXPLANATIONS, SCORE_MEANING, INDICATOR_REFERENCE, GLOSSARY,
)
from manual import render_manual, open_manual

st.set_page_config(page_title="AI / Semis Market Sentiment v5", layout="wide")
st.title("AI / Semis Market Sentiment Dashboard - v5")
st.caption("Scoring por percentil (~2 anios) + semaforos + pesos recalibrados con backtest. "
           "Datos gratuitos/demorados (Yahoo + CBOE). No es recomendacion de inversion.")

with st.sidebar:
    st.header("Configuracion")
    st.button("\U0001F4D6 Manual de la herramienta", use_container_width=True, on_click=open_manual)
    st.page_link(
        "pages/2_VIX_VIX3M_Probabilidades.py",
        label="Probabilidades VIX/VIX3M",
        icon="📊",
        use_container_width=True,
    )
    st.markdown("---")
    auto_refresh = st.toggle("Auto-refrescar", value=True)
    refresh_minutes = st.slider("Refresco (min)", 1, 30, DEFAULT_REFRESH_MINUTES, 1)
    include_options = st.toggle("Incluir opciones (Yahoo)", value=True)
    include_cboe = st.toggle("Incluir put/call CBOE (fragil)", value=True)
    save_history = st.toggle("Guardar snapshot", value=True)
    force = st.button("Actualizar ahora", use_container_width=True)
    st.caption(f"Ventana de percentil: {PCT_LOOKBACK} ruedas (~2 anios).")
    st.markdown("---")
    st.markdown("**Leyenda de semaforos**")
    st.markdown("\U0001F7E2 tranquilo  \U0001F7E1 ojo/presion  \U0001F534 alerta  \U0001F535 capitulacion (posible piso)")

# Si el manual esta abierto, mostrarlo y NO renderizar el tablero
if st.session_state.get("show_manual", False):
    render_manual()
    st.stop()

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
    cached_daily.clear(); cached_intraday.clear(); cached_cboe.clear(); cached_options.clear()

with st.spinner("Descargando datos..."):
    daily = cached_daily()
    intraday = cached_intraday()
    cboe = cached_cboe() if include_cboe else {}
    metrics = build_metrics(daily, intraday, cboe)
    metrics.update(compute_composites(metrics))
    options_df = cached_options() if include_options else pd.DataFrame()

if save_history and metrics.get("timestamp_utc"):
    save_snapshot(metrics)

st.caption(f"Ultima actualizacion local: {datetime.now():%Y-%m-%d %H:%M:%S} | "
           f"Timestamp fuente UTC: {metrics.get('timestamp_utc', 's/d')}")

# ---------------------------------------------------------------------
# SEMAFORO UNICO DE ENTRADA (lo mas accionable, va arriba de todo)
# ---------------------------------------------------------------------
es = entry_signal(metrics)
banner = f"### {es['emoji']} SEMAFORO DE ENTRADA: {es['nivel']}\n**{es['titulo']}.** {es['accion']}\n\n{es['detalle']}"
if es["emoji"] == "\U0001F7E2":
    st.success(banner)
elif es["emoji"] == "\U0001F7E1":
    st.warning(banner)
elif es["emoji"] == "\U0001F534":
    st.error(banner)
elif es["emoji"] == "\U0001F535":
    st.info(banner)
else:
    st.info(banner)
st.caption("Sintesis de las seniales que el backtest valido (term structure + credito + VIX). "
           "Es una guia de postura/exposicion, NO una recomendacion de compra/venta.")

# ---------------------------------------------------------------------
# 5 scores con SEMAFORO
# ---------------------------------------------------------------------
def metric_card(col, title, value, label_txt, bucket, contrarian=False):
    emoji, word = traffic_light(value, contrarian=contrarian)
    try:
        val = f"{float(value):.0f}/100" if value == value else "s/d"
    except Exception:
        val = "s/d"
    col.metric(f"{emoji} {title}", val, f"{label_txt} | {bucket}")


c1, c2, c3, c4, c5 = st.columns(5)
metric_card(c1, "General Risk", metrics.get("general_risk_score"),
            metrics.get("general_label", ""), metrics.get("general_bucket", ""))
metric_card(c2, "AI/Semis Risk", metrics.get("ai_semis_stress_score"),
            metrics.get("ai_semis_label", ""), metrics.get("ai_semis_bucket", ""))
metric_card(c3, "Market Stress", metrics.get("market_stress_score"),
            metrics.get("market_label", ""), metrics.get("market_bucket", ""))
metric_card(c4, "Options Sentiment", metrics.get("options_sentiment_score"),
            metrics.get("options_label", ""), metrics.get("options_bucket", ""))
metric_card(c5, "Capitulation", metrics.get("capitulation_score"),
            metrics.get("capitulation_label", ""), metrics.get("capitulation_bucket", ""),
            contrarian=True)

warns = []
if metrics.get("cov_options", 1) < 0.5:
    warns.append("Options Sentiment con datos parciales (put/call CBOE no disponible).")
if metrics.get("cov_market", 1) < 0.7:
    warns.append("Market Stress con cobertura parcial (revisar term structure / credito).")
if warns:
    st.warning(" ".join(warns))

st.info("Lectura tactica IA/Semis: " + tactical_reading(
    metrics.get("ai_semis_stress_score"), metrics.get("capitulation_score"), metrics.get("s_term")))

with st.expander("Que significa cada score (si sube / si baja / por que)", expanded=True):
    st.dataframe(pd.DataFrame(SCORE_MEANING), use_container_width=True, hide_index=True)
    st.markdown("**Rangos de color:**")
    st.dataframe(pd.DataFrame(SCORE_RANGES), use_container_width=True, hide_index=True)
    st.dataframe(pd.DataFrame(SCORE_EXPLANATIONS), use_container_width=True, hide_index=True)

with st.expander("Diccionario: que significa cada palabra (en criollo)", expanded=False):
    st.dataframe(pd.DataFrame(GLOSSARY), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------
# TERM STRUCTURE con semaforo de 4 estados (lo mas accionable)
# ---------------------------------------------------------------------
st.subheader("Term structure de volatilidad - el indicador mas confiable")
vv = metrics.get("VIX/VIX3M")
emoji, estado, expl = term_traffic(vv)
tcol1, tcol2 = st.columns([1, 3])
with tcol1:
    st.metric(f"{emoji} VIX/VIX3M", f"{vv:.2f}" if vv == vv else "s/d", estado)
with tcol2:
    st.markdown(f"**{emoji} {estado}.** {expl}")
    st.caption("Como leerlo: por debajo de 0,90 calma (verde). Entre 0,90 y 0,95 se empieza a tensar (amarillo). "
               "Entre 0,95 y 1,00 alerta (naranja): historicamente aca ya empezaban las bajas. Por encima de 1,00 "
               "backwardation (rojo): estres agudo. El backtest mostro que esta es LA senial que mejor anticipo las caidas.")
ts2 = st.columns(3)
ts2[0].metric("VIX9D (9 dias)", f"{metrics.get('VIX9D', float('nan')):.1f}" if metrics.get("VIX9D") == metrics.get("VIX9D") else "s/d")
ts2[1].metric("VIX (30 dias)", f"{metrics.get('VIX', float('nan')):.1f}" if metrics.get("VIX") == metrics.get("VIX") else "s/d")
ts2[2].metric("VIX3M (3 meses)", f"{metrics.get('VIX3M', float('nan')):.1f}" if metrics.get("VIX3M") == metrics.get("VIX3M") else "s/d")

st.caption(
    "El score del tablero mide intensidad relativa. La página estadística separa probabilidad de nuevo mínimo, "
    "caída adicional, cierre del horizonte y rebote; además muestra base, lift e intervalo conservador."
)
st.page_link(
    "pages/2_VIX_VIX3M_Probabilidades.py",
    label="Abrir probabilidades condicionadas y escenarios SPX",
    icon="📊",
    use_container_width=True,
)

# ---------------------------------------------------------------------
# Indicadores con semaforo + interpretacion direccional
# ---------------------------------------------------------------------
st.subheader("Indicadores (valor + semaforo + que significa)")
indic_rows = [
    ("VIX/VIX3M (term)", "VIX/VIX3M", "s_term", "Estres sistemico. >0,95 alerta, >1,0 alarma."),
    ("Credito HYG/IEF 20d", "HYG_IEF_20d", "s_credit", "Negativo = bonos riesgosos cayendo = estres de fondo."),
    ("VIX", "VIX", "s_vix", "Miedo del S&P. Percentil alto = nervioso para su regimen."),
    ("VXN", "VXN", "s_vxn", "Miedo del Nasdaq (tu sector)."),
    ("Salto VXN 1d", "VXN_chg_1d", "s_vxn_chg", "Cuanto salto el miedo tech hoy. Salto fuerte = mala senial."),
    ("Cambio 10Y 1d", "US10Y_chg_1d", "s_rates", "Tasas subiendo presionan a las tech (growth)."),
    ("SMH-QQQ 20d %", "smh_qqq_20d", "s_smh_qqq_20", "Negativo = semis cae mas que el Nasdaq (lidera la baja)."),
    ("QQQ-SPY 20d %", "qqq_spy_20d", "s_qqq_spy_20", "Negativo = tech cae mas que el mercado."),
    ("NVDA-SMH 20d %", "nvda_smh_20d", "s_nvda_smh_20", "Negativo = el lider (NVDA) ya no aguanta."),
    ("Breadth % > MA50", "breadth_pct", "s_breadth", "Bajo = pocas acciones aguantan. Mercado debil por dentro."),
    ("RSI SMH", "RSI_smh", "s_rsi_smh", "Bajo (<30) = sobrevendido, posible rebote."),
    ("Drawdown SMH 52w %", "DD_smh_52w", "s_dd_smh", "Cuanto esta abajo de su maximo del anio."),
    ("VXN/VIX (informativo)", "VXN/VIX", None, "Solo informa si el nervio esta en tech vs mercado. NO predice (backtest)."),
]


def fmt(v):
    try:
        return f"{float(v):.2f}" if v == v else "s/d"
    except Exception:
        return "s/d"


rows = []
for name, vkey, skey, meaning in indic_rows:
    score = metrics.get(skey) if skey else None
    light = indicator_light(score) if skey else "\u2139\ufe0f"
    rows.append({
        "Sem.": light, "Indicador": name, "Valor": fmt(metrics.get(vkey)),
        "Score": (f"{float(score):.0f}" if (score is not None and score == score) else "-"),
        "Que significa": meaning,
    })
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with st.expander("Cuales seniales sirven de verdad (resultado del backtest)", expanded=False):
    st.markdown("Esto sale de testear cada senial contra 17 anios de caidas reales. "
                "**Lift** = cuanto mejora contra el azar (1 = inutil, 3 = la caida es 3x mas probable).")
    st.dataframe(pd.DataFrame(INDICATOR_REFERENCE), use_container_width=True, hide_index=True)
    st.markdown("**Por que sacamos VXN/VIX del puntaje de riesgo:** en los 17 anios, las veces que "
                "estuvo alto NO vinieron seguidas de caidas (lift menor a 1). Sirve para DESCRIBIR donde "
                "esta el nervio (tech vs mercado general), no para ANTICIPAR la baja. Por eso quedo como "
                "dato informativo y le sacamos el voto en el puntaje.")

# ---------------------------------------------------------------------
# Opciones
# ---------------------------------------------------------------------
if include_options:
    st.subheader("Opciones - vencimiento cercano a 30 dias")
    if options_df.empty:
        st.warning("No se pudieron descargar opciones.")
    else:
        disp = options_df.copy()
        ok = int((disp.get("status") == "OK").sum()) if "status" in disp else 0
        st.caption(f"Opciones: {ok} OK / {len(disp) - ok} con error. Para tu uso, mira sobre todo 'expected_move_%'.")
        for col in ["atm_iv", "put_skew_95_105"]:
            if col in disp.columns:
                disp[col] = disp[col] * 100
        cols = [c for c in ["ticker", "status", "spot", "expiration", "days_to_exp", "atm_iv",
                            "expected_move_%", "put_call_volume_ratio", "put_call_oi_ratio",
                            "put_skew_95_105", "error"] if c in disp.columns]
        st.dataframe(disp[cols], use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------
# Graficos
# ---------------------------------------------------------------------
st.subheader("Graficos intradia")
if intraday.empty:
    st.warning("No se descargaron precios intradia.")
else:
    df = intraday.copy().ffill()
    tabs = st.tabs(["Volatilidad", "Term structure", "Relativos", "Semis / IA"])
    with tabs[0]:
        vols = [c for c in ["^VIX", "^VXN", "^VVIX", "^SKEW"] if c in df.columns]
        if vols:
            st.plotly_chart(px.line(df[vols].reset_index(), x=df.index.name or "Datetime", y=vols,
                                    title="VIX / VXN / VVIX / SKEW"), use_container_width=True)
    with tabs[1]:
        ts = [c for c in ["^VIX9D", "^VIX", "^VIX3M", "^VIX6M"] if c in df.columns]
        if ts:
            st.plotly_chart(px.line(df[ts].reset_index(), x=df.index.name or "Datetime", y=ts,
                                    title="Term structure VIX"), use_container_width=True)
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
            st.plotly_chart(px.line(rel.reset_index(), x=rel.index.name or "Datetime", y=rel.columns,
                                    title="Relativos normalizados = 100"), use_container_width=True)
    with tabs[3]:
        names = [c for c in ["QQQ", "SMH", "SOXX", "NVDA", "AMD", "AVGO", "MU", "MRVL"] if c in df.columns]
        norm = df[names].dropna(how="all").ffill()
        if not norm.empty:
            norm = norm / norm.iloc[0] * 100
            st.plotly_chart(px.line(norm.reset_index(), x=norm.index.name or "Datetime", y=names,
                                    title="IA/Semis normalizado = 100"), use_container_width=True)

# ---------------------------------------------------------------------
# Historico de scores
# ---------------------------------------------------------------------
st.subheader("Historico de scores")
hist = load_snapshots()
if hist.empty:
    st.caption("Todavia no hay historico guardado.")
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

st.caption("Advertencia: Yahoo/CBOE pueden tener datos demorados o incompletos. Validar antes de operar.")
