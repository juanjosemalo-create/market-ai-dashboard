from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from shared_market_cache import cached_intraday_shared

from vix_probability_engine import (
    Row,
    SCENARIO_COLORS,
    URL_SPX_FRED,
    URL_SPX_YAHOO,
    URL_VIX,
    URL_VIX3M,
    apply_live_snapshot,
    build_analysis,
    fetch_all,
    metric_lift,
    pct,
)

st.set_page_config(
    page_title="VIX/VIX3M · Probabilidades SPX",
    page_icon="📊",
    layout="wide",
)

st.markdown(
    """
<style>
.block-container {padding-top: 1.3rem; padding-bottom: 3rem;}
[data-testid="stMetric"] {background: rgba(124,124,124,.06); border: 1px solid rgba(124,124,124,.16); padding: 14px; border-radius: 12px;}
.prob-card {border: 1px solid rgba(124,124,124,.18); border-radius: 12px; padding: 14px 15px; min-height: 150px; background: rgba(124,124,124,.045);}
.prob-value {font-size: 1.8rem; font-weight: 750; line-height: 1.1;}
.prob-title {font-size: .92rem; margin-top: 5px;}
.prob-range {font-size: .78rem; opacity: .72; margin-top: 7px;}
.prob-lift {font-size: .82rem; font-weight: 650; margin-top: 7px;}
.scenario-box {border-radius: 14px; padding: 18px 20px; border-left: 7px solid; background: rgba(124,124,124,.055);}
.small-note {font-size: .83rem; opacity: .75;}
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)
def cached_historical_market_data():
    # Historia oficial para calibrar probabilidades. No necesita refresco intradía.
    return fetch_all()


def _last_value(frame: pd.DataFrame, column: str):
    if column not in frame.columns:
        return None, None
    series = pd.to_numeric(frame[column], errors="coerce").ffill().dropna()
    if series.empty:
        return None, None
    return float(series.iloc[-1]), series.index[-1]


def _live_snapshot(frame: pd.DataFrame) -> dict:
    vix, ts_vix = _last_value(frame, "^VIX")
    vix3m, ts_vix3m = _last_value(frame, "^VIX3M")
    spx, ts_spx = _last_value(frame, "^GSPC")
    timestamps = [ts for ts in (ts_vix, ts_vix3m, ts_spx) if ts is not None]
    latest_ts = max(timestamps) if timestamps else None
    day = latest_ts.date().isoformat() if latest_ts is not None else None
    return {
        "vix": vix,
        "vix3m": vix3m,
        "spx": spx,
        "day": day,
        "timestamp": str(latest_ts) if latest_ts is not None else None,
    }


with st.sidebar:
    st.header("Motor probabilístico")
    st.page_link("app.py", label="Volver al tablero principal", icon="↩️")
    st.divider()
    auto_refresh = st.toggle("Auto-refrescar intradía", value=True)
    refresh_minutes = st.slider("Refresco (min)", 1, 30, 5, 1)
    refresh = st.button("🔄 Actualizar datos ahora", use_container_width=True, type="primary")
    if refresh:
        cached_intraday_shared.clear()
        # La historia sólo se fuerza si el usuario lo pide; normalmente Cboe cambia al cierre.
        cached_historical_market_data.clear()
    st.caption("El ratio actual usa el mismo snapshot intradía que el tablero principal. Cboe se usa para la calibración histórica.")
    st.divider()
    st.markdown(
        """
**Cómo leerlo**

- **Probabilidad condicionada:** frecuencia en casos con la misma señal.
- **Base:** frecuencia habitual sin condicionar.
- **Lift:** cuántas veces aumenta o reduce la frecuencia frente a la base.
- **Límite conservador:** extremo inferior del intervalo estadístico del 95%.
        """
    )
    st.caption("Uso analítico. No constituye recomendación de inversión.")

if auto_refresh:
    st_autorefresh(interval=refresh_minutes * 60 * 1000, key="vix_probability_refresh")

st.title("VIX/VIX3M · Probabilidades y escenarios para el SPX")
st.caption(
    "Complementa los scores del tablero principal con frecuencias históricas condicionadas. "
    "Separa recorrido adverso, cierre del horizonte y recuperación posterior."
)

try:
    with st.spinner("Descargando mercado y actualizando el escenario…"):
        rows, meta = cached_historical_market_data()
        intraday = cached_intraday_shared()
        live = _live_snapshot(intraday)
        if live["vix"] is not None and live["vix3m"] is not None:
            rows, meta = apply_live_snapshot(
                rows,
                meta,
                vix=live["vix"],
                vix3m=live["vix3m"],
                spx=live["spx"],
                day=live["day"],
                timestamp=live["timestamp"],
                source="Yahoo Finance intradía · caché compartida con el tablero principal",
            )
        else:
            meta = dict(meta)
            meta["warnings"] = list(meta.get("warnings", [])) + [
                "Yahoo no entregó VIX/VIX3M intradía; se muestra el último cierre oficial de Cboe."
            ]
        analysis = build_analysis(rows, meta)
except Exception as exc:
    st.error("No fue posible descargar o procesar los datos.")
    st.exception(exc)
    st.info(
        "Probá nuevamente con el botón de actualización. Puede existir una interrupción temporal "
        "en Cboe, Yahoo o FRED."
    )
    st.stop()

current: Row = analysis["current"]
scenario = analysis["scenario"]
level = scenario["level"]

current_source = meta.get("current_source", "Cboe · cierre diario")
live_time = meta.get("live_timestamp")
st.success(
    f"Datos al {current.day} · {meta['aligned_rows']:,} ruedas alineadas · "
    f"Snapshot actual: {current_source}" + (f" · {live_time}" if live_time else "")
)
st.caption(f"Historia SPX para el backtest: {meta['spx_source']} · Último cierre oficial alineado: {meta.get('official_last_date', meta.get('last_date', current.day))}")
if meta["warnings"]:
    st.warning(" | ".join(meta["warnings"]))

kpi_cols = st.columns(6)
kpis = [
    ("VIX", f"{current.vix:.2f}", f"Ratio Δ1d {current.delta1:+.3f}"),
    ("VIX3M", f"{current.vix3m:.2f}", "Horizonte aproximado: 3 meses"),
    ("VIX/VIX3M", f"{current.ratio:.3f}", f"Δ5d {current.delta5:+.3f}"),
    ("SPX", f"{current.spx:,.2f}", f"DD20 {pct(current.dd20)}"),
    ("Persistencia ≥0,95", f"{current.persist95} ruedas", f"≥1,00: {current.persist100}"),
    ("Pico 20 ruedas", f"{current.peak20:.3f}", f"Hace {current.days_from_peak20} ruedas"),
]
for col, (label, value, delta) in zip(kpi_cols, kpis):
    col.metric(label, value, delta)

left, right = st.columns([1.05, 1], gap="large")
with left:
    color = SCENARIO_COLORS[level]
    st.markdown(
        f"""
<div class="scenario-box" style="border-left-color:{color}">
<div class="small-note">ESTADO ACTUAL · NIVEL {level}/8</div>
<div style="font-size:1.75rem;font-weight:800;color:{color};margin:4px 0 8px 0">{scenario['name']}</div>
<div>{scenario['description']}</div>
<br>
<div><b>Sesgo operativo:</b> {scenario['framework']['bias']}</div>
<div class="small-note">{scenario['framework']['text']}</div>
</div>
""",
        unsafe_allow_html=True,
    )
with right:
    st.subheader("Supuestos activados")
    for item in scenario["assumptions"]:
        st.markdown(f"- {item}")
    st.markdown(f"**Próximo cambio de estado:** {scenario['next_trigger']}")

st.divider()

mode = st.radio(
    "Motor estadístico",
    options=["Regla exacta", "Casos análogos"],
    horizontal=True,
    help=(
        "La regla exacta exige la misma definición del escenario. Los análogos buscan observaciones "
        "similares en ratio, pendiente, persistencia y drawdown."
    ),
)
block = analysis["rule"] if mode == "Regla exacta" else analysis["analogs"]
metrics = block["metrics"]
baseline = analysis["baseline"]["metrics"]

st.caption(
    f"Muestra: {block['event_count']} episodios separados por al menos 10 ruedas · "
    f"confianza muestral: {block['confidence']}."
)


def probability_card(title: str, metric: dict, baseline_metric: dict) -> None:
    if not metric or not metric.get("n"):
        st.markdown(
            f'<div class="prob-card"><div class="prob-value">—</div><div class="prob-title">{title}</div></div>',
            unsafe_allow_html=True,
        )
        return

    lift = metric_lift(metric, baseline_metric)
    lift_text = "—" if lift is None else f"{lift:.2f}x"
    base_text = pct(baseline_metric.get("p")) if baseline_metric else "—"
    st.markdown(
        f"""
<div class="prob-card">
<div class="prob-value">{pct(metric['p'])}</div>
<div class="prob-title">{title}</div>
<div class="prob-lift">Base {base_text} · Lift {lift_text}</div>
<div class="prob-range">Límite conservador: {pct(metric['low'])} · Rango 95%: {pct(metric['low'])}–{pct(metric['high'])} · n={metric['n']}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def show_probability_grid(items):
    cols = st.columns(len(items))
    for ui_col, (title, key, horizon) in zip(cols, items):
        with ui_col:
            probability_card(
                title,
                metrics.get(horizon, {}).get(key, {}),
                baseline.get(horizon, {}).get(key, {}),
            )


st.subheader("1. ¿Es probable encontrar un precio inferior?")
show_probability_grid([
    ("Nuevo mínimo en 5 ruedas", "new_low", "5"),
    ("Caída ≥0,5% en 5 ruedas", "drop_05", "5"),
    ("Caída ≥1% en 5 ruedas", "drop_1", "5"),
    ("Caída ≥2% en 5 ruedas", "drop_2", "5"),
])

show_probability_grid([
    ("Caída ≥2% en 10 ruedas", "drop_2", "10"),
    ("Caída ≥3% en 10 ruedas", "drop_3", "10"),
    ("Caída ≥5% en 20 ruedas", "drop_5", "20"),
    ("Caída ≥10% en 60 ruedas", "drop_10", "60"),
])

st.subheader("2. ¿Cómo termina el horizonte?")
show_probability_grid([
    ("Cierre negativo a 5 ruedas", "close_negative", "5"),
    ("Cierre positivo a 10 ruedas", "close_positive", "10"),
    ("Cierre positivo a 20 ruedas", "close_positive", "20"),
    ("Cierre positivo a 60 ruedas", "close_positive", "60"),
])

median_cols = st.columns(4)
median_items = [
    ("Excursión adversa mediana 5d", "5", "median_min"),
    ("Retorno mediano 5d", "5", "median_end"),
    ("Excursión adversa mediana 20d", "20", "median_min"),
    ("Retorno mediano 20d", "20", "median_end"),
]
for col, (label, horizon, key) in zip(median_cols, median_items):
    col.metric(label, pct(metrics.get(horizon, {}).get(key)))

st.info(
    "Una probabilidad alta de nuevo mínimo no equivale a una probabilidad igualmente alta de cierre negativo. "
    "El mercado puede caer durante el recorrido y recuperar antes de terminar el horizonte."
)

st.divider()
st.subheader("Evolución: ratio y SPX normalizado")
recent = rows[-252:]
chart_df = pd.DataFrame(
    {
        "Fecha": pd.to_datetime([r.day for r in recent]),
        "VIX/VIX3M": [r.ratio for r in recent],
        "SPX base 100": [r.spx / recent[0].spx * 100 for r in recent],
    }
)
fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=chart_df["Fecha"],
        y=chart_df["VIX/VIX3M"],
        name="VIX/VIX3M",
        mode="lines",
        line=dict(width=2),
    )
)
fig.add_trace(
    go.Scatter(
        x=chart_df["Fecha"],
        y=chart_df["SPX base 100"],
        name="SPX base 100",
        mode="lines",
        yaxis="y2",
        line=dict(width=2),
    )
)
for threshold, label in [(0.95, "0,95"), (1.00, "1,00"), (1.10, "1,10")]:
    fig.add_hline(y=threshold, line_dash="dot", opacity=0.45, annotation_text=label)
