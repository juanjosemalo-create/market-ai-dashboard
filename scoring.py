from __future__ import annotations

import math
import numpy as np
import pandas as pd


# =====================================================================
# Helpers base
# =====================================================================
def clamp(x: float, low: float = 0.0, high: float = 100.0) -> float:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return float("nan")
    return max(low, min(high, float(x)))


def pct_score(series, high_is_risk: bool = True,
              lookback: int = 504, min_obs: int = 90) -> float:
    """Score 0-100 = percentil del ULTIMO valor dentro de su propia historia.

    Esta es la mejora central de v4: en vez de umbrales fijos absolutos,
    cada indicador se mide contra su propio régimen de los últimos ~2 años.
    - high_is_risk=True  -> valor alto = score alto (ej. VIX, VIX/VIX3M).
    - high_is_risk=False -> valor bajo = score alto (ej. breadth, RSI, spreads relativos).
    """
    s = pd.to_numeric(pd.Series(series), errors="coerce").dropna()
    if len(s) < min_obs:
        return float("nan")
    s = s.iloc[-lookback:]
    last = s.iloc[-1]
    if pd.isna(last):
        return float("nan")
    pct = float((s <= last).mean() * 100.0)   # percentil rank del último valor
    return clamp(pct if high_is_risk else 100.0 - pct)


def score_linear(value: float, green: float, red: float, invert: bool = False) -> float:
    """Score 0-100 con umbrales fijos. Se conserva SOLO para put/call (sin historia)."""
    if pd.isna(value):
        return float("nan")
    if invert:
        raw = (green - value) / (green - red) * 100
    else:
        raw = (value - green) / (red - green) * 100
    return clamp(raw)


def label(score: float) -> str:
    if pd.isna(score):
        return "Sin dato"
    if score < 30:
        return "Riesgo bajo"
    if score < 50:
        return "Neutral / normal"
    if score < 65:
        return "Presión moderada"
    if score < 80:
        return "Riesgo alto"
    return "Estrés extremo"


def score_bucket(score: float) -> str:
    if pd.isna(score):
        return "Sin dato"
    if score < 30:
        return "0–30"
    if score < 50:
        return "30–50"
    if score < 65:
        return "50–65"
    if score < 80:
        return "65–80"
    return "80–100"


def weighted_average(items: dict) -> float:
    """items: nombre -> (score, peso). Ignora NaN y re-normaliza por el peso presente."""
    total_w = 0.0
    total = 0.0
    for _, (score, weight) in items.items():
        if score is None or pd.isna(score):
            continue
        total += float(score) * float(weight)
        total_w += float(weight)
    if total_w == 0:
        return float("nan")
    return total / total_w


def _coverage(items: dict) -> float:
    """Fracción del peso que efectivamente tuvo dato (para avisar lecturas parciales)."""
    have = sum(w for _, (s, w) in items.items() if not (s is None or pd.isna(s)))
    tot = sum(w for _, (s, w) in items.items())
    return have / tot if tot else 0.0


