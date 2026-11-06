# Cloud ETF Breakout Bot — PAPER ONLY

This package extends the uploaded `bot.py` strategy (`strategy_original.py`) with a scheduled paper execution engine. **There is no live Robinhood connection, order placement, or OAuth implementation.** It cannot trade real money even if Robinhood approvals are off.

## iPhone-only GitHub + Railway setup

1. Create a **private** GitHub repository. Upload these files to its root using GitHub's web interface (or a Git client). Do not upload passwords, tokens, or `.env` files.
2. In Railway, create a project **Deploy from GitHub repo** and choose that private repo. Railway builds the included `Dockerfile`.
3. Add a persistent Railway **Volume**, mounted at `/data`. Without a volume, paper positions and trade history disappear on redeploy/restart.
4. Set environment variables `STATE_PATH=/data/paper.json` and `KILL_SWITCH=false`. Use **one replica only**. Railway service must remain running; review billing and resource limits.
5. Read deployment logs. After 5 PM America/New_York on a US market day, the worker fetches completed daily candles, processes the prior day's queued entries at the new day's open, and screens for next-session signals. It polls hourly; once a date is processed, it won't process again.
6. To stop processing, set `KILL_SWITCH=true` and redeploy. To reset paper results, stop the service and delete `/data/paper.json` from the volume.

## Safety and important limitations

- Uses public Yahoo Finance historical daily candles through `yfinance`; **not guaranteed accurate or timely**, and **not broker quotes**. If data is missing, the engine fails closed. US exchange holidays are naturally skipped if no current SPY candle exists.
- This is **end-of-day paper simulation**: orders are simulated at the next day's historical open *after that session has finished*. It does not send an order at the actual open, and cannot protect a live position intraday.
- Paper stop/target fills are simplified. Gaps may exceed the $2.50 planned risk; simultaneous intraday stop and target assumes the stop hit first. Fees, slippage, dividends, corporate actions, and liquidity are not modeled comprehensively.
- Capital $625; strategy allocation $500; $125 kept outside strategy; $400 maximum exposure; 2 positions; $2.50 planned stop risk; weekly realized-loss cutoff $10; drawdown halt $30. Loss halt is persistent until manually reset.
- **No live broker code.** A future live adapter needs verified Robinhood MCP authorization for an unattended cloud process, supported account scopes, durable order IDs, bracket/OCO handling, broker-side risk checks, reconciliation, and extensive paper testing. Do not turn on live trading based on this package.
- The bot requires a single worker and persistent state; there is no distributed lock. Not suitable for multiple replicas or high-frequency trading.
