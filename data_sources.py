from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf

from config import PRICE_TICKERS, INDEX_TICKERS, OPTION_TICKERS, SNAPSHOT_FILE


def ensure_data_dir() -> None:
    os.makedirs(os.path.dirname(SNAPSHOT_FILE), exist_ok=True)


def _safe_float(x):
    try:
        if pd.isna(x):
            return np.nan
        return float(x)
    except Exception:
        return np.nan


def fetch_price_history(period: str = "5d", interval: str = "5m") -> pd.DataFrame:
    tickers = list(PRICE_TICKERS.keys()) + list(INDEX_TICKERS.keys())
    data = yf.download(
        tickers=tickers,
        period=period,
        interval=interval,
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
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
    closes = closes.dropna(how="all")
    return closes


def latest_market_row(closes: pd.DataFrame) -> Dict:
    row = {"timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if closes.empty:
        return row
    latest = closes.ffill().iloc[-1]

    mapping = {
        "^VIX": "VIX",
        "^VXN": "VXN",
        "^VVIX": "VVIX",
        "^SKEW": "SKEW",
        "^TNX": "US10Y_TNX",
        "^IRX": "US13W_IRX",
        "DX-Y.NYB": "DXY",
    }
    for col in closes.columns:
        name = mapping.get(col, col)
        row[name] = _safe_float(latest.get(col))

    def ret(ticker: str, bars: int) -> float:
        if ticker not in closes.columns or len(closes[ticker].dropna()) <= bars:
            return np.nan
        s = closes[ticker].dropna()
        return (s.iloc[-1] / s.iloc[-bars - 1] - 1.0) * 100

    # Approx bars: 5m bars. US cash session ~78 bars/day.
    bars_1d = min(78, max(1, len(closes) - 1))
    bars_1h = min(12, max(1, len(closes) - 1))

    for t in ["SPY", "QQQ", "SMH", "SOXX", "NVDA", "AMD", "AVGO", "MU", "MSFT", "GOOGL", "AMZN", "META", "HYG", "LQD"]:
        row[f"{t}_ret_1h"] = ret(t, bars_1h)
        row[f"{t}_ret_1d"] = ret(t, bars_1d)

    row["VXN/VIX"] = row.get("VXN", np.nan) / row.get("VIX", np.nan) if row.get("VIX") else np.nan
    row["QQQ_vs_SPY_1d"] = row.get("QQQ_ret_1d", np.nan) - row.get("SPY_ret_1d", np.nan)
    row["SMH_vs_QQQ_1d"] = row.get("SMH_ret_1d", np.nan) - row.get("QQQ_ret_1d", np.nan)
    row["NVDA_vs_SMH_1d"] = row.get("NVDA_ret_1d", np.nan) - row.get("SMH_ret_1d", np.nan)
    row["AMD_vs_SMH_1d"] = row.get("AMD_ret_1d", np.nan) - row.get("SMH_ret_1d", np.nan)
    row["AVGO_vs_SMH_1d"] = row.get("AVGO_ret_1d", np.nan) - row.get("SMH_ret_1d", np.nan)
    row["HYG_vs_LQD_1d"] = row.get("HYG_ret_1d", np.nan) - row.get("LQD_ret_1d", np.nan)

    if "^TNX" in closes.columns and len(closes["^TNX"].dropna()) > bars_1d:
        s = closes["^TNX"].dropna()
        row["US10Y_change_1d"] = _safe_float(s.iloc[-1] - s.iloc[-bars_1d - 1])
    else:
        row["US10Y_change_1d"] = np.nan

    return row


def fetch_cboe_put_call() -> Dict:
    """Try to scrape Cboe put/call daily statistics. Returns NaN if unavailable.

    Cboe can change page structure. The dashboard is robust to missing values.
    """
    result = {
        "total_put_call": np.nan,
        "equity_put_call": np.nan,
        "index_put_call": np.nan,
        "etf_put_call": np.nan,
        "spx_put_call": np.nan,
        "vix_put_call": np.nan,
    }
    url = "https://www.cboe.com/markets/us/options/market_statistics/daily/"
    try:
        tables = pd.read_html(url)
    except Exception:
        try:
            url2 = "https://www.cboe.com/markets/us/options/market-statistics/daily/"
            tables = pd.read_html(url2)
        except Exception:
            return result

    # Search across tables for put/call rows. This is intentionally flexible.
    for tbl in tables:
        if tbl.empty:
            continue
        flat = tbl.copy()
        flat.columns = [str(c).strip().lower() for c in flat.columns]
        text = flat.astype(str).apply(lambda s: " ".join(s), axis=1).str.lower()
        for idx, line in text.items():
            nums = pd.to_numeric(flat.loc[idx].astype(str).str.replace(",", "", regex=False), errors="coerce").dropna().tolist()
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


def _select_expiration(expirations: List[str], target_days: int = 30) -> Optional[str]:
    if not expirations:
        return None
    today = pd.Timestamp.utcnow().tz_localize(None).normalize()
    best = None
    best_diff = 9999
    for exp in expirations:
        d = (pd.Timestamp(exp) - today).days
        if d <= 0:
            continue
        diff = abs(d - target_days)
        if diff < best_diff:
            best_diff = diff
            best = exp
    return best


def _get_spot_price(ticker: str) -> float:
    """Robust spot price fetch for options calculations."""
    tk = yf.Ticker(ticker)
    # 1) intraday when available
    for period, interval in [("5d", "5m"), ("5d", "15m"), ("1mo", "1d")]:
        try:
            hist = tk.history(period=period, interval=interval)
            if not hist.empty and "Close" in hist:
                v = pd.to_numeric(hist["Close"], errors="coerce").dropna()
                if len(v):
                    return float(v.iloc[-1])
        except Exception:
            pass
    # 2) fast_info fallback
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
    """Fetch a compact options summary.

    Uses free Yahoo/yfinance data. This can be delayed or intermittently unavailable,
    especially from cloud hosts. The function always returns one row per ticker with
    an 'status'/'error' field so the dashboard can diagnose failures instead of
    silently showing a blank section.
    """
    rows = []
    for ticker in tickers:
        base = {
            "ticker": ticker,
            "spot": np.nan,
            "expiration": None,
            "days_to_exp": np.nan,
            "atm_iv": np.nan,
            "expected_move_$": np.nan,
            "expected_move_%": np.nan,
            "put_call_volume_ratio": np.nan,
            "put_call_oi_ratio": np.nan,
            "put_skew_95_105": np.nan,
            "status": "ERROR",
            "error": "",
        }
        try:
            tk = yf.Ticker(ticker)
            spot = _get_spot_price(ticker)
            base["spot"] = spot

            expirations = list(tk.options)
            if not expirations:
                raise ValueError("Yahoo/yfinance no devolvió vencimientos de opciones para este ticker")

            exp = _select_expiration(expirations, target_days=target_days)
            if exp is None:
                raise ValueError(f"Sin vencimiento útil cercano a {target_days} días. Vencimientos: {expirations[:5]}")
            if pd.isna(spot) or spot <= 0:
                raise ValueError("No se pudo obtener precio spot")

            chain = tk.option_chain(exp)
            calls = chain.calls.copy()
            puts = chain.puts.copy()
            if calls.empty or puts.empty:
                raise ValueError("Cadena de opciones vacía")

            days = max((pd.Timestamp(exp) - pd.Timestamp.utcnow().tz_localize(None).normalize()).days, 1)

            calls["distance"] = (pd.to_numeric(calls["strike"], errors="coerce") - spot).abs()
            puts["distance"] = (pd.to_numeric(puts["strike"], errors="coerce") - spot).abs()
            atm_call = calls.sort_values("distance").head(1)
            atm_put = puts.sort_values("distance").head(1)
            atm_iv = pd.concat([
                pd.to_numeric(atm_call["impliedVolatility"], errors="coerce"),
                pd.to_numeric(atm_put["impliedVolatility"], errors="coerce"),
            ]).dropna().mean()
            expected_move = spot * atm_iv * np.sqrt(days / 365.0) if pd.notna(atm_iv) else np.nan

            call_vol = pd.to_numeric(calls.get("volume"), errors="coerce").fillna(0).sum()
            put_vol = pd.to_numeric(puts.get("volume"), errors="coerce").fillna(0).sum()
            call_oi = pd.to_numeric(calls.get("openInterest"), errors="coerce").fillna(0).sum()
            put_oi = pd.to_numeric(puts.get("openInterest"), errors="coerce").fillna(0).sum()

            put_95 = puts.iloc[(pd.to_numeric(puts["strike"], errors="coerce") - spot * 0.95).abs().argsort()[:1]]
            call_105 = calls.iloc[(pd.to_numeric(calls["strike"], errors="coerce") - spot * 1.05).abs().argsort()[:1]]
            put_skew_approx = np.nan
            if len(put_95) and len(call_105):
                put_iv = pd.to_numeric(put_95["impliedVolatility"], errors="coerce").iloc[0]
                call_iv = pd.to_numeric(call_105["impliedVolatility"], errors="coerce").iloc[0]
                if pd.notna(put_iv) and pd.notna(call_iv):
                    put_skew_approx = float(put_iv - call_iv)

            base.update({
                "expiration": exp,
                "days_to_exp": days,
                "atm_iv": float(atm_iv) if pd.notna(atm_iv) else np.nan,
                "expected_move_$": float(expected_move) if pd.notna(expected_move) else np.nan,
                "expected_move_%": float(expected_move / spot * 100) if pd.notna(expected_move) and spot else np.nan,
                "put_call_volume_ratio": float(put_vol / call_vol) if call_vol else np.nan,
                "put_call_oi_ratio": float(put_oi / call_oi) if call_oi else np.nan,
                "put_skew_95_105": put_skew_approx,
                "status": "OK",
                "error": "",
            })
        except Exception as e:
            base["error"] = str(e)[:250]
        rows.append(base)
    return pd.DataFrame(rows)

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
