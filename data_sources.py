from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf

from config import (
    PRICE_TICKERS, INDEX_TICKERS, OPTION_TICKERS, SNAPSHOT_FILE,
    BREADTH_TICKERS, BREADTH_SEMIS, PCT_LOOKBACK, PCT_MIN_OBS,
    REL_WINDOWS, RSI_PERIOD, MA_BREADTH, DD_WINDOW,
)
from scoring import pct_score, score_linear


# =====================================================================
# Utilidades
# =====================================================================
def ensure_data_dir() -> None:
    os.makedirs(os.path.dirname(SNAPSHOT_FILE), exist_ok=True)


def _safe_float(x):
    try:
        if pd.isna(x):
            return np.nan
        return float(x)
    except Exception:
        return np.nan


def _download_closes(tickers: List[str], period: str, interval: str) -> pd.DataFrame:
    data = yf.download(
        tickers=tickers, period=period, interval=interval,
        group_by="ticker", auto_adjust=False, progress=False, threads=True,
    )
    closes = pd.DataFrame()
    if data.empty:
        return closes
    for t in tickers:
        try:
            if isinstance(data.columns, pd.MultiIndex):
                s = data[t]["Close"].dropna()
            else:
                s = data["Close"].dropna()
            closes[t] = s
        except Exception:
            continue
    return closes.dropna(how="all")


def fetch_daily_history(period: str = "2y", interval: str = "1d") -> pd.DataFrame:
    """Historia diaria de ~2 años. Es la base del scoring por percentiles."""
    tickers = list(PRICE_TICKERS.keys()) + list(INDEX_TICKERS.keys())
    return _download_closes(tickers, period=period, interval=interval)


def fetch_intraday(period: str = "5d", interval: str = "5m") -> pd.DataFrame:
    """Intradía para gráficos y para el último precio."""
    tickers = list(PRICE_TICKERS.keys()) + list(INDEX_TICKERS.keys())
    return _download_closes(tickers, period=period, interval=interval)


# =====================================================================
# Cálculos técnicos
# =====================================================================
def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce").dropna()
    delta = s.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def rel_spread_series(daily: pd.DataFrame, a: str, b: str, window: int) -> pd.Series:
    """Serie histórica del spread de retorno a 'window' días: ret_a - ret_b (en %)."""
    if a not in daily.columns or b not in daily.columns:
        return pd.Series(dtype=float)
    ra = daily[a].pct_change(window) * 100
    rb = daily[b].pct_change(window) * 100
    return (ra - rb).dropna()


def breadth_above_ma_series(daily: pd.DataFrame, tickers: List[str], ma: int = 50) -> pd.Series:
    """Serie histórica de % de nombres por encima de su MA(ma)."""
    cols = [t for t in tickers if t in daily.columns]
    if not cols:
        return pd.Series(dtype=float)
    above = pd.DataFrame(index=daily.index)
    for t in cols:
        s = daily[t]
        above[t] = (s > s.rolling(ma, min_periods=ma).mean()).astype(float)
    return (above.mean(axis=1) * 100).dropna()


def drawdown_series(series: pd.Series, window: int = 252) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce").dropna()
    roll_max = s.rolling(window, min_periods=20).max()
    return ((s / roll_max) - 1.0) * 100  # <= 0


