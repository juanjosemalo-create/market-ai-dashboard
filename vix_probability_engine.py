from __future__ import annotations

import csv
import io
import json
import math
import statistics
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional

URL_VIX = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
URL_VIX3M = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX3M_History.csv"
URL_SPX_YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC"
URL_SPX_FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 VIXRiskDashboard/3.0"
)

SCENARIO_LABELS = {
    1: "Normal",
    2: "Transición",
    3: "Prealerta persistente",
    4: "Continuación fuerte",
    5: "Inversión persistente",
    6: "Pánico ascendente",
    7: "Rebote temprano",
    8: "Recuperación confirmada",
}

SCENARIO_COLORS = {
    1: "#2fbf8f",
    2: "#e7b84b",
    3: "#ed9f3b",
    4: "#ec7b37",
    5: "#e85d4a",
    6: "#db435c",
    7: "#8b6fd6",
    8: "#3b82c4",
}


@dataclass
class Row:
    day: str
    vix: float
    vix3m: float
    spx: float
    ratio: float = 0.0
    delta1: float = 0.0
    delta2: float = 0.0
    delta5: float = 0.0
    persist90: int = 0
    persist95: int = 0
    persist100: int = 0
    down_streak: int = 0
    up_streak: int = 0
    spx_ret1: float = 0.0
    spx_ret5: float = 0.0
    dd20: float = 0.0
    dd60: float = 0.0
    dd252: float = 0.0
    peak20: float = 0.0
    days_from_peak20: int = 0
    spx_break3: bool = False


def http_get(url: str, timeout: int = 35) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/csv,application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def parse_date(value: str) -> str:
    value = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Fecha no reconocida: {value}")


def parse_cboe_csv(content: bytes) -> dict[str, float]:
    text = content.decode("utf-8-sig", errors="replace")
    output: dict[str, float] = {}
    for item in csv.DictReader(io.StringIO(text)):
        try:
            day = parse_date(item.get("DATE", ""))
            close = float(item.get("CLOSE", ""))
        except (ValueError, TypeError):
            continue
        if close > 0:
            output[day] = close
    return output


def parse_fred_csv(content: bytes) -> dict[str, float]:
    text = content.decode("utf-8-sig", errors="replace")
    output: dict[str, float] = {}
    for item in csv.DictReader(io.StringIO(text)):
        day_raw = item.get("observation_date") or item.get("DATE") or ""
        value_raw = item.get("SP500") or item.get("VALUE") or ""
        try:
            day = parse_date(day_raw)
            value = float(value_raw)
        except (ValueError, TypeError):
            continue
        if value > 0:
            output[day] = value
    return output


def fetch_spx_yahoo() -> dict[str, float]:
    period1 = int(datetime(2009, 1, 1, tzinfo=timezone.utc).timestamp())
    period2 = int(time.time()) + 86_400
    params = urllib.parse.urlencode(
        {
            "period1": period1,
            "period2": period2,
            "interval": "1d",
            "events": "history",
            "includeAdjustedClose": "true",
        }
    )
    payload = json.loads(http_get(f"{URL_SPX_YAHOO}?{params}").decode("utf-8"))
    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp", [])
    closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
    output: dict[str, float] = {}
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        day = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        output[day] = float(close)
    return output


