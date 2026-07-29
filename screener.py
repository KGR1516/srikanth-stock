"""NSE Volume Breakout Screener.

Finds stocks where BOTH conditions are true on the latest trading day:
1. Volume is at least N times the 20-day average volume (default 2.5x)
2. Close broke above the highest high of the previous 20 days

This is the classic "price breakout on unusually high volume" setup.

Run:
  python screener.py
  python screener.py --volume-multiple 3 --lookback 20
  python screener.py --stocks-file mylist.txt --output today.xlsx
  python screener.py --all-nse   # scan every NSE-listed equity instead of the curated list
  python screener.py --skip-delivery   # skip the extra delivery % lookup for hits

Educational tool only. Not investment advice.
"""

import argparse
import time
from datetime import datetime, timedelta

import pandas as pd
import requests
import yfinance as yf

# NSE has moved this file between domains over time; try each in order.
NSE_EQUITY_LIST_URLS = [
    "https://nsearchives.nseindia.com/content/equity/EQUITY_L.csv",
    "https://archives.nseindia.com/content/equity/EQUITY_L.csv",
]


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def check_breakout(df: pd.DataFrame, vol_multiple: float = 2.5, lookback: int = 20):
    """Return breakout details for the most recent bar, or None.

    df must be a daily OHLCV DataFrame with columns:
    Open, High, Low, Close, Volume.
    """
    df = df.dropna()
    if len(df) <= lookback + 14:  # need enough history for averages + RSI
        return None

    today = df.iloc[-1]
    history = df.iloc[:-1]  # exclude today from the averages

    avg_volume = history["Volume"].tail(lookback).mean()
    breakout_level = history["High"].tail(lookback).max()

    if not avg_volume or avg_volume != avg_volume:
        return None

    volume_ratio = float(today["Volume"]) / float(avg_volume)
    rsi_today = float(compute_rsi(df["Close"]).iloc[-1])

    if volume_ratio >= vol_multiple and float(today["Close"]) > float(breakout_level):
        return {
            "Close": round(float(today["Close"]), 2),
            "Breakout Level": round(float(breakout_level), 2),
            "% Above Level": round((float(today["Close"]) / float(breakout_level) - 1) * 100, 2),
            "Volume": int(today["Volume"]),
            "Avg Vol (20d)": int(avg_volume),
            "Volume x": round(volume_ratio, 2),
            "RSI(14)": round(rsi_today, 2),
        }
    return None


def load_symbols(path: str):
    with open(path) as f:
        return [
            line.strip().upper()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]


