# NSE Volume Breakout Screener

Scans NSE stocks and flags the ones where, on the latest trading day:

1. **Volume** is at least **2.5x the 20-day average volume**, AND
2. **Close** broke above the **highest high of the previous 20 days**

That combination — a price breakout on unusually high volume — is the setup
behind most "sudden breakout" stocks. It also shows RSI(14) and how far above
the breakout level the stock closed, so you can judge if you are early or late.

## Setup

```bash
pip install -r requirements.txt
```

## Run

```bash
python screener.py
```

Options:

```bash
python screener.py --volume-multiple 3      # stricter: 3x average volume
python screener.py --lookback 50            # breakout above 50-day high
python screener.py --stocks-file mylist.txt # scan your own list
```

Results print to the screen and save to `breakouts.csv`.

## Edit the watchlist

`stocks.txt` has ~120 liquid NSE stocks. Add or remove symbols freely —
one symbol per line, without the `.NS` suffix (the script adds it).

## Best time to run

After market close (3:30 PM IST), so the day's full volume is counted.
Running mid-session compares a partial day's volume against full-day
averages and will miss breakouts still forming.

## Notes

- Data comes from Yahoo Finance via the `yfinance` library (free, ~15 min delayed).
- A volume breakout is a starting point for research, not a buy signal.
  Always check *why* the volume came (news, results, or just a tip channel pump)
  and the delivery percentage on the NSE website.
- Educational use only. Not investment advice.
