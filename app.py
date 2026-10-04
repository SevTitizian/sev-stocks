"""Sev Stocks: a dashboard for the 50 largest S&P 500 companies.

Ranks S&P 500 members by live market cap, keeps the 50 largest, and shows
prices, daily moves, and trends for them. Data comes from Wikipedia
(member list) and Yahoo Finance via yfinance.

Run with:  ./run.sh
"""

import io
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf
from yfinance import EquityQuery

TOP_N = 50
LAST_GOOD = Path(__file__).with_name("last_good.csv")
WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

# Diverging pair for daily moves: blue = up, red = down, neutral gray at 0.
# Blue/red stays distinguishable for colorblind readers, unlike green/red.
UP, DOWN = "#2a78d6", "#e34948"
UP_DARK, DOWN_DARK = "#3987e5", "#e66767"
MID_LIGHT, MID_DARK = "#f0efec", "#383835"
LINE = "#2a78d6"

st.set_page_config(page_title="Sev Stocks", page_icon="📈", layout="wide")


# ---------- data ----------

@st.cache_data(ttl=24 * 3600, show_spinner=False)
def load_constituents() -> pd.DataFrame:
    """Current S&P 500 members with name and sector."""
    html = requests.get(
        WIKI_URL, headers={"User-Agent": "Mozilla/5.0 sev-stocks"}, timeout=20
    ).text
    table = pd.read_html(io.StringIO(html), attrs={"id": "constituents"})[0]
    table = table.rename(
        columns={"Symbol": "Ticker", "Security": "Company", "GICS Sector": "Sector"}
    )[["Ticker", "Company", "Sector"]]
    # Yahoo uses BRK-B where Wikipedia uses BRK.B
    table["Ticker"] = table["Ticker"].str.replace(".", "-", regex=False)
    return table


@st.cache_data(ttl=60, show_spinner=False)
def largest_us_stocks() -> pd.DataFrame:
    """The 250 largest US-listed stocks by market cap, with live quotes.

    One screener request covers every stock, which keeps us well under
    Yahoo's rate limit (a request per ticker gets throttled)."""
    query = EquityQuery("and", [
        EquityQuery("eq", ["region", "us"]),
        EquityQuery("gt", ["intradaymarketcap", 2e10]),
    ])
    quotes = yf.screen(query, size=250, sortField="intradaymarketcap", sortAsc=False)["quotes"]
    return pd.DataFrame([{
        "Ticker": q["symbol"],
        "Price": q.get("regularMarketPrice"),
        "Prev Close": q.get("regularMarketPreviousClose"),
        "Market Cap": q.get("marketCap"),
    } for q in quotes]).dropna()


def top_by_market_cap() -> tuple[pd.DataFrame, str | None]:
    """The 50 largest S&P 500 members. If Yahoo can't be reached, falls back
    to the last successful result and returns a warning saying so."""
    error = None
    for attempt in range(3):
        try:
            ranked = load_constituents().merge(largest_us_stocks(), on="Ticker")
            break
        except Exception as e:
            # Yahoo and Wikipedia sometimes refuse a request for a few seconds
            error = f"{type(e).__name__}: {e}"
            time.sleep(2 * (attempt + 1))
    else:
        if not LAST_GOOD.exists():
            raise RuntimeError(
                "The market data sources didn't respond after 3 tries. Check your "
                f"internet connection, wait a minute, then press Refresh. ({error})"
            )
        when = datetime.fromtimestamp(LAST_GOOD.stat().st_mtime)
        return pd.read_csv(LAST_GOOD), (
            f"The market data sources didn't respond, so prices from "
            f"{when:%b %d at %I:%M %p} are shown. Press Refresh to try again. ({error})"
        )

    ranked = ranked.sort_values("Market Cap", ascending=False)
    # Companies with two share classes (GOOGL/GOOG, FOXA/FOX, NWSA/NWS) report the
    # whole company's market cap on each; keep one so nothing is counted twice
    company = ranked["Company"].str.replace(r"\s*\(Class [A-Z]\)", "", regex=True)
    ranked = ranked[~company.duplicated()].assign(Company=company).head(TOP_N)
    ranked.to_csv(LAST_GOOD, index=False)
    return ranked, None