fig.update_layout(
    height=470,
    margin=dict(l=20, r=20, t=30, b=20),
    hovermode="x unified",
    legend=dict(orientation="h", y=1.08),
    yaxis=dict(title="VIX/VIX3M"),
    yaxis2=dict(title="SPX base 100", overlaying="y", side="right"),
)
st.plotly_chart(fig, use_container_width=True)

st.subheader("Biblioteca comparativa de escenarios")
library_df = pd.DataFrame(analysis["library"])
for column in [
    "Nuevo mínimo 5d",
    "Caída ≥1% 5d",
    "Cierre negativo 5d",
    "Positivo 20d",
    "Mediana 20d",
]:
    library_df[column] = library_df[column].map(lambda x: pct(x) if pd.notna(x) else "—")
library_df["Lift nuevo mínimo"] = library_df["Lift nuevo mínimo"].map(
    lambda x: f"{x:.2f}x" if pd.notna(x) else "—"
)
st.dataframe(library_df, use_container_width=True, hide_index=True)

with st.expander("Ver fechas de los casos análogos"):
    st.write(" · ".join(analysis["analogs"]["dates"]) or "Sin casos suficientes.")

with st.expander("Metodología, fuentes y limitaciones"):
    st.markdown(
        f"""
**Fuentes descargadas automáticamente**

- Cboe VIX: `{URL_VIX}`
- Cboe VIX3M: `{URL_VIX3M}`
- SPX principal: Yahoo Finance `^GSPC`
- SPX de respaldo: FRED `SP500`

**Definiciones**

- Las probabilidades son frecuencias históricas condicionadas al escenario.
- Los eventos se separan por al menos diez ruedas para reducir la repetición de un mismo episodio.
- El rango del 95% se calcula con el intervalo de Wilson.
- El **lift** es probabilidad condicionada dividida por probabilidad base.
- El **límite conservador** es el extremo inferior del intervalo del 95%, no una garantía mínima.

**Limitaciones**

- Las observaciones no son experimentos independientes.
- Los escenarios extremos tienen pocas observaciones.
- La relación puede cambiar por régimen monetario o microestructura.
- Un nuevo mínimo intraperíodo no implica cierre negativo.
- Debe combinarse con precio, breadth, crédito, VVIX, VIX9D, skew y el resto del tablero principal.
        """
    )

