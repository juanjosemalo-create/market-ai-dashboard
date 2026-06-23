from __future__ import annotations

import math
import pandas as pd


def clamp(x: float, low: float = 0.0, high: float = 100.0) -> float:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return float("nan")
    return max(low, min(high, float(x)))


def score_linear(value: float, green: float, red: float, invert: bool = False) -> float:
    """Return 0-100 risk score. green=low risk, red=high risk."""
    if pd.isna(value):
        return float("nan")
    if invert:
        # lower value = more risk
        raw = (green - value) / (green - red) * 100
    else:
        raw = (value - green) / (red - green) * 100
    return clamp(raw)


def score_negative_spread(value_pct: float, mild: float = 0.0, severe: float = -3.0) -> float:
    """Risk rises when relative return spread is negative. Inputs in percent points."""
    if pd.isna(value_pct):
        return float("nan")
    return score_linear(value_pct, mild, severe, invert=True)


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


def weighted_average(items: dict[str, tuple[float, float]]) -> float:
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


def compute_scores(row: dict) -> dict:
    """Compute dashboard scores from a latest row dict."""
    vix = row.get("VIX")
    vxn = row.get("VXN")
    vvix = row.get("VVIX")
    skew = row.get("SKEW")
    vxn_vix = row.get("VXN/VIX")
    qqq_spy_1d = row.get("QQQ_vs_SPY_1d")
    smh_qqq_1d = row.get("SMH_vs_QQQ_1d")
    nvda_smh_1d = row.get("NVDA_vs_SMH_1d")
    hyg_lqd_1d = row.get("HYG_vs_LQD_1d")
    tnx_1d = row.get("US10Y_change_1d")

    total_pc = row.get("total_put_call")
    equity_pc = row.get("equity_put_call")
    index_pc = row.get("index_put_call")
    etf_pc = row.get("etf_put_call")
    spx_pc = row.get("spx_put_call")
    vix_pc = row.get("vix_put_call")

    score_vix = score_linear(vix, 15, 28)
    score_vxn = score_linear(vxn, 20, 38)
    score_vvix = score_linear(vvix, 80, 120)
    score_skew = score_linear(skew, 125, 160)
    score_vxn_vix = score_linear(vxn_vix, 1.20, 1.60)
    score_qqq_spy = score_negative_spread(qqq_spy_1d, 0, -2.0)
    score_smh_qqq = score_negative_spread(smh_qqq_1d, 0, -3.0)
    score_nvda_smh = score_negative_spread(nvda_smh_1d, 0, -3.0)
    score_credit = score_negative_spread(hyg_lqd_1d, 0, -1.0)
    score_rates = score_linear(tnx_1d, 0, 0.25)  # TNX points ~= 10Y yield x10; 0.25 = 2.5 bps in yield

    score_total_pc = score_linear(total_pc, 0.70, 1.25)
    score_equity_pc = score_linear(equity_pc, 0.50, 0.95)
    score_index_pc = score_linear(index_pc, 0.90, 1.80)
    score_etf_pc = score_linear(etf_pc, 0.80, 1.70)
    score_spx_pc = score_linear(spx_pc, 1.00, 2.20)
    # VIX put/call low can imply many VIX calls = demand for vol upside, i.e. fear.
    score_vix_pc = score_linear(vix_pc, 0.75, 0.20, invert=True)

    market_stress = weighted_average({
        "VIX": (score_vix, 0.30),
        "VVIX": (score_vvix, 0.20),
        "SKEW": (score_skew, 0.15),
        "Credit": (score_credit, 0.20),
        "Rates": (score_rates, 0.15),
    })

    ai_semis_stress = weighted_average({
        "VXN": (score_vxn, 0.20),
        "VXN/VIX": (score_vxn_vix, 0.25),
        "QQQ vs SPY": (score_qqq_spy, 0.20),
        "SMH vs QQQ": (score_smh_qqq, 0.25),
        "NVDA vs SMH": (score_nvda_smh, 0.10),
    })

    options_sentiment = weighted_average({
        "Total PC": (score_total_pc, 0.15),
        "Equity PC": (score_equity_pc, 0.15),
        "Index PC": (score_index_pc, 0.20),
        "ETF PC": (score_etf_pc, 0.20),
        "SPX PC": (score_spx_pc, 0.20),
        "VIX PC": (score_vix_pc, 0.10),
    })

    capitulation = weighted_average({
        "VIX extreme": (score_linear(vix, 25, 40), 0.15),
        "VXN extreme": (score_linear(vxn, 32, 50), 0.20),
        "Equity PC extreme": (score_linear(equity_pc, 0.75, 1.15), 0.20),
        "ETF PC extreme": (score_linear(etf_pc, 1.25, 2.20), 0.15),
        "SMH liquidation": (score_negative_spread(smh_qqq_1d, -2, -6), 0.15),
        "QQQ liquidation": (score_negative_spread(qqq_spy_1d, -1.5, -4), 0.15),
    })

    general = weighted_average({
        "Market": (market_stress, 0.30),
        "AI/Semis": (ai_semis_stress, 0.35),
        "Options": (options_sentiment, 0.25),
        "Capitulation": (capitulation, 0.10),
    })

    return {
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
        "score_vix": score_vix,
        "score_vxn": score_vxn,
        "score_vvix": score_vvix,
        "score_skew": score_skew,
        "score_vxn_vix": score_vxn_vix,
        "score_qqq_spy": score_qqq_spy,
        "score_smh_qqq": score_smh_qqq,
        "score_nvda_smh": score_nvda_smh,
        "score_total_pc": score_total_pc,
        "score_equity_pc": score_equity_pc,
        "score_index_pc": score_index_pc,
        "score_etf_pc": score_etf_pc,
        "score_spx_pc": score_spx_pc,
        "score_vix_pc": score_vix_pc,
    }


