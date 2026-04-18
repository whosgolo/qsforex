from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

import requests


class TradingViewError(RuntimeError):
    """Raised when a TradingView request fails."""


@dataclass(frozen=True)
class SymbolSnapshot:
    symbol: str
    bid: float
    ask: float
    close: float
    change_pct: float
    recommendation: str
    recommendation_score: float


INTERVAL_SUFFIX = {
    "1m": "|1",
    "5m": "|5",
    "15m": "|15",
    "30m": "|30",
    "1h": "|60",
    "4h": "|240",
    "1d": "",
}


class TradingViewClient:
    """Small TradingView scanner client for forex analysis and pricing."""

    SEARCH_URL = "https://symbol-search.tradingview.com/symbol_search/"
    SCAN_URL = "https://scanner.tradingview.com/forex/scan"

    def __init__(self, timeout: int = 12) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "qsforex-analytics-bot/1.0",
                "Content-Type": "application/json",
            }
        )

    def list_pepperstone_pairs(self) -> List[str]:
        params = {
            "text": "",
            "hl": "1",
            "exchange": "PEPPERSTONE",
            "lang": "en",
            "type": "forex",
        }
        response = self.session.get(self.SEARCH_URL, params=params, timeout=self.timeout)
        if response.status_code != 200:
            raise TradingViewError(
                "Failed to load Pepperstone instruments from TradingView "
                f"(status={response.status_code})."
            )
        payload = response.json()
        symbols = sorted({item["symbol"] for item in payload if item.get("symbol")})
        return symbols

    def fetch_snapshots(self, symbols: Iterable[str], interval: str) -> Dict[str, SymbolSnapshot]:
        suffix = INTERVAL_SUFFIX[interval]
        prefixed_symbols = [f"PEPPERSTONE:{symbol}" for symbol in symbols]
        fields = [
            f"bid{suffix}",
            f"ask{suffix}",
            f"close{suffix}",
            f"change{suffix}",
            f"Recommend.All{suffix}",
            f"RSI{suffix}",
            f"MACD.macd{suffix}",
            f"MACD.signal{suffix}",
            f"ATR{suffix}",
            f"Pivot.M.Classic.S1{suffix}",
            f"Pivot.M.Classic.S2{suffix}",
            f"Pivot.M.Classic.R1{suffix}",
            f"Pivot.M.Classic.R2{suffix}",
            f"Ichimoku.BLine{suffix}",
            f"SMA20{suffix}",
            f"EMA20{suffix}",
            f"volume{suffix}",
        ]
        body = {
            "symbols": {"tickers": prefixed_symbols, "query": {"types": []}},
            "columns": fields,
        }

        response = self.session.post(self.SCAN_URL, json=body, timeout=self.timeout)
        if response.status_code != 200:
            raise TradingViewError(
                "TradingView scanner request failed "
                f"(status={response.status_code})."
            )
        payload = response.json()
        data = payload.get("data", [])
        snapshots: Dict[str, SymbolSnapshot] = {}

        for row in data:
            ticker = row["s"].split(":", 1)[-1]
            values = row["d"]
            value_map = dict(zip(fields, values))
            rec_score = float(value_map.get(f"Recommend.All{suffix}") or 0.0)
            snapshots[ticker] = SymbolSnapshot(
                symbol=ticker,
                bid=float(value_map.get(f"bid{suffix}") or 0.0),
                ask=float(value_map.get(f"ask{suffix}") or 0.0),
                close=float(value_map.get(f"close{suffix}") or 0.0),
                change_pct=float(value_map.get(f"change{suffix}") or 0.0),
                recommendation=self._score_to_recommendation(rec_score),
                recommendation_score=rec_score,
            )
        return snapshots

    @staticmethod
    def _score_to_recommendation(score: float) -> str:
        if score >= 0.5:
            return "Strong Long"
        if score >= 0.1:
            return "Long"
        if score <= -0.5:
            return "Strong Short"
        if score <= -0.1:
            return "Short"
        return "No Trade"

    def fetch_indicator_bundle(self, symbol: str, intervals: Iterable[str]) -> Dict[str, Dict[str, float]]:
        bundles: Dict[str, Dict[str, float]] = {}
        for interval in intervals:
            suffix = INTERVAL_SUFFIX[interval]
            fields = [
                f"close{suffix}",
                f"Recommend.All{suffix}",
                f"RSI{suffix}",
                f"MACD.macd{suffix}",
                f"MACD.signal{suffix}",
                f"ATR{suffix}",
                f"Pivot.M.Classic.S1{suffix}",
                f"Pivot.M.Classic.S2{suffix}",
                f"Pivot.M.Classic.R1{suffix}",
                f"Pivot.M.Classic.R2{suffix}",
                f"SMA20{suffix}",
                f"EMA20{suffix}",
            ]
            body = {
                "symbols": {"tickers": [f"PEPPERSTONE:{symbol}"], "query": {"types": []}},
                "columns": fields,
            }
            response = self.session.post(self.SCAN_URL, json=body, timeout=self.timeout)
            if response.status_code != 200:
                raise TradingViewError(
                    f"Failed to fetch indicators for {symbol} {interval} (status={response.status_code})."
                )
            data = response.json().get("data", [])
            if not data:
                continue
            values = dict(zip(fields, data[0]["d"]))
            bundles[interval] = {k: float(v or 0.0) for k, v in values.items()}
        return bundles
