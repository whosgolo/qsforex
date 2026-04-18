from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

try:
    from app.tradingview_client import INTERVAL_SUFFIX
except ModuleNotFoundError:
    # Fallback when running from inside the app/ directory
    from tradingview_client import INTERVAL_SUFFIX


@dataclass(frozen=True)
class TradePlan:
    symbol: str
    action: str
    confidence: float
    entry: float
    safe_take_profit: float
    risky_take_profit: float
    safe_stop_loss: float
    risky_stop_loss: float
    reason: str


def _interval_weight(interval: str) -> float:
    return {
        "1m": 0.6,
        "5m": 0.9,
        "15m": 1.1,
        "30m": 1.2,
        "1h": 1.4,
        "4h": 1.7,
        "1d": 2.0,
    }.get(interval, 1.0)


def _clip(v: float, min_v: float, max_v: float) -> float:
    return max(min_v, min(v, max_v))


def compute_trade_plan(symbol: str, bundles: Dict[str, Dict[str, float]]) -> TradePlan:
    if not bundles:
        return TradePlan(symbol, "No Trade", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "No data")

    weighted_score = 0.0
    weight_sum = 0.0
    aligned_bull = 0
    aligned_bear = 0

    latest_interval = max(bundles.keys(), key=lambda i: _interval_weight(i))
    latest = bundles[latest_interval]
    latest_suffix = INTERVAL_SUFFIX[latest_interval]
    entry = latest[f"close{latest_suffix}"]
    atr = max(1e-6, latest[f"ATR{latest_suffix}"])
    s1 = latest[f"Pivot.M.Classic.S1{latest_suffix}"]
    s2 = latest[f"Pivot.M.Classic.S2{latest_suffix}"]
    r1 = latest[f"Pivot.M.Classic.R1{latest_suffix}"]
    r2 = latest[f"Pivot.M.Classic.R2{latest_suffix}"]

    notes: List[str] = []

    for interval, values in bundles.items():
        suffix = INTERVAL_SUFFIX[interval]
        w = _interval_weight(interval)
        rec = values[f"Recommend.All{suffix}"]
        rsi = values[f"RSI{suffix}"]
        macd = values[f"MACD.macd{suffix}"]
        macd_signal = values[f"MACD.signal{suffix}"]
        ema20 = values[f"EMA20{suffix}"]
        sma20 = values[f"SMA20{suffix}"]
        close = values[f"close{suffix}"]

        momentum = 0.0
        if macd > macd_signal:
            momentum += 0.15
            aligned_bull += 1
        elif macd < macd_signal:
            momentum -= 0.15
            aligned_bear += 1

        trend = 0.0
        if close > ema20 > sma20:
            trend += 0.2
            aligned_bull += 1
        elif close < ema20 < sma20:
            trend -= 0.2
            aligned_bear += 1

        mean_revert_penalty = 0.0
        if rsi > 74:
            mean_revert_penalty -= 0.12
        elif rsi < 26:
            mean_revert_penalty += 0.12

        interval_score = rec + momentum + trend + mean_revert_penalty
        weighted_score += w * interval_score
        weight_sum += w

    score = weighted_score / max(weight_sum, 1e-9)

    if score >= 0.25:
        action = "Long"
        safe_tp = max(r1, entry + 1.8 * atr)
        risky_tp = max(r2, entry + 3.0 * atr)
        safe_sl = min(s1, entry - 1.2 * atr)
        risky_sl = min(s2, entry - 2.2 * atr)
    elif score <= -0.25:
        action = "Short"
        safe_tp = min(s1, entry - 1.8 * atr)
        risky_tp = min(s2, entry - 3.0 * atr)
        safe_sl = max(r1, entry + 1.2 * atr)
        risky_sl = max(r2, entry + 2.2 * atr)
    else:
        action = "No Trade"
        safe_tp = risky_tp = safe_sl = risky_sl = entry

    alignment_total = max(1, aligned_bull + aligned_bear)
    alignment_bias = abs(aligned_bull - aligned_bear) / alignment_total
    confidence = _clip((abs(score) * 65.0) + alignment_bias * 35.0, 0, 99)

    notes.append(f"Multi-timeframe score {score:.2f}")
    notes.append(f"Bull/Bear alignment {aligned_bull}/{aligned_bear}")
    notes.append(f"ATR volatility {atr:.5f}")

    return TradePlan(
        symbol=symbol,
        action=action,
        confidence=round(confidence, 1),
        entry=round(entry, 5),
        safe_take_profit=round(safe_tp, 5),
        risky_take_profit=round(risky_tp, 5),
        safe_stop_loss=round(safe_sl, 5),
        risky_stop_loss=round(risky_sl, 5),
        reason=" | ".join(notes),
    )


def pick_best_trade(plans: Iterable[TradePlan]) -> TradePlan | None:
    tradable = [p for p in plans if p.action != "No Trade"]
    if not tradable:
        return None
    return sorted(tradable, key=lambda p: p.confidence, reverse=True)[0]