# =====================================================================
# Composites
# =====================================================================
def compute_composites(m: dict) -> dict:
    """Recibe el dict de metrics (con los component scores ya calculados en
    data_sources.build_metrics) y arma los 5 scores compuestos."""

    g = lambda k: m.get(k)

    market_items = {
        "VIX":           (g("s_vix"),        0.25),
        "VVIX":          (g("s_vvix"),       0.10),
        "Term VIX/3M":   (g("s_term"),       0.25),
        "Crédito HYG/IEF": (g("s_credit"),   0.20),
        "Tasas 10Y":     (g("s_rates"),      0.10),
        "SKEW":          (g("s_skew"),       0.10),
    }
    market_stress = weighted_average(market_items)

    ai_items = {
        "VXN":           (g("s_vxn"),        0.15),
        "VXN/VIX":       (g("s_vxn_vix"),    0.20),
        "SMH-QQQ 5d":    (g("s_smh_qqq_5"),  0.10),
        "SMH-QQQ 20d":   (g("s_smh_qqq_20"), 0.20),
        "QQQ-SPY 20d":   (g("s_qqq_spy_20"), 0.15),
        "NVDA-SMH 20d":  (g("s_nvda_smh_20"),0.10),
        "VXN cambio 1d": (g("s_vxn_chg"),    0.10),
    }
    ai_semis_stress = weighted_average(ai_items)

    # Opciones: put/call de CBOE (fuente frágil, umbrales fijos, puede venir NaN).
    options_items = {
        "Total PC":  (g("s_total_pc"),  0.15),
        "Equity PC": (g("s_equity_pc"), 0.15),
        "Index PC":  (g("s_index_pc"),  0.20),
        "ETF PC":    (g("s_etf_pc"),    0.20),
        "SPX PC":    (g("s_spx_pc"),    0.20),
        "VIX PC":    (g("s_vix_pc"),    0.10),
    }
    options_sentiment = weighted_average(options_items)

    # Capitulación: sobreventa / extremos ya descontados (alto = posible piso/rebote).
    cap_items = {
        "RSI SMH":      (g("s_rsi_smh"),   0.20),
        "RSI QQQ":      (g("s_rsi_qqq"),   0.10),
        "Drawdown SMH": (g("s_dd_smh"),    0.20),
        "Breadth":      (g("s_breadth"),   0.20),
        "VIX extremo":  (g("s_vix"),       0.15),
        "Equity PC ext":(g("s_equity_pc"), 0.15),
    }
    capitulation = weighted_average(cap_items)

    general_items = {
        "Market":       (market_stress,     0.30),
        "AI/Semis":     (ai_semis_stress,   0.35),
        "Options":      (options_sentiment, 0.20),
        "Capitulation": (capitulation,      0.15),
    }
    general = weighted_average(general_items)

    out = {
        "market_stress_score": market_stress,
        "ai_semis_stress_score": ai_semis_stress,
        "options_sentiment_score": options_sentiment,
        "capitulation_score": capitulation,
        "general_risk_score": general,
        "market_label": label(market_stress),
        "ai_semis_label": label(ai_semis_stress),
        "options_label": label(options_sentiment),
        "capitulation_label": label(capitulation),
        "general_label": label(general),
        "market_bucket": score_bucket(market_stress),
        "ai_semis_bucket": score_bucket(ai_semis_stress),
        "options_bucket": score_bucket(options_sentiment),
        "capitulation_bucket": score_bucket(capitulation),
        "general_bucket": score_bucket(general),
        # cobertura de datos por bloque (para avisar si una lectura es parcial)
        "cov_market": _coverage(market_items),
        "cov_ai_semis": _coverage(ai_items),
        "cov_options": _coverage(options_items),
        "cov_capitulation": _coverage(cap_items),
    }
    return out


# =====================================================================
# Lectura táctica  -  CUALITATIVA (sin porcentajes inventados)
# =====================================================================
def tactical_reading(ai_semis: float, capitulation: float,
                     term_score: float = float("nan")) -> str:
    """Lectura cualitativa, NO una probabilidad calibrada.

    Antes la función devolvía rangos tipo '60-70%' que no salían de ningún
    backtest. Eso es falsa precisión. Hasta tener calibración real contra
    retornos forward, esto es una heurística de postura, no una probabilidad.
    """
    if pd.isna(ai_semis):
        return "Sin dato suficiente para una lectura táctica."

    if not pd.isna(capitulation) and capitulation > 75:
        base = ("Sentimiento IA/semis muy estresado, PERO con señales de sobreventa/"
                "capitulación: el riesgo se vuelve asimétrico al alza (probable rebote técnico). "
                "Postura: no perseguir la baja.")
    elif ai_semis < 35:
        base = "Sentimiento IA/semis tranquilo. Sin señal de deterioro relevante."
    elif ai_semis < 50:
        base = "Sentimiento IA/semis neutral. Conviene mirar los componentes individuales."
    elif ai_semis < 65:
        base = "Presión moderada sobre IA/semis. Vigilar continuidad bajista, sin estrés severo aún."
    elif ai_semis < 80:
        base = "Presión relevante sobre IA/semis. Tech/semis liderando la baja; gestionar exposición."
    else:
        base = "Estrés alto en IA/semis. Riesgo de continuidad, salvo que aparezca capitulación."

    if not pd.isna(term_score) and term_score > 70:
        base += " La estructura temporal de volatilidad está en backwardation (estrés agudo de corto plazo)."
    return base + "  [Lectura heurística, no calibrada — no es una probabilidad.]"


# =====================================================================
# Tablas de referencia (didácticas) para la UI
# =====================================================================
SCORE_RANGES = [
    {"Rango": "0–30", "Etiqueta": "Riesgo bajo", "Lectura": "Indicadores en la mitad baja de su régimen de 2 años. Baja presión."},
    {"Rango": "30–50", "Etiqueta": "Neutral / normal", "Lectura": "Sin señal fuerte. Mirar los componentes."},
    {"Rango": "50–65", "Etiqueta": "Presión moderada", "Lectura": "Indicadores por encima de su mediana histórica. Sube el riesgo."},
    {"Rango": "65–80", "Etiqueta": "Riesgo alto", "Lectura": "Zona alta del régimen de 2 años. Presión vendedora relevante."},
    {"Rango": "80–100", "Etiqueta": "Estrés extremo", "Lectura": "Cuasi-máximos de 2 años. Riesgo alto, pero aumenta la chance de rebote si hay capitulación."},
]

