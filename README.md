# Sev Stocks

A local dashboard that tracks the 50 largest S&P 500 companies by market cap.

## Run it

You need Python 3.10 or newer on macOS or Linux.

    git clone https://github.com/SevTitizian/sev-stocks.git
    cd sev-stocks
    ./run.sh

The first run creates a virtual environment and installs the dependencies.

It opens at http://localhost:8501 and loads in a few seconds. Stop it with Ctrl+C.

## What it shows

- **Summary row**: combined market cap, cap-weighted move today, how many are up or down,
  and the day's biggest gainer and loser.
- **Rankings**: price, today's move, market cap, 1-month, year-to-date and 1-year
  returns, plus a 30-day trend line for each stock. Click a column header to sort.
- **Sector map**: a treemap sized by market cap and colored by today's move.
- **Stock detail**: a price chart for one stock over 1M, 3M, 6M, YTD or 1Y.

The sidebar has a Refresh button, a one-minute auto-refresh toggle, and a
sector filter. Every refresh re-ranks the list, so a company that climbs into
the top 50 shows up right away.

## Data

- Members: Wikipedia's "List of S&P 500 companies" table.
- Prices and market caps: Yahoo Finance via `yfinance`. Quotes can be delayed up to 15 minutes.
- Companies with two share classes (Alphabet, Fox, News Corp) count once.

Prices and the ranking come from one Yahoo screener request (the 250 largest
US stocks), matched against the S&P 500 list. If Yahoo doesn't respond, the
app shows the last successful result and says when it's from.
