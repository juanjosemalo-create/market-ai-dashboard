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
    """Score 0-100 = percentil del ULTIMO valor dentro de su propia historia (~2 anios)."""
    s = pd.to_numeric(pd.Series(series), errors="coerce").dropna()
    if len(s) < min_obs:
        return float("nan")
    s = s.iloc[-lookback:]
    last = s.iloc[-1]
    if pd.isna(last):
        return float("nan")
    pct = float((s <= last).mean() * 100.0)
    return clamp(pct if high_is_risk else 100.0 - pct)


def score_linear(value: float, green: float, red: float, invert: bool = False) -> float:
    if pd.isna(value):
        return float("nan")
    raw = (green - value) / (green - red) * 100 if invert else (value - green) / (red - green) * 100
    return clamp(raw)


def label(score: float) -> str:
    if pd.isna(score):
        return "Sin dato"
    if score < 30:
        return "Riesgo bajo"
    if score < 50:
        return "Neutral / normal"
    if score < 65:
        return "Presion moderada"
    if score < 80:
        return "Riesgo alto"
    return "Estres extremo"


def score_bucket(score: float) -> str:
    if pd.isna(score):
        return "Sin dato"
    if score < 30:
        return "0-30"
    if score < 50:
        return "30-50"
    if score < 65:
        return "50-65"
    if score < 80:
        return "65-80"
    return "80-100"


# =====================================================================
# SEMAFOROS
# =====================================================================
def traffic_light(score: float, contrarian: bool = False):
    """(emoji, palabra). Riesgo: alto=rojo. contrarian (Capitulation): alto=azul (posible piso)."""
    if pd.isna(score):
        return "\u26aa", "sin dato"
    if contrarian:
        if score < 50:
            return "\U0001F7E2", "sin sobreventa"
        if score < 75:
            return "\U0001F7E1", "sobreventa creciente"
        return "\U0001F535", "capitulacion (posible piso)"
    if score < 40:
        return "\U0001F7E2", "tranquilo"
    if score < 65:
        return "\U0001F7E1", "ojo / presion"
    return "\U0001F534", "alerta"


def term_traffic(ratio: float):
    """Semaforo de 4 estados del VIX/VIX3M (term structure)."""
    if pd.isna(ratio):
        return "\u26aa", "sin dato", "No hay dato del term structure."
    if ratio < 0.90:
        return "\U0001F7E2", "Contango pleno", "Curva normal con colchon. Las bajas suelen ser comprables."
    if ratio < 0.95:
        return "\U0001F7E1", "Aplanandose", "El colchon se esta consumiendo. Empezar a prestar atencion."
    if ratio < 1.00:
        return "\U0001F7E0", "Comprimido (alerta)", "Cerca de invertirse. Historicamente aca ya aparecian bajas. Reducir agresividad."
    return "\U0001F534", "Backwardation", "Curva invertida = estres agudo de corto plazo. No meter la mano todavia."


def indicator_light(score: float):
    if pd.isna(score):
        return "\u26aa"
    if score < 40:
        return "\U0001F7E2"
    if score < 65:
        return "\U0001F7E1"
    return "\U0001F534"


def weighted_average(items: dict) -> float:
    total_w = total = 0.0
    for _, (score, weight) in items.items():
        if score is None or pd.isna(score):
            continue
        total += float(score) * float(weight)
        total_w += float(weight)
    return total / total_w if total_w else float("nan")


def _coverage(items: dict) -> float:
    have = sum(w for _, (s, w) in items.items() if not (s is None or pd.isna(s)))
    tot = sum(w for _, (s, w) in items.items())
    return have / tot if tot else 0.0