SCORE_EXPLANATIONS = [
    {"Score": "General Risk", "Qué mide": "Riesgo compuesto del tablero.",
     "Fórmula": "30% Market + 35% AI/Semis + 20% Options + 15% Capitulation.",
     "Uso": "Resumen general: modo normal, alerta o estrés."},
    {"Score": "AI/Semis Risk", "Qué mide": "Presión específica sobre Nasdaq, semis e IA.",
     "Fórmula": "VXN, VXN/VIX, SMH-QQQ (5d/20d), QQQ-SPY 20d, NVDA-SMH 20d, salto de VXN — todos por percentil.",
     "Uso": "El score más importante para el trade IA. Alto = tech/semis lideran la baja."},
    {"Score": "Market Stress", "Qué mide": "Estrés sistémico, no solo tech.",
     "Fórmula": "VIX, VVIX, VIX/VIX3M (term structure), HYG/IEF (crédito), 10Y, SKEW — por percentil.",
     "Uso": "Distingue baja sectorial de deterioro sistémico. El term structure es el núcleo."},
    {"Score": "Options Sentiment", "Qué mide": "Demanda de protección en opciones (put/call CBOE).",
     "Fórmula": "Put/call total, equity, index, ETF, SPX y VIX. FUENTE FRÁGIL (scraping CBOE) — puede venir parcial.",
     "Uso": "Alto = más cobertura. Extremo puede ser contrarian."},
    {"Score": "Capitulation", "Qué mide": "Si el miedo / la sobreventa ya están en zona extrema.",
     "Fórmula": "RSI (SMH/QQQ) bajo, drawdown profundo, breadth baja, VIX extremo, equity put/call alto.",
     "Uso": "Alto NO siempre es bajista: arriba de 75 sube el riesgo de rebote violento."},
]

INDICATOR_REFERENCE = [
    {"Indicador": "VIX / VXN / VVIX / SKEW", "Lectura": "Percentil del nivel actual vs últimos ~2 años.",
     "Fundamento": "Mide cuán cara está la protección HOY relativo a su propio régimen, no contra un umbral fijo."},
    {"Indicador": "VIX/VIX3M (term structure)", "Lectura": "Percentil del ratio. >1 = backwardation = estrés agudo de corto plazo.",
     "Fundamento": "Señal de estrés más limpia que SKEW/VVIX. Curva invertida = el mercado paga más por vol inmediata que por vol a 3 meses."},
    {"Indicador": "VXN/VIX", "Lectura": "Percentil del ratio. Alto = estrés concentrado en Nasdaq/IA.",
     "Fundamento": "Aísla si el problema es tech o todo el mercado."},
    {"Indicador": "SMH-QQQ, QQQ-SPY, NVDA-SMH", "Lectura": "Percentil del spread de retorno a 5d/20d. Bajo (muy negativo) = liderazgo bajista del sector.",
     "Fundamento": "Multi-ventana en vez de 1 día = menos ruido. Mide momentum relativo, no una sola rueda."},
    {"Indicador": "Breadth (% sobre MA50)", "Lectura": "Percentil de la amplitud. Baja = pocos nombres aguantan.",
     "Fundamento": "Capta deterioro interno que los índices (concentrados) esconden."},
    {"Indicador": "RSI (14) SMH/QQQ", "Lectura": "Percentil invertido. RSI bajo = sobreventa = capitulación.",
     "Fundamento": "Componente de piso/rebote, no de continuidad."},
    {"Indicador": "Drawdown 52w", "Lectura": "Percentil de la profundidad de la caída desde el máximo de 52 semanas.",
     "Fundamento": "Cuán estirada está la goma a la baja."},
    {"Indicador": "Crédito HYG/IEF", "Lectura": "Percentil del spread de retorno HY vs Treasuries. Bajo = estrés crediticio.",
     "Fundamento": "HYG/IEF aísla crédito mejor que HYG/LQD (que mete duración)."},
    {"Indicador": "Cambio 10Y / salto de VXN", "Lectura": "Percentil del CAMBIO reciente, no del nivel.",
     "Fundamento": "El sentimiento táctico vive en la velocidad del movimiento, no solo en el nivel."},
    {"Indicador": "Put/Call (CBOE)", "Lectura": "Umbrales fijos (sin historia). Fuente de scraping frágil.",
     "Fundamento": "Demanda de cobertura. Si viene NaN, Options/Capitulation quedan parciales."},
]
