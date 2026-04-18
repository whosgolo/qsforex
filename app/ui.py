from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

try:
    from app.analysis import compute_trade_plan, pick_best_trade
    from app.tradingview_client import TradingViewClient, TradingViewError
except ModuleNotFoundError:
    # Fallback when running from inside the app/ directory
    from analysis import compute_trade_plan, pick_best_trade
    from tradingview_client import TradingViewClient, TradingViewError

INTERVALS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
DEFAULT_INTERVALS = ["5m", "15m", "1h", "4h"]


@st.cache_resource
def get_client() -> TradingViewClient:
    return TradingViewClient(timeout=15)


@st.cache_data(ttl=600)
def load_pepperstone_pairs() -> list[str]:
    return get_client().list_pepperstone_pairs()


st.set_page_config(page_title="QSForex Analyst", page_icon="📈", layout="wide")
st.title("📈 QSForex Multi-Timeframe Analyst")
st.caption("Live analysis using TradingView scanner endpoints with German time (Europe/Berlin).")
st.info("If TradingView blocks symbol lookup (HTTP 403), the app automatically falls back to a built-in major/minor forex pair list.")

with st.sidebar:
    st.header("Settings")
    selected_symbol = st.selectbox("Currency pair", options=load_pepperstone_pairs(), index=0)
    selected_intervals = st.multiselect(
        "Analysis timeframes", INTERVALS, default=DEFAULT_INTERVALS
    )
    refresh = st.button("Run analysis", type="primary")

if not selected_intervals:
    st.warning("Pick at least one timeframe.")
    st.stop()

if refresh or "plans" not in st.session_state:
    try:
        bundles = get_client().fetch_indicator_bundle(selected_symbol, selected_intervals)
        single_plan = compute_trade_plan(selected_symbol, bundles)
        snapshots = get_client().fetch_snapshots(load_pepperstone_pairs(), selected_intervals[0])

        plans = []
        for symbol in snapshots:
            pair_bundle = get_client().fetch_indicator_bundle(symbol, selected_intervals)
            plans.append(compute_trade_plan(symbol, pair_bundle))

        st.session_state["single_plan"] = single_plan
        st.session_state["plans"] = plans
        st.session_state["updated_at"] = datetime.now(ZoneInfo("Europe/Berlin"))
        st.session_state["snapshot_interval"] = selected_intervals[0]
    except TradingViewError as exc:
        st.error(str(exc))
        st.stop()

single_plan = st.session_state["single_plan"]
plans = st.session_state["plans"]
best_trade = pick_best_trade(plans)
updated_at = st.session_state["updated_at"]

left, right = st.columns([1, 1])
with left:
    st.subheader(f"Selected Pair: {single_plan.symbol}")
    st.metric("Action", single_plan.action)
    st.metric("Confidence", f"{single_plan.confidence:.1f}%")
    st.metric("Entry", f"{single_plan.entry:.5f}")

    st.markdown("#### Targets")
    st.write(f"Safe TP: `{single_plan.safe_take_profit:.5f}`")
    st.write(f"Risky TP: `{single_plan.risky_take_profit:.5f}`")
    st.write(f"Safe SL: `{single_plan.safe_stop_loss:.5f}`")
    st.write(f"Risky SL: `{single_plan.risky_stop_loss:.5f}`")
    st.caption(single_plan.reason)

with right:
    st.subheader("Best Trade Right Now")
    if best_trade is None:
        st.info("No pair currently clears the trade threshold.")
    else:
        st.success(
            f"{best_trade.symbol}: {best_trade.action} with {best_trade.confidence:.1f}% confidence"
        )
        st.write(f"Entry: `{best_trade.entry:.5f}`")
        st.write(
            f"TP (safe/risky): `{best_trade.safe_take_profit:.5f}` / `{best_trade.risky_take_profit:.5f}`"
        )
        st.write(
            f"SL (safe/risky): `{best_trade.safe_stop_loss:.5f}` / `{best_trade.risky_stop_loss:.5f}`"
        )

st.markdown("---")
st.subheader("All Pepperstone Forex Pairs")

df = pd.DataFrame([p.__dict__ for p in plans]).sort_values(
    ["confidence", "symbol"], ascending=[False, True]
)
st.dataframe(df, use_container_width=True, hide_index=True)
st.caption(
    "Time shown in Europe/Berlin: "
    f"{updated_at.strftime('%Y-%m-%d %H:%M:%S %Z')} | "
    "Values shown with 5 decimals."
)

st.warning(
    "No system can guarantee profitability or perfect 1:1 broker fills. "
    "Use this as decision support, validate prices on your broker before execution."
)
