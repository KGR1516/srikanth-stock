"""NSE Volume Breakout Screener.

Finds stocks where BOTH conditions are true on the latest trading day:
  1. Volume is at least N times the 20-day average volume (default 2.5x)
  2. Close broke above the highest high of the previous 20 days

This is the classic "price breakout on unusually high volume" setup.

Run:
    python screener.py
    python screener.py --volume-multiple 3 --lookback 20
    python screener.py --stocks-file mylist.txt --output today.xlsx

Educational tool only. Not investment advice.
"""

import argparse
from datetime import datetime

import pandas as pd
import yfinance as yf


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


def main():
    parser = argparse.ArgumentParser(description="NSE volume breakout screener")
    parser.add_argument("--stocks-file", default="stocks.txt",
                         help="text file with one NSE symbol per line")
    parser.add_argument("--volume-multiple", type=float, default=2.5,
                         help="today's volume must be >= this x 20-day average")
    parser.add_argument("--lookback", type=int, default=20,
                         help="days used for average volume and breakout high")
    parser.add_argument("--output", default="breakouts.xlsx",
                         help="Excel file to save results")
    args = parser.parse_args()

    symbols = load_symbols(args.stocks_file)
    tickers = [s if s.endswith(".NS") else s + ".NS" for s in symbols]

    print(f"Scanning {len(tickers)} NSE stocks "
          f"(volume >= {args.volume_multiple}x avg, {args.lookback}-day breakout)...")

    data = yf.download(tickers, period="6mo", interval="1d",
                        group_by="ticker", auto_adjust=False,
                        threads=True, progress=False)

    hits = {}
    for sym, ticker in zip(symbols, tickers):
        try:
            df = data[ticker] if len(tickers) > 1 else data
            result = check_breakout(df, args.volume_multiple, args.lookback)
            if result:
                hits[sym] = result
        except Exception as exc:
            print(f"  skipped {sym}: {exc}")

    if not hits:
        print("No volume breakouts today with the current settings.")
        print("Tip: try --volume-multiple 2, or run after 3:30 PM market close.")
        return

    table = pd.DataFrame.from_dict(hits, orient="index")
    table = table.sort_values("Volume x", ascending=False)

    print(f"=== Volume breakouts \u2014 {datetime.now():%d-%b-%Y} ===")
    print(table.to_string())

    table.to_excel(args.output, index_label="Symbol")
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
