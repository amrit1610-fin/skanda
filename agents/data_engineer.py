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
VALID_TIMEFRAMES = {"5m", "15m", "1h", "4h"}

# Timeframe → default REST candle count (primary & multi-coin panels)
TF_CANDLES = {"5m": 288, "15m": 96, "1h": 168, "4h": 90}

# CCXT interval string (Binance spot)
TF_CCXT = {"5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h"}

# Binance combined stream kline suffix
TF_BINANCE_WS = {"5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h"}

BINANCE_WS_BASE = "wss://stream.binance.com:9443/ws"

_DEFAULT_WARMUP_LIMIT = 500
_CANDLE_DEQUE_MAX = 5000
_RECONNECT_BACKOFF_MAX = 60.0


def _mock_ohlcv_for_symbol(symbol: str, n_candles: int, timeframe: str) -> pd.DataFrame:
    """Deterministic-per-symbol mock OHLCV (fallback for offline / CCXT failure)."""
    seed = int(hashlib.sha256(f"{symbol}:{timeframe}:{n_candles}".encode()).hexdigest()[:8], 16) % (2**31)
    rng = np.random.default_rng(seed)

    base_price = 20000.0 + (seed % 50000) / 10.0
    pct_moves = rng.normal(0, 0.008, n_candles)
    closes = base_price * np.cumprod(1 + pct_moves)
    ts_base = int(time.time() * 1000) - n_candles * 60_000
    timestamps = [ts_base + i * 60_000 for i in range(n_candles)]

    return pd.DataFrame({
        "timestamp": timestamps,
        "open": closes * (1 + rng.uniform(-0.002, 0.002, n_candles)),
        "high": closes * (1 + np.abs(rng.normal(0, 0.004, n_candles))),
        "low": closes * (1 - np.abs(rng.normal(0, 0.004, n_candles))),
        "close": closes,
        "volume": rng.integers(500, 5000, n_candles).astype(float),
    })


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
    Output schema: timestamp (Unix ms), open, high, low, close, volume.
    """

    def __init__(self):
        skill_path = os.path.join(os.path.dirname(__file__), "..", ".skills", "data_engineer", "system_prompt.md")
        super().__init__("DataEngineer", skill_path)
        self._lock = threading.RLock()
        self._candles: deque[dict[str, Any]] = deque(maxlen=_CANDLE_DEQUE_MAX)
        self._partial: Optional[dict[str, Any]] = None
        self._exchange: Optional[ccxt.binance] = None
        self._warmup_limit = _DEFAULT_WARMUP_LIMIT
        self._live_symbol: Optional[str] = None
        self._live_timeframe: Optional[str] = None
        self._stream_stop = threading.Event()

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

    def get_historical_ohlcv(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        """
        Fetch historical OHLCV via CCXT (Binance). Returns columns:
        timestamp, open, high, low, close, volume (timestamp = Unix milliseconds).
        """
        tf = timeframe if timeframe in VALID_TIMEFRAMES else "5m"
        ccxt_tf = TF_CCXT.get(tf, "5m")
        pair = _to_ccxt_symbol(symbol)
        lim = max(10, min(int(limit), 1500))

        try:
            ex = self._get_exchange()
            # Dynamic since: count backward from now based on candle duration
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
            n = TF_CANDLES.get(tf, 288)
            return _mock_ohlcv_for_symbol(symbol, min(n, lim), tf)

        if not raw:
            self.think(f"Empty OHLCV from exchange for {pair}; using mock fallback.")
            n = TF_CANDLES.get(tf, 288)
            return _mock_ohlcv_for_symbol(symbol, min(n, lim), tf)

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
        """Load REST history into the thread-safe buffer (call before live stream)."""
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
        """
        Merge completed historical buffer with the current in-flight kline for a seamless OHLCV DataFrame.
        Columns: timestamp, open, high, low, close, volume (timestamp = Unix ms).
        """
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
        """
        Connect to Binance public WebSocket kline stream; update buffer with live OHLCV.
        Automatic reconnection with exponential backoff.
        """
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

    def fetch_market_data(self):
        """Primary symbol: hybrid buffer; universe peers: REST-only historical panels."""
        symbol = self._get_active_symbol()
        timeframe = self._get_timeframe()
        n_candles = TF_CANDLES.get(timeframe, 288)

        primary_df = self.get_latest_market_state()
        if primary_df.empty:
            self.think("Hybrid buffer empty; refreshing from REST for primary.")
            primary_df = self.get_historical_ohlcv(symbol, timeframe, max(n_candles, self._warmup_limit))

        self.think(
            f"Market state: primary {symbol} ({len(primary_df)} rows hybrid), "
            f"fetching REST panels for {len(UNIVERSE)} symbols @ {timeframe}."
        )

        ohlcv_by_symbol: dict[str, pd.DataFrame] = {symbol: primary_df}
        others = [s for s in UNIVERSE if s != symbol]
        with ThreadPoolExecutor(max_workers=min(10, len(others) + 1)) as ex:
            futures = {
                ex.submit(self._fetch_one_symbol_historical, sym, n_candles, timeframe): sym
                for sym in others
            }
            for fut in as_completed(futures):
                sym, df = fut.result()
                ohlcv_by_symbol[sym] = df

        macro_news = {
            "summary": "Hybrid feed: CCXT REST warm-up + Binance WebSocket klines.",
            "sentiment": "neutral",
        }

        standard_payload = {
            "symbol": symbol,
            "exchange": "binance",
            "timeframe": timeframe,
            "ohlcv_data": primary_df,
            "ohlcv_by_symbol": ohlcv_by_symbol,
            "universe": UNIVERSE,
            "macro_news": macro_news,
        }

        return self.act("fetch_market_data", standard_payload)

    def fetch_pairs_data(self, symbol_a: str, symbol_b: str, timeframe: str, limit: int) -> pd.DataFrame:
        """
        Fetch historical OHLCV for two symbols and merge them for pairs trading analysis.
        Calculates the spread_ratio as close_A / close_B.
        """
        df_a = self.get_historical_ohlcv(symbol_a, timeframe, limit)
        df_b = self.get_historical_ohlcv(symbol_b, timeframe, limit)

        # Prefix columns except timestamp
        df_a = df_a.rename(columns={col: f"{col}_A" for col in df_a.columns if col != "timestamp"})
        df_b = df_b.rename(columns={col: f"{col}_B" for col in df_b.columns if col != "timestamp"})

        # Inner join on timestamp to ensure exact temporal alignment
        merged = pd.merge(df_a, df_b, on="timestamp", how="inner")

        # Calculate spread ratio
        if 'close_A' in merged.columns and 'close_B' in merged.columns:
            merged['spread_ratio'] = merged['close_A'] / merged['close_B']

        return merged
