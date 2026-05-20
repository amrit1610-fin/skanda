import asyncio
import json
import os
import hashlib
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

import ccxt
import numpy as np
import pandas as pd
import websockets
from websockets.exceptions import ConnectionClosed

from .base_agent import ReActAgent
from .asset_manager import UNIVERSE

REAL_SYMBOL = "BTCUSDT"
VALID_TIMEFRAMES = {"1m", "5m", "15m", "1h", "4h", "1d"}

# Timeframe → default REST candle count (primary & multi-coin panels)
TF_CCXT = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}
TF_CANDLES = {"1m": 250, "5m": 250, "15m": 250, "1h": 250, "4h": 250, "1d": 250}

# Multi-Timeframe Regime Radar — timeframes fetched every live cycle
MTF_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]
MTF_CANDLES    = 250  # 250 bars per TF is enough for EMA20/50/SMA200

# Binance combined stream kline suffix
TF_BINANCE_WS = {"5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h"}

BINANCE_WS_BASE = "wss://stream.binance.com:9443/ws"

_DEFAULT_WARMUP_LIMIT = 500
_CANDLE_DEQUE_MAX = 5000
_RECONNECT_BACKOFF_MAX = 60.0

def _to_ccxt_symbol(symbol: str) -> str:
    s = (symbol or REAL_SYMBOL).strip().upper().replace("/", "").replace("-", "")
    if not s.endswith("USDT"):
        s = f"{s}USDT"
    base = s[:-4]
    return f"{base}/USDT"


def _to_binance_stream_symbol(symbol: str) -> str:
    s = (symbol or REAL_SYMBOL).strip().upper().replace("/", "").replace("-", "")
    if not s.endswith("USDT"):
        s = f"{s}USDT"
    return s.lower()


def _rows_to_dataframe(rows: list[dict], partial: Optional[dict]) -> pd.DataFrame:
    merged = list(rows)
    if partial is not None:
        merged = merged + [partial]
    if not merged:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = pd.DataFrame(merged)
    df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
    df = df.reset_index(drop=True)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce").astype("int64")
    return df