# =====================================================================
# Composites  -  PESOS RECALIBRADOS POR EL BACKTEST (v5)
# =====================================================================
# Cambios vs v4, fundamentados en el backtest sobre 2008-2026:
#  - Term structure (VIX/VIX3M) fue la senal MAS fuerte (lift 2,7-7,0) -> sube de peso.
#  - Credito HYG/IEF brilla en caidas grandes (lift ~4 en SPY -10%) -> sube de peso.
#  - VXN/VIX dio lift <1 y edge NEGATIVO en los 4 cuadrantes -> SALE del score de riesgo.
#    Queda solo informativo (describe donde esta el nervio, no anticipa).
#  - Velocidad (term_speed / vix_speed) quedo secundaria (lift ~1,5) -> peso menor.
def compute_composites(m: dict) -> dict:
    g = lambda k: m.get(k)

    market_items = {
        "Term VIX/3M":     (g("s_term"),   0.35),
        "Credito HYG/IEF": (g("s_credit"), 0.25),
        "VIX":             (g("s_vix"),    0.20),
        "SKEW":            (g("s_skew"),   0.10),
        "VVIX":            (g("s_vvix"),   0.05),
        "Tasas 10Y":       (g("s_rates"),  0.05),
    }
    market_stress = weighted_average(market_items)

    # AI/Semis: VXN/VIX YA NO ENTRA (era ruido como predictor).
    ai_items = {
        "VXN":           (g("s_vxn"),        0.20),
        "SMH-QQQ 5d":    (g("s_smh_qqq_5"),  0.10),
        "SMH-QQQ 20d":   (g("s_smh_qqq_20"), 0.25),
        "QQQ-SPY 20d":   (g("s_qqq_spy_20"), 0.20),
        "NVDA-SMH 20d":  (g("s_nvda_smh_20"),0.15),
        "VXN cambio 1d": (g("s_vxn_chg"),    0.10),
    }
    ai_semis_stress = weighted_average(ai_items)

    options_items = {
        "Total PC":  (g("s_total_pc"),  0.15), "Equity PC": (g("s_equity_pc"), 0.15),
        "Index PC":  (g("s_index_pc"),  0.20), "ETF PC":    (g("s_etf_pc"),    0.20),
        "SPX PC":    (g("s_spx_pc"),    0.20), "VIX PC":    (g("s_vix_pc"),    0.10),
    }
    options_sentiment = weighted_average(options_items)

    cap_items = {
        "RSI SMH":       (g("s_rsi_smh"),   0.20), "RSI QQQ":       (g("s_rsi_qqq"),   0.10),
        "Drawdown SMH":  (g("s_dd_smh"),    0.20), "Breadth":       (g("s_breadth"),   0.20),
        "VIX extremo":   (g("s_vix"),       0.15), "Equity PC ext": (g("s_equity_pc"), 0.15),
    }
    capitulation = weighted_average(cap_items)

    general_items = {
        "Market":       (market_stress,     0.30), "AI/Semis":     (ai_semis_stress,   0.35),
        "Options":      (options_sentiment, 0.20), "Capitulation": (capitulation,      0.15),
    }
    general = weighted_average(general_items)

    return {
        "market_stress_score": market_stress, "ai_semis_stress_score": ai_semis_stress,
        "options_sentiment_score": options_sentiment, "capitulation_score": capitulation,
        "general_risk_score": general,
        "market_label": label(market_stress), "ai_semis_label": label(ai_semis_stress),
        "options_label": label(options_sentiment), "capitulation_label": label(capitulation),
        "general_label": label(general),
        "market_bucket": score_bucket(market_stress), "ai_semis_bucket": score_bucket(ai_semis_stress),
        "options_bucket": score_bucket(options_sentiment), "capitulation_bucket": score_bucket(capitulation),
        "general_bucket": score_bucket(general),
        "cov_market": _coverage(market_items), "cov_ai_semis": _coverage(ai_items),
        "cov_options": _coverage(options_items), "cov_capitulation": _coverage(cap_items),
    }


# =====================================================================
# Lectura tactica cualitativa (sin % inventados)
# =====================================================================
def tactical_reading(ai_semis: float, capitulation: float, term_score: float = float("nan")) -> str:
    if pd.isna(ai_semis):
        return "Sin dato suficiente para una lectura tactica."
    if not pd.isna(capitulation) and capitulation > 75:
        base = ("Mucho estres en IA/semis PERO con sobreventa/capitulacion: el riesgo se "
                "vuelve asimetrico al alza (probable rebote). Postura: no perseguir la baja.")
    elif ai_semis < 35:
        base = "Sentimiento IA/semis tranquilo. Sin deterioro relevante."
    elif ai_semis < 50:
        base = "Sentimiento IA/semis neutral. Mirar los componentes."
    elif ai_semis < 65:
        base = "Presion moderada sobre IA/semis. Vigilar, sin estres severo aun."
    elif ai_semis < 80:
        base = "Presion relevante: tech/semis liderando la baja. Gestionar exposicion."
    else:
        base = "Estres alto en IA/semis. Riesgo de continuidad, salvo capitulacion."
    if not pd.isna(term_score) and term_score > 70:
        base += " Ademas, term structure en zona alta (estres sistemico de corto plazo)."
    return base + "  [Lectura heuristica, NO una probabilidad calibrada.]"