def fetch_all() -> tuple[list[Row], dict]:
    warnings: list[str] = []
    vix = parse_cboe_csv(http_get(URL_VIX))
    vix3m = parse_cboe_csv(http_get(URL_VIX3M))

    try:
        spx = fetch_spx_yahoo()
        spx_source = "Yahoo Finance · índice ^GSPC"
        if len(spx) < 1_500:
            raise ValueError("La serie SPX descargada es demasiado corta")
    except Exception as yahoo_error:
        warnings.append(f"Yahoo no respondió; se utilizó FRED: {yahoo_error}")
        spx = parse_fred_csv(http_get(URL_SPX_FRED))
        spx_source = "FRED · SP500"

    dates = sorted(set(vix) & set(vix3m) & set(spx))
    if len(dates) < 500:
        raise RuntimeError(
            f"Sólo se pudieron alinear {len(dates)} ruedas entre VIX, VIX3M y SPX."
        )

    rows = [Row(day=d, vix=vix[d], vix3m=vix3m[d], spx=spx[d]) for d in dates]
    compute_features(rows)
    meta = {
        "spx_source": spx_source,
        "warnings": warnings,
        "aligned_rows": len(rows),
        "first_date": rows[0].day,
        "last_date": rows[-1].day,
        "downloaded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    return rows, meta



def apply_live_snapshot(
    rows: list[Row],
    meta: dict,
    *,
    vix: float,
    vix3m: float,
    spx: Optional[float] = None,
    day: Optional[str] = None,
    timestamp: Optional[str] = None,
    source: str = "Yahoo Finance intradía",
) -> tuple[list[Row], dict]:
    """Superpone el snapshot intradía sobre la historia oficial.

    La calibración histórica continúa usando cierres diarios de Cboe/SPX. Sólo la
    última fila se reemplaza o agrega con el mismo dato intradía que utiliza el
    tablero principal. De este modo el ratio visible en ambas páginas queda
    sincronizado sin contaminar los eventos históricos ya cerrados.
    """
    if not rows:
        raise ValueError("No hay historia sobre la cual aplicar el snapshot intradía")
    if not (math.isfinite(vix) and vix > 0 and math.isfinite(vix3m) and vix3m > 0):
        return rows, meta

    live_day = day or datetime.now(timezone.utc).date().isoformat()
    live_spx = float(spx) if spx is not None and math.isfinite(spx) and spx > 0 else rows[-1].spx

    # Copia sólo los datos crudos para no modificar el objeto cacheado.
    updated = [Row(day=r.day, vix=r.vix, vix3m=r.vix3m, spx=r.spx) for r in rows]
    official_last_date = updated[-1].day

    if live_day < official_last_date:
        new_meta = dict(meta)
        new_meta.setdefault("warnings", [])
        new_meta["warnings"] = list(new_meta["warnings"]) + [
            f"El snapshot intradía ({live_day}) era anterior al último cierre oficial ({official_last_date}); no se aplicó."
        ]
        return rows, new_meta

    if live_day == official_last_date:
        updated[-1] = Row(day=live_day, vix=float(vix), vix3m=float(vix3m), spx=live_spx)
        mode = "reemplazo de la última rueda"
    else:
        updated.append(Row(day=live_day, vix=float(vix), vix3m=float(vix3m), spx=live_spx))
        mode = "fila intradía agregada"

    compute_features(updated)
    new_meta = dict(meta)
    new_meta["official_last_date"] = official_last_date
    new_meta["last_date"] = updated[-1].day
    new_meta["aligned_rows"] = len(updated)
    new_meta["current_source"] = source
    new_meta["live_overlay_mode"] = mode
    if timestamp:
        new_meta["live_timestamp"] = timestamp
    return updated, new_meta

def trailing_max(values: list[float], start: int, end: int) -> float:
    return max(values[max(0, start): end + 1])


def compute_features(rows: list[Row]) -> None:
    spx_values = [r.spx for r in rows]
    ratios: list[float] = []
    p90 = p95 = p100 = down = up = 0

    for i, row in enumerate(rows):
        row.ratio = row.vix / row.vix3m if row.vix3m else 0.0
        ratios.append(row.ratio)
        row.delta1 = row.ratio - ratios[i - 1] if i >= 1 else 0.0
        row.delta2 = row.ratio - ratios[i - 2] if i >= 2 else 0.0
        row.delta5 = row.ratio - ratios[i - 5] if i >= 5 else 0.0

        p90 = p90 + 1 if row.ratio >= 0.90 else 0
        p95 = p95 + 1 if row.ratio >= 0.95 else 0
        p100 = p100 + 1 if row.ratio >= 1.00 else 0
        row.persist90, row.persist95, row.persist100 = p90, p95, p100

        if i >= 1 and row.ratio < ratios[i - 1]:
            down += 1
            up = 0
        elif i >= 1 and row.ratio > ratios[i - 1]:
            up += 1
            down = 0
        else:
            down = up = 0
        row.down_streak, row.up_streak = down, up

        row.spx_ret1 = row.spx / spx_values[i - 1] - 1 if i >= 1 else 0.0
        row.spx_ret5 = row.spx / spx_values[i - 5] - 1 if i >= 5 else 0.0

        for window, attr in ((20, "dd20"), (60, "dd60"), (252, "dd252")):
            high = trailing_max(spx_values, i - window + 1, i)
            setattr(row, attr, row.spx / high - 1 if high else 0.0)

        peak_start = max(0, i - 19)
        peak_slice = ratios[peak_start: i + 1]
        row.peak20 = max(peak_slice)
        peak_rel = max(range(len(peak_slice)), key=lambda j: peak_slice[j])
        row.days_from_peak20 = len(peak_slice) - 1 - peak_rel
        row.spx_break3 = i >= 3 and row.spx > max(spx_values[i - 3:i])


def scenario_name(row: Row) -> tuple[str, str, int]:
    if row.peak20 > 1.05 and row.down_streak >= 2 and row.ratio < 1.0 and row.spx_break3:
        return (
            "Recuperación confirmada",
            "El ratio volvió debajo de 1 y el precio confirmó recuperación de corto plazo.",
            8,
        )
    if row.peak20 > 1.05 and row.down_streak >= 2:
        return (
            "Rebote temprano",
            "El ratio retrocedió dos cierres desde un pico de estrés; todavía puede haber retesteo.",
            7,
        )
    if row.ratio > 1.10 and row.delta1 > 0:
        return (
            "Pánico ascendente",
            "Backwardation extrema todavía en expansión; riesgo bilateral muy elevado.",
            6,
        )
    if row.persist100 >= 2:
        return (
            "Inversión persistente",
            "El VIX supera al VIX3M durante al menos dos ruedas.",
            5,
        )
    if 0.95 <= row.ratio < 1.0 and row.persist95 >= 3 and row.delta5 > 0.02:
        return (
            "Continuación fuerte",
            "Persistencia sobre 0,95 con pendiente positiva y sin capitulación completa.",
            4,
        )
    if row.persist95 >= 2:
        return (
            "Prealerta persistente",
            "Dos o más cierres sobre 0,95; aumenta la probabilidad de recorrido adverso.",
            3,
        )
    if row.ratio >= 0.90:
        return (
            "Transición",
            "Cobertura de corto plazo creciendo, pero sin señal condicionada fuerte.",
            2,
        )
    return (
        "Normal",
        "Estructura en contango normal; el ratio no aporta una señal direccional fuerte.",
        1,
    )


def scenario_predicate(level: int) -> Callable[[Row], bool]:
    predicates: dict[int, Callable[[Row], bool]] = {
        1: lambda r: r.ratio < 0.90,
        2: lambda r: 0.90 <= r.ratio < 0.95,
        3: lambda r: r.persist95 >= 2 and r.ratio < 1.0,
        4: lambda r: 0.95 <= r.ratio < 1.0 and r.persist95 >= 3 and r.delta5 > 0.02,
        5: lambda r: r.persist100 >= 2 and r.ratio <= 1.10,
        6: lambda r: r.ratio > 1.10 and r.delta1 > 0,
        7: lambda r: r.peak20 > 1.05 and r.down_streak >= 2,
        8: lambda r: (
            r.peak20 > 1.05
            and r.down_streak >= 2
            and r.ratio < 1
            and r.spx_break3
        ),
    }
    return predicates[level]


def sample_indices(
    rows: list[Row],
    predicate: Callable[[Row], bool],
    horizon: int = 60,
    min_gap: int = 10,
) -> list[int]:
    selected: list[int] = []
    last = -10_000
    for i, row in enumerate(rows[:-horizon]):
        if predicate(row) and i - last >= min_gap:
            selected.append(i)
            last = i
    return selected


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 0.0
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return max(0.0, centre - margin), min(1.0, centre + margin)


def event_metrics(
    rows: list[Row],
    indices: list[int],
    horizons: Iterable[int] = (3, 5, 10, 20, 60),
) -> dict[str, dict]:
    output: dict[str, dict] = {}

    for horizon in horizons:
        events: list[tuple[float, float, float]] = []
        for i in indices:
            if i + horizon >= len(rows):
                continue
            current = rows[i].spx
            future = [rows[j].spx for j in range(i + 1, i + horizon + 1)]
            events.append(
                (
                    min(future) / current - 1,
                    max(future) / current - 1,
                    rows[i + horizon].spx / current - 1,
                )
            )

        n = len(events)
        if not n:
            output[str(horizon)] = {"n": 0}
            continue

        def binary(condition: Callable[[tuple[float, float, float]], bool]) -> dict:
            successes = sum(1 for event in events if condition(event))
            low, high = wilson(successes, n)
            return {
                "p": successes / n,
                "low": low,
                "high": high,
                "successes": successes,
                "n": n,
            }

        output[str(horizon)] = {
            "n": n,
            "new_low": binary(lambda e: e[0] < 0),
            "drop_05": binary(lambda e: e[0] <= -0.005),
            "drop_1": binary(lambda e: e[0] <= -0.01),
            "drop_2": binary(lambda e: e[0] <= -0.02),
            "drop_3": binary(lambda e: e[0] <= -0.03),
            "drop_5": binary(lambda e: e[0] <= -0.05),
            "drop_10": binary(lambda e: e[0] <= -0.10),
            "close_negative": binary(lambda e: e[2] < 0),
            "close_positive": binary(lambda e: e[2] > 0),
            "median_min": statistics.median(e[0] for e in events),
            "median_max": statistics.median(e[1] for e in events),
            "median_end": statistics.median(e[2] for e in events),
        }

    return output


def similarity_indices(
    rows: list[Row], current_idx: int, max_n: int = 40, min_gap: int = 10
) -> list[int]:
    current = rows[current_idx]
    current_level = scenario_name(current)[2]
    candidates: list[tuple[float, int]] = []

    for i in range(60, current_idx - 60):
        r = rows[i]
        level = scenario_name(r)[2]
        distance = (
            4.0 * abs(r.ratio - current.ratio) / 0.05
            + 2.0 * abs(r.delta5 - current.delta5) / 0.03
            + 1.5 * abs(r.dd20 - current.dd20) / 0.03
            + 0.8 * abs(r.dd60 - current.dd60) / 0.06
            + 0.5 * abs(min(r.persist95, 5) - min(current.persist95, 5))
            + 0.6 * abs(min(r.down_streak, 4) - min(current.down_streak, 4))
            + (2.0 if level != current_level else 0.0)
            + (1.0 if (r.delta1 > 0) != (current.delta1 > 0) else 0.0)
        )
        candidates.append((distance, i))

    candidates.sort()
    selected: list[int] = []
    for _, idx in candidates:
        if all(abs(idx - existing) >= min_gap for existing in selected):
            selected.append(idx)
            if len(selected) >= max_n:
                break
    return sorted(selected)


def confidence_label(n: int) -> str:
    if n >= 50:
        return "Alta"
    if n >= 25:
        return "Media"
    if n >= 12:
        return "Baja"
    return "Insuficiente"


def pct(value: Optional[float], digits: int = 1) -> str:
    return "—" if value is None else f"{value * 100:.{digits}f}%"


def assumptions(row: Row) -> list[str]:
    items = [
        f"Ratio actual {row.ratio:.3f}; variación de cinco ruedas {row.delta5:+.3f}.",
        f"Persistencia: {row.persist95} ruedas ≥0,95 y {row.persist100} ruedas ≥1,00.",
        f"SPX: drawdown de 20 ruedas {pct(row.dd20)} y de 60 ruedas {pct(row.dd60)}.",
    ]
    if row.peak20 > 1.05:
        items.append(
            f"Pico de 20 ruedas {row.peak20:.3f}, ocurrido hace {row.days_from_peak20} ruedas."
        )
    if row.down_streak >= 2:
        items.append(
            f"El ratio acumula {row.down_streak} cierres descendentes: posible agotamiento del estrés."
        )
    if row.up_streak >= 2:
        items.append(
            f"El ratio acumula {row.up_streak} cierres ascendentes: estrés todavía acelerándose."
        )
    if row.spx_break3:
        items.append(
            "El SPX superó el máximo de las tres ruedas previas: confirmación de precio de corto plazo."
        )
    return items


def action_framework(level: int) -> dict[str, str]:
    frameworks = {
        1: {
            "bias": "Neutral",
            "text": "No tomar decisiones direccionales sólo por el ratio. Vigilar cambios de pendiente y precio.",
        },
        2: {
            "bias": "Vigilancia",
            "text": "Confirmar persistencia sobre 0,95 antes de elevar coberturas.",
        },
        3: {
            "bias": "Cautela",
            "text": "Puede convenir escalonar compras y reducir apalancamiento; buscar un precio inferior en 3–5 ruedas.",
        },
        4: {
            "bias": "Defensivo",
            "text": "Alta probabilidad de recorrido adverso inmediato. Priorizar entradas parciales y protección táctica.",
        },
        5: {
            "bias": "Riesgo bilateral",
            "text": "Parte del daño puede haber ocurrido. Medir caída adicional y rebote por separado.",
        },
        6: {
            "bias": "Pánico",
            "text": "Evitar decisiones binarias. Esperar señal de pico y dos cierres descendentes.",
        },
        7: {
            "bias": "Rebote probable",
            "text": "Mejora la probabilidad de recuperación, pero el retesteo sigue siendo frecuente.",
        },
        8: {
            "bias": "Estabilización",
            "text": "La señal mejora, aunque no elimina una nueva prueba de mínimos.",
        },
    }
    return frameworks[level]


def next_trigger(level: int) -> str:
    triggers = {
        1: "Cruce de 0,90 o aceleración de cinco ruedas superior a +0,03.",
        2: "Dos cierres consecutivos sobre 0,95.",
        3: "Tres cierres sobre 0,95, todavía debajo de 1, y Δ5d superior a +0,02.",
        4: "Dos cierres sobre 1,00 o comienzo de una secuencia descendente desde un pico.",
        5: "Ratio superior a 1,10 todavía ascendiendo, o dos cierres descendentes desde pico >1,05.",
        6: "Dos cierres descendentes desde el máximo de estrés.",
        7: "Ratio debajo de 1 y SPX por encima del máximo de las tres ruedas previas.",
        8: "Pérdida de la confirmación de precio o nueva aceleración del ratio.",
    }
    return triggers[level]


def metric_lift(metric: dict, baseline_metric: dict) -> Optional[float]:
    p = metric.get("p") if metric else None
    base = baseline_metric.get("p") if baseline_metric else None
    if p is None or base in (None, 0):
        return None
    return p / base


def build_analysis(rows: list[Row], meta: dict) -> dict:
    current_idx = len(rows) - 1
    current = rows[current_idx]
    name, description, level = scenario_name(current)

    rule_indices = sample_indices(rows, scenario_predicate(level))
    analog_indices = similarity_indices(rows, current_idx)
    baseline_indices = sample_indices(rows, lambda _r: True)

    rule_metrics = event_metrics(rows, rule_indices)
    analog_metrics = event_metrics(rows, analog_indices)
    baseline_metrics = event_metrics(rows, baseline_indices)

    library = []
    for scenario_level in range(1, 9):
        idxs = sample_indices(rows, scenario_predicate(scenario_level))
        metrics = event_metrics(rows, idxs, horizons=(5, 10, 20, 60))
        m5 = metrics.get("5", {})
        m20 = metrics.get("20", {})
        base5 = baseline_metrics.get("5", {})
        library.append(
            {
                "Nivel": scenario_level,
                "Escenario": SCENARIO_LABELS[scenario_level],
                "Casos": m5.get("n", 0),
                "Confianza": confidence_label(m5.get("n", 0)),
                "Nuevo mínimo 5d": m5.get("new_low", {}).get("p"),
                "Lift nuevo mínimo": metric_lift(
                    m5.get("new_low", {}), base5.get("new_low", {})
                ),
                "Caída ≥1% 5d": m5.get("drop_1", {}).get("p"),
                "Cierre negativo 5d": m5.get("close_negative", {}).get("p"),
                "Positivo 20d": m20.get("close_positive", {}).get("p"),
                "Mediana 20d": m20.get("median_end"),
            }
        )

    return {
        "current": current,
        "scenario": {
            "name": name,
            "description": description,
            "level": level,
            "framework": action_framework(level),
            "assumptions": assumptions(current),
            "next_trigger": next_trigger(level),
        },
        "rule": {
            "event_count": len(rule_indices),
            "confidence": confidence_label(len(rule_indices)),
            "metrics": rule_metrics,
        },
        "analogs": {
            "event_count": len(analog_indices),
            "confidence": confidence_label(len(analog_indices)),
            "metrics": analog_metrics,
            "dates": [rows[i].day for i in analog_indices],
        },
        "baseline": {
            "event_count": len(baseline_indices),
            "confidence": confidence_label(len(baseline_indices)),
            "metrics": baseline_metrics,
        },
        "library": library,
        "rows": rows,
        "meta": meta,
    }