# =====================================================================
# build_metrics: arma valores crudos + component scores (por percentil)
# =====================================================================
def build_metrics(daily: pd.DataFrame, intraday: pd.DataFrame, cboe: Dict) -> Dict:
    m: Dict = {"timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    def last(df, col):
        if col in df.columns:
            s = df[col].ffill().dropna()
            if len(s):
                return _safe_float(s.iloc[-1])
        return np.nan

    # ---- Niveles actuales (último intradía si hay, si no último diario) -----
    idx_map = {
        "^VIX": "VIX", "^VIX9D": "VIX9D", "^VIX3M": "VIX3M", "^VIX6M": "VIX6M",
        "^VXN": "VXN", "^VVIX": "VVIX", "^SKEW": "SKEW",
        "^TNX": "US10Y_TNX", "DX-Y.NYB": "DXY",
    }
    for raw, name in idx_map.items():
        v = last(intraday, raw)
        if pd.isna(v):
            v = last(daily, raw)
        m[name] = v

    # Ratios actuales
    m["VXN/VIX"] = m["VXN"] / m["VIX"] if m.get("VIX") else np.nan
    m["VIX/VIX3M"] = m["VIX"] / m["VIX3M"] if m.get("VIX3M") else np.nan
    m["VIX9D/VIX"] = m["VIX9D"] / m["VIX"] if m.get("VIX") else np.nan

    # ---- Scores de NIVEL por percentil (historia diaria) --------------------
    def pscore(col, high_is_risk=True):
        if col not in daily.columns:
            return np.nan
        return pct_score(daily[col], high_is_risk=high_is_risk,
                         lookback=PCT_LOOKBACK, min_obs=PCT_MIN_OBS)

    m["s_vix"] = pscore("^VIX", True)
    m["s_vxn"] = pscore("^VXN", True)
    m["s_vvix"] = pscore("^VVIX", True)
    m["s_skew"] = pscore("^SKEW", True)

    # VXN/VIX y term structure: percentil de la serie histórica del ratio
    if "^VXN" in daily.columns and "^VIX" in daily.columns:
        m["s_vxn_vix"] = pct_score((daily["^VXN"] / daily["^VIX"]).dropna(),
                                   True, PCT_LOOKBACK, PCT_MIN_OBS)
    else:
        m["s_vxn_vix"] = np.nan

    if "^VIX" in daily.columns and "^VIX3M" in daily.columns:
        term_series = (daily["^VIX"] / daily["^VIX3M"]).dropna()
        m["s_term"] = pct_score(term_series, True, PCT_LOOKBACK, PCT_MIN_OBS)
    else:
        m["s_term"] = np.nan

    # ---- CAMBIOS recientes (deltas) por percentil ---------------------------
    if "^VXN" in daily.columns:
        m["VXN_chg_1d"] = _safe_float(daily["^VXN"].diff(1).dropna().iloc[-1]) if len(daily["^VXN"].dropna()) > 1 else np.nan
        m["s_vxn_chg"] = pct_score(daily["^VXN"].diff(1).dropna(), True, PCT_LOOKBACK, PCT_MIN_OBS)
    else:
        m["VXN_chg_1d"], m["s_vxn_chg"] = np.nan, np.nan

    if "^VIX" in daily.columns:
        m["VIX_chg_1d"] = _safe_float(daily["^VIX"].diff(1).dropna().iloc[-1]) if len(daily["^VIX"].dropna()) > 1 else np.nan
    if "^TNX" in daily.columns:
        tnx_chg = daily["^TNX"].diff(1).dropna()
        m["US10Y_chg_1d"] = _safe_float(tnx_chg.iloc[-1]) if len(tnx_chg) else np.nan
        m["s_rates"] = pct_score(tnx_chg, True, PCT_LOOKBACK, PCT_MIN_OBS)
    else:
        m["US10Y_chg_1d"], m["s_rates"] = np.nan, np.nan

    # ---- Relativos multi-ventana (momentum relativo) ------------------------
    rel_defs = {
        ("SMH", "QQQ"): "smh_qqq",
        ("QQQ", "SPY"): "qqq_spy",
        ("NVDA", "SMH"): "nvda_smh",
    }
    for (a, b), tag in rel_defs.items():
        for w in REL_WINDOWS:
            ser = rel_spread_series(daily, a, b, w)
            key_val = f"{tag}_{w}d"
            m[key_val] = _safe_float(ser.iloc[-1]) if len(ser) else np.nan
            # spread bajo (muy negativo) = riesgo -> high_is_risk=False
            m[f"s_{tag}_{w}"] = pct_score(ser, high_is_risk=False,
                                          lookback=PCT_LOOKBACK, min_obs=PCT_MIN_OBS)

    # ---- Crédito: HYG vs IEF (aísla spread) y HYG vs LQD (referencia) --------
    cred = rel_spread_series(daily, "HYG", "IEF", 20)
    m["HYG_IEF_20d"] = _safe_float(cred.iloc[-1]) if len(cred) else np.nan
    m["s_credit"] = pct_score(cred, high_is_risk=False, lookback=PCT_LOOKBACK, min_obs=PCT_MIN_OBS)
    cred2 = rel_spread_series(daily, "HYG", "LQD", 20)
    m["HYG_LQD_20d"] = _safe_float(cred2.iloc[-1]) if len(cred2) else np.nan

    # ---- Breadth ------------------------------------------------------------
    bs = breadth_above_ma_series(daily, BREADTH_TICKERS, MA_BREADTH)
    m["breadth_pct"] = _safe_float(bs.iloc[-1]) if len(bs) else np.nan
    m["s_breadth"] = pct_score(bs, high_is_risk=False, lookback=PCT_LOOKBACK, min_obs=PCT_MIN_OBS)
    bss = breadth_above_ma_series(daily, BREADTH_SEMIS, MA_BREADTH)
    m["breadth_semis_pct"] = _safe_float(bss.iloc[-1]) if len(bss) else np.nan

    # ---- Momentum / sobreventa ---------------------------------------------
    for t, tag in [("SMH", "smh"), ("QQQ", "qqq")]:
        if t in daily.columns:
            r = rsi(daily[t], RSI_PERIOD)
            m[f"RSI_{tag}"] = _safe_float(r.dropna().iloc[-1]) if len(r.dropna()) else np.nan
            # RSI bajo = sobreventa = capitulación -> high_is_risk=False
            m[f"s_rsi_{tag}"] = pct_score(r.dropna(), high_is_risk=False,
                                          lookback=PCT_LOOKBACK, min_obs=PCT_MIN_OBS)
        else:
            m[f"RSI_{tag}"], m[f"s_rsi_{tag}"] = np.nan, np.nan

    if "SMH" in daily.columns:
        dd = drawdown_series(daily["SMH"], DD_WINDOW).dropna()
        m["DD_smh_52w"] = _safe_float(dd.iloc[-1]) if len(dd) else np.nan
        # drawdown más negativo = más estrés -> high_is_risk=False
        m["s_dd_smh"] = pct_score(dd, high_is_risk=False, lookback=PCT_LOOKBACK, min_obs=PCT_MIN_OBS)
    else:
        m["DD_smh_52w"], m["s_dd_smh"] = np.nan, np.nan

    # ---- Retornos 1d simples (para mostrar) ---------------------------------
    for t in ["SPY", "QQQ", "SMH", "NVDA", "AMD", "AVGO"]:
        if t in daily.columns:
            r1 = daily[t].pct_change(1).dropna()
            m[f"{t}_ret_1d"] = _safe_float(r1.iloc[-1] * 100) if len(r1) else np.nan

    # ---- Put/Call CBOE (umbrales fijos; fuente frágil) ----------------------
    for k in ["total_put_call", "equity_put_call", "index_put_call",
              "etf_put_call", "spx_put_call", "vix_put_call"]:
        m[k] = cboe.get(k, np.nan)
    m["s_total_pc"] = score_linear(m["total_put_call"], 0.70, 1.25)
    m["s_equity_pc"] = score_linear(m["equity_put_call"], 0.50, 0.95)
    m["s_index_pc"] = score_linear(m["index_put_call"], 0.90, 1.80)
    m["s_etf_pc"] = score_linear(m["etf_put_call"], 0.80, 1.70)
    m["s_spx_pc"] = score_linear(m["spx_put_call"], 1.00, 2.20)
    m["s_vix_pc"] = score_linear(m["vix_put_call"], 0.75, 0.20, invert=True)

    return m


# =====================================================================
# Put/Call CBOE (igual que antes: scraping frágil, robusto a faltantes)
# =====================================================================
def fetch_cboe_put_call() -> Dict:
    result = {k: np.nan for k in [
        "total_put_call", "equity_put_call", "index_put_call",
        "etf_put_call", "spx_put_call", "vix_put_call"]}
    for url in ("https://www.cboe.com/markets/us/options/market_statistics/daily/",
                "https://www.cboe.com/markets/us/options/market-statistics/daily/"):
        try:
            tables = pd.read_html(url)
            break
        except Exception:
            tables = None
    if not tables:
        return result
    for tbl in tables:
        if tbl.empty:
            continue
        flat = tbl.copy()
        flat.columns = [str(c).strip().lower() for c in flat.columns]
        text = flat.astype(str).apply(lambda s: " ".join(s), axis=1).str.lower()
        for idx, line in text.items():
            nums = pd.to_numeric(flat.loc[idx].astype(str).str.replace(",", "", regex=False),
                                 errors="coerce").dropna().tolist()
            if not nums:
                continue
            value = nums[-1]
            if "total" in line and "put" in line and "call" in line:
                result["total_put_call"] = value
            elif "equity" in line and "put" in line and "call" in line:
                result["equity_put_call"] = value
            elif "index" in line and "put" in line and "call" in line:
                result["index_put_call"] = value
            elif "etf" in line and "put" in line and "call" in line:
                result["etf_put_call"] = value
            elif "spx" in line and "put" in line and "call" in line:
                result["spx_put_call"] = value
            elif "vix" in line and "put" in line and "call" in line:
                result["vix_put_call"] = value
    return result


# =====================================================================
# Opciones (Yahoo / yfinance) - igual que v3, con diagnóstico por ticker
# =====================================================================
def _select_expiration(expirations: List[str], target_days: int = 30) -> Optional[str]:
    if not expirations:
        return None
    today = pd.Timestamp.utcnow().tz_localize(None).normalize()
    best, best_diff = None, 9999
    for exp in expirations:
        d = (pd.Timestamp(exp) - today).days
        if d <= 0:
            continue
        diff = abs(d - target_days)
        if diff < best_diff:
            best_diff, best = diff, exp
    return best


def _get_spot_price(ticker: str) -> float:
    tk = yf.Ticker(ticker)
    for period, interval in [("5d", "5m"), ("5d", "15m"), ("1mo", "1d")]:
        try:
            hist = tk.history(period=period, interval=interval)
            if not hist.empty and "Close" in hist:
                v = pd.to_numeric(hist["Close"], errors="coerce").dropna()
                if len(v):
                    return float(v.iloc[-1])
        except Exception:
            pass
    try:
        fi = tk.fast_info
        for key in ["last_price", "regular_market_price", "previous_close"]:
            try:
                val = fi.get(key)
            except Exception:
                val = getattr(fi, key, None)
            if val is not None and not pd.isna(val):
                return float(val)
    except Exception:
        pass
    return np.nan


def fetch_options_summary(tickers: List[str] = OPTION_TICKERS, target_days: int = 30) -> pd.DataFrame:
    rows = []
    for ticker in tickers:
        base = {
            "ticker": ticker, "spot": np.nan, "expiration": None, "days_to_exp": np.nan,
            "atm_iv": np.nan, "expected_move_$": np.nan, "expected_move_%": np.nan,
            "put_call_volume_ratio": np.nan, "put_call_oi_ratio": np.nan,
            "put_skew_95_105": np.nan, "status": "ERROR", "error": "",
        }
        try:
            tk = yf.Ticker(ticker)
            spot = _get_spot_price(ticker)
            base["spot"] = spot
            expirations = list(tk.options)
            if not expirations:
                raise ValueError("Yahoo no devolvió vencimientos de opciones")
            exp = _select_expiration(expirations, target_days)
            if exp is None:
                raise ValueError(f"Sin vencimiento útil cercano a {target_days} días")
            if pd.isna(spot) or spot <= 0:
                raise ValueError("No se pudo obtener precio spot")
            chain = tk.option_chain(exp)
            calls, puts = chain.calls.copy(), chain.puts.copy()
            if calls.empty or puts.empty:
                raise ValueError("Cadena de opciones vacía")
            days = max((pd.Timestamp(exp) - pd.Timestamp.utcnow().tz_localize(None).normalize()).days, 1)
            calls["distance"] = (pd.to_numeric(calls["strike"], errors="coerce") - spot).abs()
            puts["distance"] = (pd.to_numeric(puts["strike"], errors="coerce") - spot).abs()
            atm_iv = pd.concat([
                pd.to_numeric(calls.sort_values("distance").head(1)["impliedVolatility"], errors="coerce"),
                pd.to_numeric(puts.sort_values("distance").head(1)["impliedVolatility"], errors="coerce"),
            ]).dropna().mean()
            expected_move = spot * atm_iv * np.sqrt(days / 365.0) if pd.notna(atm_iv) else np.nan
            call_vol = pd.to_numeric(calls.get("volume"), errors="coerce").fillna(0).sum()
            put_vol = pd.to_numeric(puts.get("volume"), errors="coerce").fillna(0).sum()
            call_oi = pd.to_numeric(calls.get("openInterest"), errors="coerce").fillna(0).sum()
            put_oi = pd.to_numeric(puts.get("openInterest"), errors="coerce").fillna(0).sum()
            put_95 = puts.iloc[(pd.to_numeric(puts["strike"], errors="coerce") - spot * 0.95).abs().argsort()[:1]]
            call_105 = calls.iloc[(pd.to_numeric(calls["strike"], errors="coerce") - spot * 1.05).abs().argsort()[:1]]
            put_skew = np.nan
            if len(put_95) and len(call_105):
                piv = pd.to_numeric(put_95["impliedVolatility"], errors="coerce").iloc[0]
                civ = pd.to_numeric(call_105["impliedVolatility"], errors="coerce").iloc[0]
                if pd.notna(piv) and pd.notna(civ):
                    put_skew = float(piv - civ)
            base.update({
                "expiration": exp, "days_to_exp": days,
                "atm_iv": float(atm_iv) if pd.notna(atm_iv) else np.nan,
                "expected_move_$": float(expected_move) if pd.notna(expected_move) else np.nan,
                "expected_move_%": float(expected_move / spot * 100) if pd.notna(expected_move) and spot else np.nan,
                "put_call_volume_ratio": float(put_vol / call_vol) if call_vol else np.nan,
                "put_call_oi_ratio": float(put_oi / call_oi) if call_oi else np.nan,
                "put_skew_95_105": put_skew, "status": "OK", "error": "",
            })
        except Exception as e:
            base["error"] = str(e)[:250]
        rows.append(base)
    return pd.DataFrame(rows)


# =====================================================================
# Snapshots
# =====================================================================
def save_snapshot(row: Dict) -> None:
    ensure_data_dir()
    df = pd.DataFrame([row])
    if os.path.exists(SNAPSHOT_FILE):
        df.to_csv(SNAPSHOT_FILE, mode="a", header=False, index=False)
    else:
        df.to_csv(SNAPSHOT_FILE, index=False)


def load_snapshots() -> pd.DataFrame:
    ensure_data_dir()
    if not os.path.exists(SNAPSHOT_FILE):
        return pd.DataFrame()
    return pd.read_csv(SNAPSHOT_FILE)