class DataEngineer(ReActAgent):
    """
    Hybrid market data: CCXT REST warm-up + Binance public WebSocket kline stream.
    Upgraded for WOTA Architecture (Live & Backtest Mode).
    """

    def __init__(self):
        skill_path = os.path.join(os.path.dirname(__file__), "..", ".skills", "data_engineer", "system_prompt.md")
        super().__init__("DataEngineer", skill_path)
        
        # Live Stream State
        self._lock = threading.RLock()
        self._candles: deque[dict[str, Any]] = deque(maxlen=_CANDLE_DEQUE_MAX)
        self._partial: Optional[dict[str, Any]] = None
        self._exchange: Optional[ccxt.binance] = None
        self._warmup_limit = _DEFAULT_WARMUP_LIMIT
        self._live_symbol: Optional[str] = None
        self._live_timeframe: Optional[str] = None
        self._stream_stop = threading.Event()
        
        # WOTA Backtest Time Machine State
        self.historical_dfs = {} # dict of symbol -> pd.DataFrame
        self.current_step = 0
        self.lookback_window = 250 # Ensure 200 EMA can calculate

    def _read_policy(self) -> dict:
        try:
            policy_path = os.path.join(os.path.dirname(__file__), "..", "config", "active_policy.json")
            with open(policy_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _get_active_symbol(self) -> str:
        return self._read_policy().get("symbol", REAL_SYMBOL)

    def _get_timeframe(self) -> str:
        tf = self._read_policy().get("timeframe", "5m")
        return tf if tf in VALID_TIMEFRAMES else "5m"

    def _get_exchange(self) -> ccxt.binance:
        if self._exchange is None:
            self._exchange = ccxt.binance({"enableRateLimit": True})
        return self._exchange

    # --- Live CCXT & WebSocket Logic ---

    def get_historical_ohlcv(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        tf = timeframe if timeframe in VALID_TIMEFRAMES else "5m"
        ccxt_tf = TF_CCXT.get(tf, "5m")
        pair = _to_ccxt_symbol(symbol)
        lim = max(10, min(int(limit), 1500))

        try:
            ex = self._get_exchange()
            tf_ms_map = {
                "1m": 60_000, "3m": 180_000, "5m": 300_000,
                "15m": 900_000, "30m": 1_800_000, "1h": 3_600_000,
                "2h": 7_200_000, "4h": 14_400_000, "1d": 86_400_000,
            }
            candle_ms = tf_ms_map.get(ccxt_tf, 300_000)
            since = ex.milliseconds() - (lim * candle_ms)
            raw = ex.fetch_ohlcv(pair, timeframe=ccxt_tf, limit=lim, since=since)
        except Exception as e:
            self.think(f"CCXT fetch_ohlcv failed for {pair} {ccxt_tf}: {e}. Using mock fallback.")
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        if not raw:
            self.think(f"Empty OHLCV from exchange for {pair}; using mock fallback.")
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        rows = []
        for t, o, h, l, c, v in raw:
            rows.append({
                "timestamp": int(t),
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "volume": float(v),
            })
        return pd.DataFrame(rows)

    def warm_up_historical(
        self,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> None:
        sym = symbol or self._get_active_symbol()
        tf = timeframe or self._get_timeframe()
        lim = int(limit) if limit is not None else self._warmup_limit
        df = self.get_historical_ohlcv(sym, tf, lim)
        with self._lock:
            self._candles.clear()
            self._partial = None
            for _, row in df.iterrows():
                self._candles.append({
                    "timestamp": int(row["timestamp"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                })
        self.think(f"Warm-up loaded {len(df)} candles for {sym} @ {tf}.")

    def get_latest_market_state(self) -> pd.DataFrame:
        with self._lock:
            rows = list(self._candles)
            partial = dict(self._partial) if self._partial is not None else None
        return _rows_to_dataframe(rows, partial)

    def _apply_kline_message(self, data: dict) -> None:
        if data.get("e") != "kline":
            return
        k = data.get("k") or {}
        try:
            ts = int(k["t"])
            is_closed = bool(k.get("x", False))
            row = {
                "timestamp": ts,
                "open": float(k["o"]),
                "high": float(k["h"]),
                "low": float(k["l"]),
                "close": float(k["c"]),
                "volume": float(k["v"]),
            }
        except (KeyError, TypeError, ValueError):
            return

        with self._lock:
            if is_closed:
                if self._candles and self._candles[-1]["timestamp"] == ts:
                    self._candles[-1] = row
                else:
                    self._candles.append(row)
                self._partial = None
            else:
                self._partial = row

    def _binance_kline_url(self, symbol: str, timeframe: str) -> str:
        tf = timeframe if timeframe in VALID_TIMEFRAMES else "5m"
        interval = TF_BINANCE_WS.get(tf, "5m")
        stream_sym = _to_binance_stream_symbol(symbol)
        return f"{BINANCE_WS_BASE}/{stream_sym}@kline_{interval}"

    async def start_live_stream(self, symbol: str) -> None:
        self._live_symbol = symbol
        self._live_timeframe = self._get_timeframe()
        backoff = 1.0

        while not self._stream_stop.is_set():
            uri = self._binance_kline_url(symbol, self._live_timeframe)
            self.think(f"Connecting Binance WebSocket: {uri}")
            try:
                async with websockets.connect(
                    uri,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=10,
                ) as ws:
                    backoff = 1.0
                    while not self._stream_stop.is_set():
                        raw = await ws.recv()
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        self._apply_kline_message(msg)
            except asyncio.CancelledError:
                raise
            except (ConnectionClosed, OSError) as e:
                if self._stream_stop.is_set():
                    break
                self.think(f"WebSocket dropped ({type(e).__name__}: {e}). Reconnect in {backoff:.1f}s.")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, _RECONNECT_BACKOFF_MAX)
            except Exception as e:
                if self._stream_stop.is_set():
                    break
                self.think(f"WebSocket error: {e}. Reconnect in {backoff:.1f}s.")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, _RECONNECT_BACKOFF_MAX)

    def stop_live_stream(self) -> None:
        self._stream_stop.set()

    def _fetch_one_symbol_historical(self, symbol: str, n_candles: int, timeframe: str) -> tuple[str, pd.DataFrame]:
        df = self.get_historical_ohlcv(symbol, timeframe, n_candles)
        return symbol, df

    def _fetch_mtf_data(self, symbol: str) -> dict:
        """
        Fetches 250 candles for each MTF_TIMEFRAME in parallel.
        Gracefully returns an empty DataFrame for any TF that fails.
        """
        results: dict[str, pd.DataFrame] = {}

        def _fetch_one_tf(tf: str):
            try:
                return tf, self.get_historical_ohlcv(symbol, tf, MTF_CANDLES)
            except Exception as exc:
                self.think(f"MTF fetch failed for {symbol} @ {tf}: {exc}")
                return tf, pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        with ThreadPoolExecutor(max_workers=len(MTF_TIMEFRAMES)) as pool:
            futures = {pool.submit(_fetch_one_tf, tf): tf for tf in MTF_TIMEFRAMES}
            for fut in as_completed(futures):
                tf, df = fut.result()
                results[tf] = df

        return results

    # --- Dual Mode Execution ---

    def fetch_market_data(self):
        """
        The Universal Faucet.
        Fetches the latest live market data from CCXT and WebSockets.
        """
        symbol = self._get_active_symbol()
        timeframe = self._get_timeframe()

        n_candles = TF_CANDLES.get(timeframe, 288)
        primary_df = self.get_latest_market_state()
        
        if primary_df.empty:
            self.think("Hybrid buffer empty; refreshing from REST for primary.")
            primary_df = self.get_historical_ohlcv(symbol, timeframe, max(n_candles, self._warmup_limit))

            if primary_df.empty:
                raise RuntimeError(f"CRITICAL API FAILURE: Could not fetch data for {symbol}. Halting trading cycle.")

        # 1. Single-Coin Focus (Saves API Limits)
        self.think(f"Market state: primary {symbol} ({len(primary_df)} rows hybrid).")
        ohlcv_by_symbol: dict[str, pd.DataFrame] = {symbol: primary_df}

        # 2. MTF Regime Radar Fetch (Parallelized)
        mtf_timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]
        mtf_dataframes = {}
        
        self.think("Fetching MTF data for Regime Radar in parallel...")
        import concurrent.futures
        import random

        def fetch_tf(tf):
            # A tiny random jitter (0-50ms) to prevent absolute simultaneous hits on Binance
            time.sleep(random.uniform(0.0, 0.05)) 
            return tf, self.get_historical_ohlcv(symbol, tf, limit=250)

        # Blast out all 6 network requests simultaneously
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            results = executor.map(fetch_tf, mtf_timeframes)
            for tf, df_mtf in results:
                mtf_dataframes[tf] = df_mtf

        macro_news = {
            "summary": "Hybrid feed: CCXT REST warm-up + Binance WebSocket klines.",
            "sentiment": "neutral",
        }

        # 3. Build the Payload
        standard_payload = {
            "symbol": symbol,
            "exchange": "binance",
            "timeframe": timeframe,
            "ohlcv_data": primary_df,
            "ohlcv_by_symbol": ohlcv_by_symbol,
            "universe": UNIVERSE,
            "macro_news": macro_news,
            "mtf_data": mtf_dataframes  # 🚨 This is what engine.py is looking for!
        }

        return self.act("fetch_market_data", standard_payload)


    def fetch_pairs_data(self, symbol_a: str, symbol_b: str, timeframe: str, limit: int) -> pd.DataFrame:
        df_a = self.get_historical_ohlcv(symbol_a, timeframe, limit)
        df_b = self.get_historical_ohlcv(symbol_b, timeframe, limit)

        df_a = df_a.rename(columns={col: f"{col}_A" for col in df_a.columns if col != "timestamp"})
        df_b = df_b.rename(columns={col: f"{col}_B" for col in df_b.columns if col != "timestamp"})

        merged = pd.merge(df_a, df_b, on="timestamp", how="inner")

        if 'close_A' in merged.columns and 'close_B' in merged.columns:
            merged['spread_ratio'] = merged['close_A'] / merged['close_B']

        return merged