@st.cache_data(ttl=15 * 60, show_spinner=False)
def price_history(tickers: tuple[str, ...]) -> pd.DataFrame:
    """One year of daily closes, one column per ticker."""
    closes = yf.download(
        list(tickers), period="1y", interval="1d", auto_adjust=True, progress=False
    )["Close"]
    # Drop today's empty bar while the market is open
    return closes.dropna(how="all")


def pct_since(closes: pd.Series, start) -> float | None:
    window = closes[closes.index >= pd.Timestamp(start)].dropna()
    if window.empty:
        return None
    return (closes.dropna().iloc[-1] / window.iloc[0] - 1) * 100


def build_table() -> tuple[pd.DataFrame, pd.DataFrame, str | None]:
    df, warning = top_by_market_cap()
    hist = price_history(tuple(df["Ticker"]))
    df["Day %"] = (df["Price"] / df["Prev Close"] - 1) * 100

    today = pd.Timestamp.now().normalize()
    year_start = pd.Timestamp(today.year, 1, 1)
    one_month = today - pd.DateOffset(months=1)
    rows = []
    for t in df["Ticker"]:
        s = hist[t].dropna() if t in hist else pd.Series(dtype=float)
        rows.append({
            "Ticker": t,
            "1M %": pct_since(s, one_month),
            "YTD %": pct_since(s, year_start),
            "1Y %": pct_since(s, s.index.min()) if not s.empty else None,
            "30-day trend": s.tail(30).round(2).tolist(),
        })
    df = df.merge(pd.DataFrame(rows), on="Ticker")
    df.insert(0, "Rank", range(1, len(df) + 1))
    return df, hist, warning


def is_dark() -> bool:
    try:
        return st.context.theme.type == "dark"
    except Exception:
        return False


def fmt_cap(v: float) -> str:
    return f"${v / 1e12:.2f}T" if v >= 1e12 else f"${v / 1e9:.0f}B"


def arrow(v: float) -> str:
    return f"▲ {v:.2f}%" if v > 0 else f"▼ {abs(v):.2f}%" if v < 0 else "0.00%"


# ---------- layout ----------

st.title("Sev Stocks")
st.caption("The 50 largest S&P 500 companies by market cap, re-ranked on every refresh.")

with st.sidebar:
    st.header("Controls")
    if st.button("Refresh", width="stretch"):
        largest_us_stocks.clear()
        price_history.clear()
    auto = st.toggle("Auto-refresh every minute", value=False)
    try:
        sectors = sorted(load_constituents()["Sector"].unique())
    except Exception:
        sectors = []
    picked = st.multiselect("Sectors", sectors, default=sectors)