# =====================================================================
# SEMAFORO UNICO DE ENTRADA  (solo con seniales VALIDADAS por backtest)
# =====================================================================
# Combina term structure + credito + VIX (las 3 que el backtest confirmo).
# Term pesa mas porque fue el mejor predictor. Backwardation fuerza rojo
# (lift 7 en el backtest). Capitulation actua de contrapeso: arriba de 75
# avisa que NO es momento de vender en panico.
def entry_signal(m: dict):
    ratio = m.get("VIX/VIX3M")
    s_term = m.get("s_term")
    s_credit = m.get("s_credit")
    s_vix = m.get("s_vix")
    cap = m.get("capitulation_score")

    # Riesgo combinado ponderado (term el mas fuerte)
    items = {"term": (s_term, 0.50), "credit": (s_credit, 0.30), "vix": (s_vix, 0.20)}
    riesgo = weighted_average(items)

    # Override duro: backwardation siempre es rojo
    backwardation = (not pd.isna(ratio)) and ratio > 1.00
    comprimido = (not pd.isna(ratio)) and ratio > 0.95

    if backwardation or (not pd.isna(riesgo) and riesgo > 70):
        nivel, emoji = "ALERTA", "\U0001F534"
    elif comprimido or (not pd.isna(riesgo) and riesgo > 50):
        nivel, emoji = "PRECAUCION", "\U0001F7E1"
    elif pd.isna(riesgo):
        nivel, emoji = "SIN DATO", "\u26aa"
    else:
        nivel, emoji = "OK", "\U0001F7E2"

    capitulando = (not pd.isna(cap)) and cap > 75

    if nivel == "ALERTA" and capitulando:
        msg = ("Estres sistemico alto PERO con capitulacion. NO vendas en panico: "
               "estadisticamente esta zona suele marcar pisos. Si tocas la cartera, es para "
               "acumular escalonado (DCA), no para liquidar.")
    elif nivel == "ALERTA":
        msg = ("Riesgo alto de baja de mercado. No agregar exposicion nueva agresiva; "
               "tener polvora seca y revisar coberturas. El term structure es la alarma principal.")
    elif nivel == "PRECAUCION":
        msg = ("El colchon se esta consumiendo. No es momento de agregar agresivo. "
               "DCA normal o pausado, sin acelerar compras.")
    elif nivel == "OK":
        msg = "Sin senial de alerta sistemica. Operativa normal; el DCA puede seguir su curso."
    else:
        msg = "Faltan datos para una lectura de entrada."

    return emoji, nivel, msg, (round(riesgo) if not pd.isna(riesgo) else None)


# =====================================================================
# SEMAFORO UNICO DE ENTRADA  -  sintesis de las seniales VALIDADAS
# =====================================================================
def entry_signal(m: dict) -> dict:
    """Combina las seniales que el backtest valido (term structure, credito, VIX)
    en una sola luz accionable para gestion de exposicion / DCA.

    Devuelve dict con: emoji, nivel, titulo, accion, detalle.
    NO es una recomendacion de compra/venta: es una sintesis de riesgo sistemico.
    """
    ratio = m.get("VIX/VIX3M")
    s_credit = m.get("s_credit")     # alto = estres de credito
    s_vix = m.get("s_vix")           # alto = VIX elevado para su regimen
    cap = m.get("capitulation_score")

    # Nivel del term structure (la senial mas fuerte): 0 a 3
    if pd.isna(ratio):
        term_level = None
    elif ratio < 0.90:
        term_level = 0
    elif ratio < 0.95:
        term_level = 1
    elif ratio < 1.00:
        term_level = 2
    else:
        term_level = 3

    # Confirmadores validados
    conf = 0
    conf_txt = []
    if not pd.isna(s_credit) and s_credit >= 80:
        conf += 1; conf_txt.append("credito en estres")
    if not pd.isna(s_vix) and s_vix >= 80:
        conf += 1; conf_txt.append("VIX elevado")

    if term_level is None:
        return {"emoji": "\u26aa", "nivel": "sin dato", "titulo": "Sin dato suficiente",
                "accion": "Faltan datos del term structure.", "detalle": ""}

    # Caso contrarian: estres extremo + capitulacion = posible piso (asimetrico al alza)
    if term_level >= 2 and not pd.isna(cap) and cap > 75:
        return {"emoji": "\U0001F535", "nivel": "ACUMULACION (contrarian)",
                "titulo": "Estres extremo CON capitulacion",
                "accion": "Zona de acumular con cabeza, no de vender en panico.",
                "detalle": "El miedo ya esta en extremo. Historicamente el riesgo se vuelve "
                           "asimetrico al alza (mas chance de rebote que de seguir cayendo). "
                           "Para DCA: momento de acelerar, no de frenar."}

    risk = term_level + conf
    extra = (" + " + ", ".join(conf_txt)) if conf_txt else ""

    if risk <= 0:
        return {"emoji": "\U0001F7E2", "nivel": "VERDE - normal",
                "titulo": "Condiciones normales",
                "accion": "DCA y exposicion segun plan. Sin alertas sistemicas.",
                "detalle": f"Term structure en contango{extra}. Las bajas, si aparecen, suelen ser comprables."}
    if risk <= 2:
        return {"emoji": "\U0001F7E1", "nivel": "AMARILLO - cautela",
                "titulo": "Empieza a tensarse",
                "accion": "Fraccionar entradas nuevas. No agregar riesgo agresivo.",
                "detalle": f"Nivel de term {term_level}/3{extra}. Mantener el plan pero con la guardia mas alta."}
    return {"emoji": "\U0001F534", "nivel": "ROJO - defensivo",
            "titulo": "Estres sistemico relevante",
            "accion": "Pausar entradas nuevas agresivas, esperar estabilizacion. NO es senial de vender en panico.",
            "detalle": f"Nivel de term {term_level}/3{extra}. El backtest mostro que en esta zona "
                       f"las caidas fueron varias veces mas probables que en un dia normal."}



