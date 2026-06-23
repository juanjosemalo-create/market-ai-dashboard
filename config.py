# =====================================================================
# config.py  -  Market AI Dashboard v4
# =====================================================================
# Tickers de acciones / ETF que se usan para retornos, breadth y momentum.
PRICE_TICKERS = {
    "SPY": "S&P 500 ETF",
    "QQQ": "Nasdaq 100 ETF",
    "SMH": "Semiconductors ETF",
    "SOXX": "Semiconductors ETF 2",
    "NVDA": "Nvidia",
    "AMD": "AMD",
    "AVGO": "Broadcom",
    "MU": "Micron",
    "MRVL": "Marvell",
    "TSM": "TSMC ADR",
    "ARM": "Arm",
    "ASML": "ASML ADR",
    "MSFT": "Microsoft",
    "GOOGL": "Alphabet",
    "AMZN": "Amazon",
    "META": "Meta",
    "ORCL": "Oracle",
    "HYG": "High Yield ETF",
    "LQD": "IG Credit ETF",
    "IEF": "US Treasury 7-10y ETF",   # NUEVO: para aislar el spread de crédito (HYG vs IEF)
}

# Universo para el cálculo de BREADTH (% de nombres sobre su MA50).
# Solo acciones/ETF de equity; se excluyen los de crédito.
BREADTH_TICKERS = [
    "SPY", "QQQ", "SMH", "SOXX", "NVDA", "AMD", "AVGO", "MU", "MRVL",
    "TSM", "ARM", "ASML", "MSFT", "GOOGL", "AMZN", "META", "ORCL",
]

# Subconjunto IA/semis para breadth sectorial.
BREADTH_SEMIS = ["SMH", "SOXX", "NVDA", "AMD", "AVGO", "MU", "MRVL", "TSM", "ARM", "ASML"]

# Índices de volatilidad y macro.  NUEVO: term structure completa.
INDEX_TICKERS = {
    "^VIX": "VIX (30d)",
    "^VIX9D": "VIX9D (9d)",     # NUEVO
    "^VIX3M": "VIX3M (3m)",     # NUEVO
    "^VIX6M": "VIX6M (6m)",     # NUEVO
    "^VXN": "VXN (Nasdaq)",
    "^VVIX": "VVIX",
    "^SKEW": "SKEW",
    "^TNX": "US 10Y Yield x10",
    "^IRX": "US 13W Bill x10",
    "DX-Y.NYB": "DXY",
}

# Tickers para el resumen de cadenas de opciones (Yahoo / yfinance).
OPTION_TICKERS = ["QQQ", "SMH", "NVDA", "AMD", "AVGO"]

# --- Parámetros de cálculo --------------------------------------------------
# Ventana (en ruedas) para el percentil histórico de cada indicador.
PCT_LOOKBACK = 504          # ~2 años hábiles
PCT_MIN_OBS = 90            # mínimo de datos para calcular percentil con sentido

# Ventanas para retornos relativos (momentum relativo multi-horizonte).
REL_WINDOWS = [5, 20]       # 1 semana y 1 mes bursátil

RSI_PERIOD = 14
MA_BREADTH = 50             # media móvil para breadth
DD_WINDOW = 252             # ventana para drawdown vs máximo de 52 semanas

SNAPSHOT_FILE = "data/snapshots.csv"
DEFAULT_REFRESH_MINUTES = 5