def tactical_probability(score: float, capitulation_score: float) -> str:
    """Qualitative probability bucket for continuation downside."""
    if pd.isna(score):
        return "Sin dato suficiente"
    # When capitulation is too high, continuation probability stops rising linearly.
    if capitulation_score is not None and not pd.isna(capitulation_score) and capitulation_score > 75:
        return "50–60%: estrés extremo, pero aumenta riesgo de rebote violento"
    if score < 35:
        return "35–45%: baja probabilidad de continuidad"
    if score < 50:
        return "45–52%: neutral"
    if score < 65:
        return "52–60%: moderada"
    if score < 80:
        return "60–70%: moderadamente alta"
    return "65–75%: alta, salvo capitulación/rebote técnico"


SCORE_RANGES = [
    {"Rango": "0–30", "Etiqueta": "Riesgo bajo", "Lectura": "Mercado relativamente tranquilo. Baja presión vendedora."},
    {"Rango": "30–50", "Etiqueta": "Neutral / normal", "Lectura": "Sin señal fuerte. Conviene mirar los componentes."},
    {"Rango": "50–65", "Etiqueta": "Presión moderada", "Lectura": "Aumenta el riesgo de continuidad, pero sin estrés severo."},
    {"Rango": "65–80", "Etiqueta": "Riesgo alto", "Lectura": "Presión vendedora relevante. Cuidado con continuidad bajista."},
    {"Rango": "80–100", "Etiqueta": "Estrés extremo", "Lectura": "Riesgo alto, pero también aumenta probabilidad de rebote técnico si aparece capitulación."},
]

SCORE_EXPLANATIONS = [
    {"Score": "General Risk", "Qué mide": "Riesgo compuesto del dashboard.", "Fórmula": "30% Market Stress + 35% AI/Semis Risk + 25% Options Sentiment + 10% Capitulation.", "Uso": "Resumen general. Sirve para saber si el tablero está en modo normal, alerta o estrés."},
    {"Score": "AI/Semis Risk", "Qué mide": "Presión específica sobre Nasdaq, semiconductores e IA.", "Fórmula": "20% VXN + 25% VXN/VIX + 20% QQQ vs SPY + 25% SMH vs QQQ + 10% NVDA vs SMH.", "Uso": "Es el score más importante para el trade IA. Alto = tech/semis lideran la baja."},
    {"Score": "Market Stress", "Qué mide": "Estrés general del mercado, no solo tecnología.", "Fórmula": "30% VIX + 20% VVIX + 15% SKEW + 20% HYG/LQD + 15% US10Y.", "Uso": "Distingue una baja sectorial de un deterioro más sistémico."},
    {"Score": "Options Sentiment", "Qué mide": "Demanda de protección y sesgo defensivo en opciones.", "Fórmula": "Put/call total, equity, index, ETF, SPX y VIX put/call ponderados.", "Uso": "Alto = más cobertura. Extremo puede volverse contrarian si el precio deja de caer."},
    {"Score": "Capitulation", "Qué mide": "Si el miedo ya entró en zona extrema.", "Fórmula": "VIX/VXN extremos, put/call equity/ETF altos y liquidación relativa de QQQ/SMH.", "Uso": "Alto no siempre es bajista: arriba de 75 aumenta riesgo de rebote violento."},
]