@st.fragment(run_every=60 if auto else None)
def dashboard():
    with st.spinner("Loading market data…"):
        try:
            data, hist, warning = build_table()
        except Exception as e:
            st.error(f"Couldn't load market data. {e}")
            return
    if warning:
        st.warning(warning)
    view = data[data["Sector"].isin(picked)] if picked else data
    if view.empty:
        st.info("None of the top 50 are in the selected sectors.")
        return

    dark = is_dark()
    up, down = (UP_DARK, DOWN_DARK) if dark else (UP, DOWN)
    mid = MID_DARK if dark else MID_LIGHT

    # Summary row
    advancers = int((view["Day %"] > 0).sum())
    decliners = int((view["Day %"] < 0).sum())
    weighted = (view["Day %"] * view["Market Cap"]).sum() / view["Market Cap"].sum()
    best = view.loc[view["Day %"].idxmax()]
    worst = view.loc[view["Day %"].idxmin()]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Combined market cap", fmt_cap(view["Market Cap"].sum()))
    c2.metric("Cap-weighted move today", f"{weighted:+.2f}%")
    c3.metric("Up / down today", f"{advancers} / {decliners}")
    c4.metric(f"Top gainer · {best['Ticker']}", f"${best['Price']:,.2f}", f"{best['Day %']:+.2f}%")
    c5.metric(f"Top loser · {worst['Ticker']}", f"${worst['Price']:,.2f}", f"{worst['Day %']:+.2f}%")
    st.caption(f"Last updated {datetime.now():%b %d, %Y %I:%M:%S %p}")

    tab_table, tab_map, tab_detail = st.tabs(["Rankings", "Sector map", "Stock detail"])

    with tab_table:
        st.dataframe(
            view[["Rank", "Ticker", "Company", "Sector", "Price", "Day %", "Market Cap",
                  "1M %", "YTD %", "1Y %", "30-day trend"]],
            hide_index=True,
            width="stretch",
            height=min(38 + 35 * len(view), 1800),
            column_config={
                "Rank": st.column_config.NumberColumn(width="small"),
                "Price": st.column_config.NumberColumn(format="$%.2f"),
                "Day %": st.column_config.NumberColumn(format="%+.2f%%"),
                "Market Cap": st.column_config.NumberColumn(format="compact"),
                "1M %": st.column_config.NumberColumn(format="%+.1f%%"),
                "YTD %": st.column_config.NumberColumn(format="%+.1f%%"),
                "1Y %": st.column_config.NumberColumn(format="%+.1f%%"),
                "30-day trend": st.column_config.LineChartColumn(width="medium"),
            },
        )

    with tab_map:
        st.caption("Box size is market cap. Color is today's move: blue is up, red is down, "
                   "capped at ±3%.")
        tm = view.assign(
            Label=view["Ticker"] + "<br>" + view["Day %"].map(arrow),
            Cap=view["Market Cap"].map(fmt_cap),
        )
        fig = px.treemap(
            tm, path=[px.Constant("Top 50"), "Sector", "Ticker"], values="Market Cap",
            color="Day %", color_continuous_scale=[(0, down), (0.5, mid), (1, up)],
            range_color=(-3, 3), custom_data=["Company", "Cap", "Day %", "Price"],
        )
        fig.update_traces(
            marker=dict(line=dict(width=2)),
            texttemplate="<b>%{label}</b><br>%{customdata[2]:+.2f}%",
            hovertemplate="<b>%{label}</b> · %{customdata[0]}<br>Price $%{customdata[3]:,.2f}"
                          "<br>Market cap %{customdata[1]}<br>Today %{customdata[2]:+.2f}%<extra></extra>",
        )
        fig.update_layout(margin=dict(t=10, l=0, r=0, b=0), height=640,
                          coloraxis_colorbar=dict(title="Day %", ticksuffix="%"))
        st.plotly_chart(fig, width="stretch")

    with tab_detail:
        options = view["Ticker"] + " · " + view["Company"]
        choice = st.selectbox("Stock", options, index=0, key="detail_pick")
        ticker = choice.split(" · ")[0]
        period = st.segmented_control("Range", ["1M", "3M", "6M", "YTD", "1Y"],
                                      default="6M", key="detail_range") or "6M"

        closes = hist[ticker].dropna()
        end = closes.index.max()
        start = {
            "1M": end - pd.DateOffset(months=1), "3M": end - pd.DateOffset(months=3),
            "6M": end - pd.DateOffset(months=6), "YTD": pd.Timestamp(end.year, 1, 1),
            "1Y": closes.index.min(),
        }[period]
        series = closes[closes.index >= start]
        change = (series.iloc[-1] / series.iloc[0] - 1) * 100
        row = view.set_index("Ticker").loc[ticker]

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Price", f"${row['Price']:,.2f}", f"{row['Day %']:+.2f}% today")
        m2.metric(f"{period} change", f"{change:+.2f}%")
        m3.metric("Market cap", fmt_cap(row["Market Cap"]))
        m4.metric("Rank", f"#{int(row['Rank'])} of {len(data)}")

        fig = go.Figure(go.Scatter(
            x=series.index, y=series.values, mode="lines",
            line=dict(color=LINE, width=2), fill="tozeroy",
            fillcolor="rgba(42,120,214,0.10)",
            hovertemplate="%{x|%b %d, %Y}<br>$%{y:,.2f}<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=[series.index[-1]], y=[series.iloc[-1]], mode="markers",
            marker=dict(size=9, color=LINE, line=dict(width=2, color=mid)),
            hoverinfo="skip", showlegend=False,
        ))
        pad = (series.max() - series.min()) * 0.08 or 1
        fig.update_layout(
            height=420, margin=dict(t=10, l=0, r=0, b=0), showlegend=False,
            hovermode="x unified",
            yaxis=dict(range=[series.min() - pad, series.max() + pad], tickprefix="$"),
        )
        st.plotly_chart(fig, width="stretch")


dashboard()

st.caption("Data from Yahoo Finance (via yfinance) and Wikipedia's S&P 500 list. "
           "Quotes may be delayed up to 15 minutes. Not investment advice.")