GLOSSARY = [
    {"Palabra": "Percentil", "En criollo": "En que puesto esta el valor de hoy comparado con los ultimos 2 anios. Percentil 90 = mas alto que el 90% de los dias. Es decir 'esto esta extremo para lo que suele estar'."},
    {"Palabra": "Score (0-100)", "En criollo": "El percentil convertido en nota de riesgo. 0 = tranquilisimo, 100 = nunca tan estresado en 2 anios. 50 = un dia normal."},
    {"Palabra": "VIX", "En criollo": "El 'medidor de miedo' del S&P 500: cuanto se paga por seguro contra caidas. Sube cuando el mercado se pone nervioso."},
    {"Palabra": "VXN", "En criollo": "Lo mismo que el VIX pero para el Nasdaq (tecnologicas). Mas sensible a tu cartera de semis."},
    {"Palabra": "Term structure (VIX/VIX3M)", "En criollo": "Compara el miedo a 1 mes contra el miedo a 3 meses. Si el de corto plazo se dispara por encima del de largo, hay un susto inminente."},
    {"Palabra": "Contango", "En criollo": "Estado NORMAL: el miedo a largo plazo es mayor que el de corto. Mercado tranquilo. El ratio VIX/VIX3M esta por debajo de 1."},
    {"Palabra": "Backwardation", "En criollo": "Estado de ALARMA: se invirtio, el miedo de corto supera al de largo. Panico inmediato. El ratio pasa de 1."},
    {"Palabra": "Breadth (amplitud)", "En criollo": "Cuantas acciones aguantan vs cuantas caen. Si el indice sube pero pocas acciones lo acompanian, el mercado esta mas debil de lo que parece."},
    {"Palabra": "RSI", "En criollo": "Mide si algo esta 'sobrecomprado' (muy estirado para arriba) o 'sobrevendido' (castigado de mas, posible rebote). Va de 0 a 100."},
    {"Palabra": "Drawdown", "En criollo": "Cuanto cayo desde su punto mas alto del ultimo anio. Un drawdown de -20% = esta 20% abajo de su maximo."},
    {"Palabra": "Credito HYG/IEF", "En criollo": "Compara bonos riesgosos (HYG) contra bonos seguros (IEF). Si los riesgosos caen contra los seguros, hay estres financiero de fondo."},
    {"Palabra": "Capitulacion", "En criollo": "Cuando el miedo ya toco el extremo y casi todos vendieron. Suena feo pero suele marcar PISOS, no techos. Por eso su semaforo es azul, no rojo."},
    {"Palabra": "Lift (del backtest)", "En criollo": "Cuanto mejora una senial contra tirar la moneda. Lift 3 = cuando se prende, la caida es 3 veces mas probable que un dia cualquiera. Lift 1 = no sirve, es azar."},
    {"Palabra": "Lead (del backtest)", "En criollo": "Cuantos dias de aviso te dio la senial antes de la caida. Cuanto mas, mejor te anticipas."},
]