INDICATOR_REFERENCE = [
    {"Indicador": "VIX", "Cálculo / fuente": "Volatilidad implícita esperada a 30 días del S&P 500.", "Bajo/normal": "<16", "Tensión": "16–20", "Riesgo alto": "20–25", "Extremo": ">25", "Fundamento": "Mide el precio de la protección en SPX. Sube cuando aumenta la demanda de cobertura."},
    {"Indicador": "VXN", "Cálculo / fuente": "Volatilidad implícita esperada a 30 días del Nasdaq 100.", "Bajo/normal": "<22", "Tensión": "22–28", "Riesgo alto": "28–35", "Extremo": ">35", "Fundamento": "Más útil que VIX para detectar estrés en tech/IA."},
    {"Indicador": "VVIX", "Cálculo / fuente": "Volatilidad implícita de opciones sobre VIX.", "Bajo/normal": "<85", "Tensión": "85–100", "Riesgo alto": "100–115", "Extremo": ">115", "Fundamento": "Mide nerviosismo sobre la propia volatilidad."},
    {"Indicador": "SKEW", "Cálculo / fuente": "Precio relativo de puts OTM de SPX / riesgo de cola.", "Bajo/normal": "<130", "Tensión": "130–145", "Riesgo alto": "145–155", "Extremo": ">155", "Fundamento": "Alto = se paga más por protección ante caídas extremas."},
    {"Indicador": "VXN/VIX", "Cálculo / fuente": "VXN dividido VIX.", "Bajo/normal": "<1,25", "Tensión": "1,25–1,40", "Riesgo alto": "1,40–1,55", "Extremo": ">1,55", "Fundamento": "Detecta si el estrés está concentrado en Nasdaq/IA vs mercado general."},
    {"Indicador": "QQQ vs SPY", "Cálculo / fuente": "Retorno QQQ 1d menos retorno SPY 1d.", "Bajo/normal": ">0%", "Tensión": "0% a -0,75%", "Riesgo alto": "-0,75% a -2%", "Extremo": "<-2%", "Fundamento": "Si QQQ cae más que SPY, tech lidera la baja."},
    {"Indicador": "SMH vs QQQ", "Cálculo / fuente": "Retorno SMH 1d menos retorno QQQ 1d.", "Bajo/normal": ">0%", "Tensión": "0% a -1%", "Riesgo alto": "-1% a -3%", "Extremo": "<-3%", "Fundamento": "Si SMH cae más que QQQ, semiconductores son el epicentro."},
    {"Indicador": "NVDA vs SMH", "Cálculo / fuente": "Retorno NVDA 1d menos retorno SMH 1d.", "Bajo/normal": ">0%", "Tensión": "0% a -1%", "Riesgo alto": "-1% a -3%", "Extremo": "<-3%", "Fundamento": "Si NVDA deja de aguantar, el líder confirma deterioro del sector."},
    {"Indicador": "Total Put/Call", "Cálculo / fuente": "Volumen total de puts dividido calls.", "Bajo/normal": "0,70–1,00", "Tensión": "1,00–1,20", "Riesgo alto": "1,20–1,40", "Extremo": ">1,40", "Fundamento": "Más puts = más cobertura/miedo. Extremos pueden ser contrarian."},
    {"Indicador": "Equity Put/Call", "Cálculo / fuente": "Puts/calls en acciones individuales.", "Bajo/normal": "0,50–0,70", "Tensión": "0,70–0,90", "Riesgo alto": "0,90–1,10", "Extremo": ">1,10", "Fundamento": "Mide miedo en acciones. Si sigue bajo, no hay capitulación minorista."},
    {"Indicador": "Index Put/Call", "Cálculo / fuente": "Puts/calls en índices.", "Bajo/normal": "0,90–1,30", "Tensión": "1,30–1,70", "Riesgo alto": "1,70–2,00", "Extremo": ">2,00", "Fundamento": "Suele capturar cobertura institucional."},
    {"Indicador": "ETF Put/Call", "Cálculo / fuente": "Puts/calls en ETFs.", "Bajo/normal": "0,80–1,20", "Tensión": "1,20–1,60", "Riesgo alto": "1,60–2,00", "Extremo": ">2,00", "Fundamento": "Detecta cobertura en SPY/QQQ/SMH/SOXX."},
    {"Indicador": "SPX Put/Call", "Cálculo / fuente": "Puts/calls en opciones SPX y SPXW.", "Bajo/normal": "1,00–1,50", "Tensión": "1,50–2,00", "Riesgo alto": "2,00–2,50", "Extremo": ">2,50", "Fundamento": "Cobertura institucional grande sobre S&P 500."},
    {"Indicador": "VIX Put/Call", "Cálculo / fuente": "Puts/calls en opciones sobre VIX.", "Bajo/normal": ">0,75", "Tensión": "0,50–0,75", "Riesgo alto": "0,20–0,50", "Extremo": "<0,20", "Fundamento": "Valor bajo suele implicar mucha demanda de calls de VIX, cobertura contra salto de volatilidad."},
    {"Indicador": "US10Y change", "Cálculo / fuente": "Cambio reciente del Treasury 10Y.", "Bajo/normal": "≤0", "Tensión": "+0 a +2,5 bps", "Riesgo alto": "+2,5 a +5 bps", "Extremo": ">+5 bps", "Fundamento": "Tasas al alza presionan valuaciones growth/IA."},
    {"Indicador": "HYG vs LQD", "Cálculo / fuente": "Retorno HYG 1d menos retorno LQD 1d.", "Bajo/normal": ">0%", "Tensión": "0% a -0,5%", "Riesgo alto": "-0,5% a -1%", "Extremo": "<-1%", "Fundamento": "Si high yield cae contra investment grade, sube estrés crediticio."},
]