summary_df = pd.DataFrame(
    [
        {
            "fecha": current.day,
            "vix": current.vix,
            "vix3m": current.vix3m,
            "spx": current.spx,
            "ratio": current.ratio,
            "delta_5d": current.delta5,
            "persistencia_095": current.persist95,
            "persistencia_100": current.persist100,
            "escenario": scenario["name"],
            "nivel": level,
            "casos_regla_exacta": analysis["rule"]["event_count"],
            "prob_nuevo_minimo_5d": analysis["rule"]["metrics"].get("5", {}).get("new_low", {}).get("p"),
            "prob_caida_1pct_5d": analysis["rule"]["metrics"].get("5", {}).get("drop_1", {}).get("p"),
            "prob_cierre_negativo_5d": analysis["rule"]["metrics"].get("5", {}).get("close_negative", {}).get("p"),
            "prob_positivo_20d": analysis["rule"]["metrics"].get("20", {}).get("close_positive", {}).get("p"),
        }
    ]
)
st.download_button(
    "Descargar resumen actual en CSV",
    data=summary_df.to_csv(index=False).encode("utf-8-sig"),
    file_name=f"vix_vix3m_escenario_{current.day}.csv",
    mime="text/csv",
)

st.caption(
    "Herramienta estadística educativa. Las frecuencias históricas no garantizan resultados futuros ni constituyen recomendación de inversión."
)