# Que significa cada score si sube o baja, y por que
SCORE_MEANING = [
    {"Score": "General Risk", "Si esta ALTO": "\U0001F534 El tablero entero en modo estres.",
     "Si esta BAJO": "\U0001F7E2 Mercado tranquilo, sin peligro.",
     "Por que importa": "Resumen de todo. Vistazo rapido de 'hay que preocuparse?'."},
    {"Score": "AI/Semis Risk", "Si esta ALTO": "\U0001F534 Tech y semis (tu cartera core) liderando la baja.",
     "Si esta BAJO": "\U0001F7E2 Tu sector aguanta bien.",
     "Por que importa": "El mas relevante para tu exposicion real (NVDA, TSM, AVGO...)."},
    {"Score": "Market Stress", "Si esta ALTO": "\U0001F534 Deterioro de TODO el mercado, no solo tech.",
     "Si esta BAJO": "\U0001F7E2 Sistema financiero calmo.",
     "Por que importa": "Distingue un mal dia de tech de un problema sistemico. Aca vive la mejor senial (term structure)."},
    {"Score": "Options Sentiment", "Si esta ALTO": "\U0001F534 Mucha gente comprando seguro contra caidas.",
     "Si esta BAJO": "\U0001F7E2 Poca cobertura, calma.",
     "Por que importa": "Nerviosismo en opciones. OJO: fuente (CBOE) fragil, suele venir incompleta."},
    {"Score": "Capitulation", "Si esta ALTO": "\U0001F535 Miedo en extremo; suele ser PISO, no techo. Zona de acumular, no de vender en panico.",
     "Si esta BAJO": "\U0001F7E2 Todavia no hubo capitulacion.",
     "Por que importa": "Contrapeso: te frena de vender en el peor momento. Arriba de 75, el riesgo se da vuelta para arriba."},
]

SCORE_RANGES = [
    {"Semaforo": "\U0001F7E2 0-40", "Etiqueta": "Tranquilo", "Lectura": "Indicadores en la mitad baja de su regimen de 2 anios."},
    {"Semaforo": "\U0001F7E1 40-65", "Etiqueta": "Ojo / presion", "Lectura": "Por encima de su mediana historica. Empieza a subir el riesgo."},
    {"Semaforo": "\U0001F534 65-100", "Etiqueta": "Alerta", "Lectura": "Zona alta del regimen. Presion vendedora relevante."},
    {"Semaforo": "\U0001F535 (solo Capitulation)", "Etiqueta": "Posible piso", "Lectura": "Sobreventa extrema: contrarian, suele marcar pisos."},
]

SCORE_EXPLANATIONS = [
    {"Score": "General Risk", "Formula": "30% Market + 35% AI/Semis + 20% Options + 15% Capitulation."},
    {"Score": "AI/Semis Risk", "Formula": "VXN, SMH-QQQ (5d/20d), QQQ-SPY 20d, NVDA-SMH 20d, salto de VXN. (VXN/VIX salio: el backtest mostro que no anticipa bajas.)"},
    {"Score": "Market Stress", "Formula": "35% Term structure (VIX/VIX3M) + 25% Credito HYG/IEF + 20% VIX + 10% SKEW + 5% VVIX + 5% Tasas. Recalibrado: term y credito pesan mas (mejores predictores)."},
    {"Score": "Options Sentiment", "Formula": "Put/call CBOE. Fuente fragil, puede venir parcial."},
    {"Score": "Capitulation", "Formula": "RSI (SMH/QQQ), drawdown, breadth, VIX extremo, equity put/call."},
]

INDICATOR_REFERENCE = [
    {"Indicador": "Term structure VIX/VIX3M", "Validado por backtest": "SI - la mejor (lift 2,7 a 7,0)",
     "Que significa": "Ratio >0,95 = alerta; >1,0 = backwardation (alarma)."},
    {"Indicador": "Credito HYG/IEF", "Validado por backtest": "SI - fuerte en caidas grandes (lift ~4)",
     "Que significa": "Spread bajo = bonos riesgosos cayendo = estres de fondo."},
    {"Indicador": "VIX (percentil)", "Validado por backtest": "SI - el de mayor cobertura",
     "Que significa": "Percentil alto = miedo elevado para su regimen. Aviso muchas caidas, menos preciso."},
    {"Indicador": "Salto de VIX / velocidad term", "Validado por backtest": "Secundario (lift ~1,5)",
     "Que significa": "Aporta, pero menos que el nivel. Peso reducido."},
    {"Indicador": "VXN/VIX", "Validado por backtest": "NO - lift <1, no anticipa",
     "Que significa": "Solo informativo: dice si el nervio esta en tech vs mercado. NO entra al score de riesgo."},
    {"Indicador": "SMH-QQQ, QQQ-SPY, NVDA-SMH", "Validado por backtest": "No testeado aun",
     "Que significa": "Miden liderazgo bajista del sector. Descriptivos hasta backtestearlos."},
    {"Indicador": "Breadth / RSI / Drawdown", "Validado por backtest": "No testeado (alimentan Capitulation)",
     "Que significa": "Sobreventa y amplitud. Utiles para detectar pisos, no para anticipar."},
]