def fetch_all_nse_symbols_direct():
    """Download the current list of every NSE-listed equity symbol directly.

    NSE requires a browser-like session (cookies + headers) before it will
    serve this file, so we visit the homepage first to pick up cookies, then
    try each known archive domain in turn. Raises on failure so callers can
    fall back to another method.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    session = requests.Session()
    session.headers.update(headers)
    try:
        session.get("https://www.nseindia.com", timeout=15)
    except Exception:
        pass  # best effort; some archive URLs work without a live cookie too

    last_exc = None
    for url in NSE_EQUITY_LIST_URLS:
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            lines = resp.text.splitlines()
            symbols = []
            for line in lines[1:]:  # skip header row
                parts = line.split(",")
                symbol = parts[0].strip() if parts else ""
                if symbol:
                    symbols.append(symbol)
            if len(symbols) > 500:  # sanity check: a real listing has 1000s
                return symbols
            last_exc = RuntimeError(f"unexpectedly short list ({len(symbols)}) from {url}")
        except Exception as exc:
            last_exc = exc
    raise RuntimeError(f"could not fetch NSE equity list: {last_exc}")


def fetch_all_nse_symbols_nsepython():
    """Try nsepython's own NSE-session handling to get the full equity list.

    nsepython manages NSE's cookie/header/bot-detection requirements
    internally, which can be more reliable from cloud IPs (like GitHub
    Actions) than a raw requests session. Raises on failure so callers can
    fall back to another method.
    """
    from nsepython import nse_eq_symbols
    symbols = nse_eq_symbols()
    symbols = [str(s).strip().upper() for s in symbols if s and str(s).strip()]
    if len(symbols) > 500:
        return symbols
    raise RuntimeError(f"unexpectedly short list ({len(symbols)}) from nsepython")


def fetch_all_nse_symbols():
    """Get every NSE-listed equity symbol, trying multiple sources in turn.

    1. nsepython (handles NSE's bot-detection/session requirements itself)
    2. Direct download from NSE's archive CSV
    Raises only if every method fails, so the caller can fall back to a
    static watchlist (stocks.txt).
    """
    try:
        symbols = fetch_all_nse_symbols_nsepython()
        print(f"Fetched {len(symbols)} NSE-listed equities via nsepython.")
        return symbols
    except Exception as exc:
        print(f"nsepython fetch failed ({exc}); trying direct NSE archive download...")

    symbols = fetch_all_nse_symbols_direct()
    print(f"Fetched {len(symbols)} NSE-listed equities from NSE's archive CSV.")
    return symbols


def get_delivery_percent(symbol: str):
    """Best-effort lookup of the latest delivery % for a symbol via nsepython.

    Delivery % is the share of traded volume that actually changed hands
    (settled into demat accounts) rather than being squared off intraday.
    A volume breakout with high delivery % is more likely to be genuine
    accumulation rather than a speculative intraday pump. Returns None if
    nsepython isn't available or the lookup fails for any reason - this is
    an optional enrichment, never required for the core breakout logic.
    """
    try:
        from nsepython import equity_history
        end = datetime.now()
        start = end - timedelta(days=10)
        hist = equity_history(symbol, "EQ", start.strftime("%d-%m-%Y"), end.strftime("%d-%m-%Y"))
        if hist is None or len(hist) == 0:
            return None
        row = hist.iloc[-1]
        for col in ("COP_DELIV_PERC", "CH_DELIV_PERC", "DELIV_PER", "%DlyQttoTradedQty"):
            if col in row and row[col] not in (None, ""):
                return round(float(row[col]), 2)
    except Exception:
        return None
    return None


def scan_batch(symbols, vol_multiple, lookback):
    """Download one batch of tickers and check each for a breakout."""
    tickers = [s if s.endswith(".NS") else s + ".NS" for s in symbols]
    hits = {}
    try:
        data = yf.download(tickers, period="6mo", interval="1d",
                            group_by="ticker", auto_adjust=False,
                            threads=True, progress=False)
    except Exception as exc:
        print(f"  batch download failed: {exc}")
        return hits

    for sym, ticker in zip(symbols, tickers):
        try:
            df = data[ticker] if len(tickers) > 1 else data
            result = check_breakout(df, vol_multiple, lookback)
            if result:
                hits[sym] = result
        except Exception as exc:
            print(f"  skipped {sym}: {exc}")
    return hits


def main():
    parser = argparse.ArgumentParser(description="NSE volume breakout screener")
    parser.add_argument("--stocks-file", default="stocks.txt",
                         help="text file with one NSE symbol per line")
    parser.add_argument("--all-nse", action="store_true",
                         help="scan every NSE-listed equity instead of --stocks-file")
    parser.add_argument("--volume-multiple", type=float, default=2.5,
                         help="today's volume must be >= this x 20-day average")
    parser.add_argument("--lookback", type=int, default=20,
                         help="days used for average volume and breakout high")
    parser.add_argument("--batch-size", type=int, default=150,
                         help="how many tickers to download from Yahoo Finance at a time")
    parser.add_argument("--skip-delivery", action="store_true",
                         help="skip the extra delivery %% lookup for breakout hits")
    parser.add_argument("--output", default="breakouts.xlsx",
                         help="Excel file to save results")
    args = parser.parse_args()

    if args.all_nse:
        try:
            symbols = fetch_all_nse_symbols()
        except Exception as exc:
            print(f"Could not fetch the full NSE list ({exc}); falling back to {args.stocks_file}.")
            symbols = load_symbols(args.stocks_file)
    else:
        symbols = load_symbols(args.stocks_file)

    print(f"Scanning {len(symbols)} NSE stocks "
          f"(volume >= {args.volume_multiple}x avg, {args.lookback}-day breakout)...")

    hits = {}
    for i in range(0, len(symbols), args.batch_size):
        batch = symbols[i:i + args.batch_size]
        print(f"  batch {i // args.batch_size + 1}: {len(batch)} symbols...")
        hits.update(scan_batch(batch, args.volume_multiple, args.lookback))
        time.sleep(2)  # be gentle on Yahoo Finance between batches

    if not hits:
        print("No volume breakouts today with the current settings.")
        print("Tip: try --volume-multiple 2, or run after 3:30 PM market close.")
        return

    table = pd.DataFrame.from_dict(hits, orient="index")
    table = table.sort_values("Volume x", ascending=False)

    if not args.skip_delivery:
        print("Fetching delivery % for breakout candidates (best-effort, via nsepython)...")
        delivery = {}
        for sym in table.index:
            delivery[sym] = get_delivery_percent(sym)
            time.sleep(0.5)  # be gentle on NSE between lookups
        table["Delivery %"] = table.index.map(delivery)

    print(f"=== Volume breakouts \u2014 {datetime.now():%d-%b-%Y} ===")
    print(table.to_string())

    table.to_excel(args.output, index_label="Symbol")
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