def indicator_signal(name: str, value) -> tuple[str, str]:
    if value is None or pd.isna(value):
        return "Sin dato", "No se pudo calcular con la fuente actual."
    v = float(value)
    if name == "VIX":
        return ("Bajo/normal", "Volatilidad del S&P contenida.") if v < 16 else (("Tensión", "Sube el costo de cobertura, pero sin estrés alto.") if v < 20 else (("Riesgo alto", "Corrección con cobertura relevante.") if v < 25 else ("Extremo", "Estrés general alto; mirar capitulación.")))
    if name == "VXN":
        return ("Bajo/normal", "Tech/Nasdaq tranquilo.") if v < 22 else (("Tensión", "Aumenta el riesgo en tech.") if v < 28 else (("Riesgo alto", "Estrés relevante en Nasdaq/IA.") if v < 35 else ("Extremo", "Estrés muy alto en tech; cuidado con rebotes violentos.")))
    if name == "VVIX":
        return ("Bajo/normal", "Volatilidad de volatilidad contenida.") if v < 85 else (("Tensión", "Más nerviosismo sobre VIX.") if v < 100 else (("Riesgo alto", "Cobertura de volatilidad más demandada.") if v < 115 else ("Extremo", "Mercado preocupado por saltos de volatilidad.")))
    if name == "SKEW":
        return ("Bajo/normal", "Riesgo de cola poco demandado.") if v < 130 else (("Tensión", "Aumenta protección ante eventos adversos.") if v < 145 else (("Riesgo alto", "Puts OTM caros; miedo a cola izquierda.") if v < 155 else ("Extremo", "Cobertura de eventos extremos muy demandada.")))
    if name == "VXN/VIX":
        return ("Bajo/normal", "Tech no muestra estrés diferencial.") if v < 1.25 else (("Tensión", "Nasdaq con algo más de estrés que S&P.") if v < 1.40 else (("Riesgo alto", "Estrés concentrado en tech/IA.") if v < 1.55 else ("Extremo", "Foco claro de estrés en Nasdaq/IA.")))
    if name in ["QQQ_vs_SPY_1d", "SMH_vs_QQQ_1d", "NVDA_vs_SMH_1d", "HYG_vs_LQD_1d"]:
        return ("Bajo/normal", "Aguanta mejor que su referencia.") if v > 0 else (("Tensión", "Debilidad relativa leve.") if v > -1 else (("Riesgo alto", "Debilidad relativa clara.") if v > -3 else ("Extremo", "Liquidación relativa fuerte.")))
    if name in ["total_put_call", "equity_put_call"]:
        return ("Bajo/normal", "Poca demanda relativa de puts; no hay pánico.") if v < 0.70 else (("Tensión", "Cobertura moderada.") if v < 1.00 else (("Riesgo alto", "Demanda fuerte de protección.") if v < 1.25 else ("Extremo", "Cobertura extrema; puede volverse contrarian.")))
    if name in ["index_put_call", "etf_put_call", "spx_put_call"]:
        return ("Bajo/normal", "Cobertura institucional contenida.") if v < 1.20 else (("Tensión", "Cobertura institucional moderada.") if v < 1.60 else (("Riesgo alto", "Cobertura institucional elevada.") if v < 2.00 else ("Extremo", "Cobertura institucional extrema.")))
    if name == "vix_put_call":
        return ("Bajo/normal", "No se ve demanda extrema de calls de VIX.") if v > 0.75 else (("Tensión", "Aumenta cobertura contra volatilidad.") if v > 0.50 else (("Riesgo alto", "Mucha demanda relativa de calls de VIX.") if v > 0.20 else ("Extremo", "Apuesta/cobertura agresiva a salto del VIX.")))
    return "Referencia", "Ver tabla de rangos y fundamento."
