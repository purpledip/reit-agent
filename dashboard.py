import streamlit as st
import pandas as pd
import yfinance as yf
import csv, os
from datetime import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="REIT Agent Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Syne:wght@400;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Syne', sans-serif;
    background-color: #0a0f1e;
    color: #e8eaf0;
}

.stApp { background-color: #0a0f1e; }

/* Hide default streamlit header */
header[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }

/* Metric cards */
.metric-card {
    background: linear-gradient(135deg, #111827 0%, #1a2236 100%);
    border: 1px solid #1e2d45;
    border-radius: 16px;
    padding: 24px 28px;
    position: relative;
    overflow: hidden;
}
.metric-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
}
.metric-card.blue::before  { background: linear-gradient(90deg, #3b82f6, #60a5fa); }
.metric-card.green::before { background: linear-gradient(90deg, #10b981, #34d399); }
.metric-card.amber::before { background: linear-gradient(90deg, #f59e0b, #fbbf24); }
.metric-card.purple::before{ background: linear-gradient(90deg, #8b5cf6, #a78bfa); }
.metric-card.red::before   { background: linear-gradient(90deg, #ef4444, #f87171); }

.metric-label {
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #6b7fa3;
    margin-bottom: 8px;
}
.metric-value {
    font-family: 'Syne', sans-serif;
    font-size: 32px;
    font-weight: 700;
    color: #f0f4ff;
    line-height: 1;
}
.metric-sub {
    font-family: 'DM Mono', monospace;
    font-size: 12px;
    color: #6b7fa3;
    margin-top: 6px;
}
.metric-change-pos { color: #34d399; font-weight: 600; }
.metric-change-neg { color: #f87171; font-weight: 600; }

/* Section headers */
.section-header {
    font-family: 'Syne', sans-serif;
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: #4b6cb7;
    margin: 32px 0 16px 0;
    display: flex;
    align-items: center;
    gap: 10px;
}
.section-header::after {
    content: '';
    flex: 1;
    height: 1px;
    background: linear-gradient(90deg, #1e2d45, transparent);
}

/* Dashboard title */
.dash-title {
    font-family: 'Syne', sans-serif;
    font-size: 28px;
    font-weight: 800;
    background: linear-gradient(135deg, #60a5fa, #a78bfa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: -0.02em;
}
.dash-sub {
    font-family: 'DM Mono', monospace;
    font-size: 12px;
    color: #4b6cb7;
    margin-top: 4px;
}

/* Signal badge */
.signal-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.05em;
}
.signal-buy    { background: #0d2e1e; color: #34d399; border: 1px solid #065f46; }
.signal-hold   { background: #2d2206; color: #fbbf24; border: 1px solid #78350f; }
.signal-skip   { background: #1f0707; color: #f87171; border: 1px solid #7f1d1d; }

/* Transaction row */
.tx-row {
    display: flex;
    align-items: center;
    padding: 12px 16px;
    background: #111827;
    border-radius: 10px;
    margin-bottom: 6px;
    border: 1px solid #1e2d45;
    font-family: 'DM Mono', monospace;
    font-size: 12px;
    gap: 12px;
}
.tx-date { color: #4b6cb7; min-width: 90px; }
.tx-stock { color: #60a5fa; min-width: 80px; font-weight: 500; }
.tx-amount { color: #f0f4ff; flex: 1; }
.tx-units { color: #6b7fa3; }
.tx-skip { color: #4b6cb7; font-style: italic; }

/* Plotly chart container */
[data-testid="stPlotlyChart"] {
    background: transparent !important;
}

/* Streamlit elements override */
div[data-testid="metric-container"] {
    background: #111827;
    border: 1px solid #1e2d45;
    border-radius: 12px;
    padding: 16px;
}

.stSelectbox > div { background: #111827; border-color: #1e2d45; }
</style>
""", unsafe_allow_html=True)


# ── Helper: load purchases.csv ────────────────────────────────────────────────
LOG_FILE = "purchases.csv"
MONTHLY_CAP = 5000

@st.cache_data(ttl=60)
def load_purchases():
    if not os.path.exists(LOG_FILE):
        return pd.DataFrame()

    with open(LOG_FILE, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["embassy_amt"]   = df["embassy_amt"].astype(float)
    df["biret_amt"]     = df["biret_amt"].astype(float)
    df["embassy_price"] = df["embassy_price"].astype(float)
    df["biret_price"]   = df["biret_price"].astype(float)
    df["date"]          = pd.to_datetime(df["date"])
    return df


@st.cache_data(ttl=300)
def fetch_stock_data(ticker, period="3mo"):
    df = yf.download(ticker, period=period, interval="1d", progress=False)
    df.dropna(inplace=True)
    return df

@st.cache_data(ttl=60)
def get_current_price(ticker):
    try:
        info = yf.Ticker(ticker).info
        return info.get("currentPrice") or info.get("regularMarketPrice") or 0
    except:
        return 0

def compute_rsi(series, period=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss
    return 100 - (100 / (1 + rs))

def compute_macd(series):
    ema12 = series.ewm(span=12).mean()
    ema26 = series.ewm(span=26).mean()
    macd  = ema12 - ema26
    signal= macd.ewm(span=9).mean()
    return macd, signal


# ── Chart theme ───────────────────────────────────────────────────────────────
CHART_BG    = "#0a0f1e"
CHART_PAPER = "#0a0f1e"
GRID_COLOR  = "#1e2d45"
TEXT_COLOR  = "#6b7fa3"
FONT_FAMILY = "DM Mono"

def chart_layout(title="", height=320):
    return dict(
        title=dict(text=title, font=dict(family="Syne", size=14, color="#8ba3cc")),
        plot_bgcolor=CHART_BG,
        paper_bgcolor=CHART_PAPER,
        font=dict(family=FONT_FAMILY, color=TEXT_COLOR),
        height=height,
        margin=dict(l=12, r=12, t=40, b=12),
        xaxis=dict(showgrid=False, color=TEXT_COLOR, tickfont=dict(size=10)),
        yaxis=dict(gridcolor=GRID_COLOR, color=TEXT_COLOR, tickfont=dict(size=10), zeroline=False),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="#1a2236", bordercolor="#1e2d45", font=dict(family=FONT_FAMILY)),
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

# Title row
col_title, col_refresh = st.columns([4, 1])
with col_title:
    st.markdown('<div class="dash-title">REIT Agent Dashboard</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="dash-sub">EMBASSY.NS · BIRET.NS · Updated {datetime.now().strftime("%d %b %Y, %H:%M")}</div>', unsafe_allow_html=True)
with col_refresh:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("⟳  Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.markdown("---")

# ── Load data ─────────────────────────────────────────────────────────────────
purchases   = load_purchases()
emb_hist    = fetch_stock_data("EMBASSY.NS", "3mo")
bir_hist    = fetch_stock_data("BIRET.NS",   "3mo")
emb_price   = get_current_price("EMBASSY.NS")
bir_price   = get_current_price("BIRET.NS")

# Month stats
cur_month = datetime.today().strftime("%Y-%m")
if not purchases.empty:
    month_data = purchases[purchases["month"] == cur_month]
    spent_emb  = month_data["embassy_amt"].sum()
    spent_bir  = month_data["biret_amt"].sum()
    total_spent= spent_emb + spent_bir
    remaining  = max(0, MONTHLY_CAP - total_spent)
    buy_days   = len(month_data[(month_data["embassy_amt"] > 0) | (month_data["biret_amt"] > 0)])
    skip_days  = len(month_data[(month_data["embassy_amt"] == 0) & (month_data["biret_amt"] == 0)])
else:
    spent_emb = spent_bir = total_spent = 0
    remaining = MONTHLY_CAP
    buy_days = skip_days = 0

# All-time totals
if not purchases.empty:
    total_emb_invested = purchases["embassy_amt"].sum()
    total_bir_invested = purchases["biret_amt"].sum()
    total_invested     = total_emb_invested + total_bir_invested

    # Compute approximate current value
    emb_units = (purchases[purchases["embassy_amt"] > 0]
                 .apply(lambda r: r["embassy_amt"] / r["embassy_price"] if r["embassy_price"] > 0 else 0, axis=1)
                 .sum())
    bir_units = (purchases[purchases["biret_amt"] > 0]
                 .apply(lambda r: r["biret_amt"] / r["biret_price"] if r["biret_price"] > 0 else 0, axis=1)
                 .sum())
    current_value = emb_units * emb_price + bir_units * bir_price
    pnl           = current_value - total_invested
    pnl_pct       = (pnl / total_invested * 100) if total_invested > 0 else 0
else:
    total_invested = current_value = pnl = pnl_pct = 0
    emb_units = bir_units = 0


# ════════════════════════════════════════════════════════
#  SECTION 1 — OVERVIEW KPI CARDS
# ════════════════════════════════════════════════════════
st.markdown('<div class="section-header">Portfolio Overview</div>', unsafe_allow_html=True)

k1, k2, k3, k4, k5 = st.columns(5)

with k1:
    change_class = "metric-change-pos" if pnl >= 0 else "metric-change-neg"
    sign = "+" if pnl >= 0 else ""
    st.markdown(f"""
    <div class="metric-card purple">
        <div class="metric-label">Total Invested</div>
        <div class="metric-value">₹{total_invested:,.0f}</div>
        <div class="metric-sub <{change_class}>">All time</div>
    </div>""", unsafe_allow_html=True)

with k2:
    st.markdown(f"""
    <div class="metric-card blue">
        <div class="metric-label">Current Value</div>
        <div class="metric-value">₹{current_value:,.0f}</div>
        <div class="metric-sub">Live prices</div>
    </div>""", unsafe_allow_html=True)

with k3:
    pnl_color = "green" if pnl >= 0 else "red"
    sign = "+" if pnl >= 0 else ""
    st.markdown(f"""
    <div class="metric-card {pnl_color}">
        <div class="metric-label">Unrealised P&amp;L</div>
        <div class="metric-value">{sign}₹{abs(pnl):,.0f}</div>
        <div class="metric-sub">{sign}{pnl_pct:.2f}% return</div>
    </div>""", unsafe_allow_html=True)

with k4:
    budget_pct = int((total_spent / MONTHLY_CAP) * 100) if MONTHLY_CAP > 0 else 0
    st.markdown(f"""
    <div class="metric-card amber">
        <div class="metric-label">This Month</div>
        <div class="metric-value">₹{total_spent:,.0f}</div>
        <div class="metric-sub">₹{remaining:,.0f} remaining · {budget_pct}% used</div>
    </div>""", unsafe_allow_html=True)

with k5:
    st.markdown(f"""
    <div class="metric-card blue">
        <div class="metric-label">Agent Activity</div>
        <div class="metric-value">{buy_days}</div>
        <div class="metric-sub">buy days · {skip_days} skipped this month</div>
    </div>""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════
#  SECTION 2 — STOCK PRICES + INDICATORS
# ════════════════════════════════════════════════════════
st.markdown('<div class="section-header">Stock Performance</div>', unsafe_allow_html=True)

tab1, tab2 = st.tabs(["📊 EMBASSY.NS", "📊 BIRET.NS"])

def stock_panel(df_hist, ticker_label, current_price, purchases_df, col_amt, col_price):
    if df_hist.empty:
        st.warning(f"Could not fetch data for {ticker_label}")
        return

    close = df_hist["Close"].squeeze()

    # Price change
    prev_close  = close.iloc[-2] if len(close) > 1 else close.iloc[-1]
    day_chg     = current_price - prev_close
    day_chg_pct = (day_chg / prev_close) * 100 if prev_close else 0
    week_chg_pct= ((close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] * 100) if len(close) > 5 else 0
    month_chg_pct=((close.iloc[-1] - close.iloc[0])  / close.iloc[0] * 100)  if len(close) > 0 else 0
    sma20       = close.rolling(20).mean()
    sma50       = close.rolling(50).mean()
    rsi_vals    = compute_rsi(close)
    macd_line, signal_line = compute_macd(close)

    # Mini KPIs
    m1, m2, m3, m4 = st.columns(4)
    sign = "▲" if day_chg >= 0 else "▼"
    color= "#34d399" if day_chg >= 0 else "#f87171"
    m1.metric("Current Price",  f"₹{current_price:.2f}", f"{sign} {abs(day_chg_pct):.2f}% today")
    m2.metric("1-Week Change",  f"{week_chg_pct:+.2f}%")
    m3.metric("3-Month Change", f"{month_chg_pct:+.2f}%")
    rsi_now = float(rsi_vals.iloc[-1]) if not rsi_vals.empty else 50
    rsi_label = "Oversold 🟢" if rsi_now < 35 else "Overbought 🔴" if rsi_now > 65 else "Neutral 🟡"
    m4.metric("RSI (14)", f"{rsi_now:.1f}", rsi_label)

    # ── Price + SMA chart ──────────────────────────────────────
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_hist.index, y=close,
        name="Price", line=dict(color="#60a5fa", width=2),
        fill="tozeroy", fillcolor="rgba(59,130,246,0.06)"
    ))
    fig.add_trace(go.Scatter(
        x=df_hist.index, y=sma20,
        name="SMA 20", line=dict(color="#f59e0b", width=1.2, dash="dot")
    ))
    fig.add_trace(go.Scatter(
        x=df_hist.index, y=sma50,
        name="SMA 50", line=dict(color="#a78bfa", width=1.2, dash="dash")
    ))

    # Mark purchase dates
    if purchases_df is not None and not purchases_df.empty:
        buys = purchases_df[purchases_df[col_amt] > 0]
        if not buys.empty:
            buy_dates  = pd.to_datetime(buys["date"])
            buy_prices = buys[col_price].values
            fig.add_trace(go.Scatter(
                x=buy_dates, y=buy_prices,
                mode="markers", name="Your buys",
                marker=dict(color="#34d399", size=10, symbol="triangle-up",
                            line=dict(color="#065f46", width=1))
            ))

    layout = chart_layout(f"{ticker_label} — Price & Moving Averages", height=300)
    layout["yaxis"]["tickprefix"] = "₹"
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True)

    # ── RSI + MACD side by side ────────────────────────────────
    c1, c2 = st.columns(2)

    with c1:
        fig_rsi = go.Figure()
        fig_rsi.add_trace(go.Scatter(
            x=df_hist.index, y=rsi_vals,
            line=dict(color="#60a5fa", width=1.8), name="RSI"
        ))
        fig_rsi.add_hline(y=70, line_dash="dot", line_color="#f87171", line_width=1, opacity=0.6)
        fig_rsi.add_hline(y=30, line_dash="dot", line_color="#34d399", line_width=1, opacity=0.6)
        fig_rsi.add_hrect(y0=30, y1=70, fillcolor="rgba(255,255,255,0.02)", line_width=0)
        fig_rsi.update_layout(**chart_layout("RSI (14)", height=220))
        fig_rsi.update_layout(yaxis=dict(range=[0, 100], gridcolor=GRID_COLOR,
                                          tickfont=dict(size=10), color=TEXT_COLOR, zeroline=False))
        st.plotly_chart(fig_rsi, use_container_width=True)

    with c2:
        fig_macd = go.Figure()
        hist_macd = macd_line - signal_line
        colors_macd = ["#34d399" if v >= 0 else "#f87171" for v in hist_macd]
        fig_macd.add_trace(go.Bar(
            x=df_hist.index, y=hist_macd,
            marker_color=colors_macd, name="Histogram", opacity=0.7
        ))
        fig_macd.add_trace(go.Scatter(
            x=df_hist.index, y=macd_line,
            line=dict(color="#60a5fa", width=1.5), name="MACD"
        ))
        fig_macd.add_trace(go.Scatter(
            x=df_hist.index, y=signal_line,
            line=dict(color="#f59e0b", width=1.5, dash="dot"), name="Signal"
        ))
        fig_macd.update_layout(**chart_layout("MACD", height=220))
        st.plotly_chart(fig_macd, use_container_width=True)

with tab1:
    stock_panel(emb_hist, "EMBASSY.NS", emb_price, purchases, "embassy_amt", "embassy_price")

with tab2:
    stock_panel(bir_hist, "BIRET.NS",   bir_price, purchases, "biret_amt",   "biret_price")


# ════════════════════════════════════════════════════════
#  SECTION 3 — AGENT PERFORMANCE
# ════════════════════════════════════════════════════════
st.markdown('<div class="section-header">Agent Performance</div>', unsafe_allow_html=True)

left, right = st.columns([3, 2])

with left:
    # Cumulative investment over time
    if not purchases.empty:
        df_sorted = purchases.sort_values("date").copy()
        df_sorted["total_amt"] = df_sorted["embassy_amt"] + df_sorted["biret_amt"]
        df_sorted["cum_invested"] = df_sorted["total_amt"].cumsum()
        df_sorted["cum_emb"]      = df_sorted["embassy_amt"].cumsum()
        df_sorted["cum_bir"]      = df_sorted["biret_amt"].cumsum()

        fig_cum = go.Figure()
        fig_cum.add_trace(go.Scatter(
            x=df_sorted["date"], y=df_sorted["cum_emb"],
            name="EMBASSY", stackgroup="one",
            line=dict(color="#60a5fa"), fillcolor="rgba(59,130,246,0.35)"
        ))
        fig_cum.add_trace(go.Scatter(
            x=df_sorted["date"], y=df_sorted["cum_bir"],
            name="BIRET", stackgroup="one",
            line=dict(color="#a78bfa"), fillcolor="rgba(167,139,250,0.35)"
        ))
        layout_cum = chart_layout("Cumulative Investment Over Time", height=280)
        layout_cum["yaxis"]["tickprefix"] = "₹"
        fig_cum.update_layout(**layout_cum)
        st.plotly_chart(fig_cum, use_container_width=True)
    else:
        st.info("No purchase history yet.")

with right:
    # Monthly spend bar chart
    if not purchases.empty:
        monthly = (purchases.groupby("month")
                   .agg(emb=("embassy_amt","sum"), bir=("biret_amt","sum"))
                   .reset_index())
        monthly["total"] = monthly["emb"] + monthly["bir"]

        fig_monthly = go.Figure()
        fig_monthly.add_trace(go.Bar(
            x=monthly["month"], y=monthly["emb"],
            name="EMBASSY", marker_color="#3b82f6"
        ))
        fig_monthly.add_trace(go.Bar(
            x=monthly["month"], y=monthly["bir"],
            name="BIRET", marker_color="#8b5cf6"
        ))
        fig_monthly.add_hline(y=5000, line_dash="dot", line_color="#f59e0b",
                               line_width=1.5, opacity=0.8, annotation_text="₹5000 cap")
        layout_m = chart_layout("Monthly Spend vs Cap", height=280)
        layout_m["yaxis"]["tickprefix"] = "₹"
        layout_m["barmode"] = "stack"
        fig_monthly.update_layout(**layout_m)
        st.plotly_chart(fig_monthly, use_container_width=True)
    else:
        st.info("No data yet.")


# ── Agent signal accuracy ──────────────────────────────────────────────────────
st.markdown('<div class="section-header">Agent Signal Stats</div>', unsafe_allow_html=True)

s1, s2, s3, s4 = st.columns(4)

if not purchases.empty:
    total_days   = len(purchases)
    actual_buys  = len(purchases[(purchases["embassy_amt"] > 0) | (purchases["biret_amt"] > 0)])
    actual_skips = total_days - actual_buys
    avg_per_buy  = (total_invested / actual_buys) if actual_buys > 0 else 0
    emb_share    = (total_emb_invested / total_invested * 100) if total_invested > 0 else 50
    bir_share    = 100 - emb_share
else:
    total_days = actual_buys = actual_skips = 0
    avg_per_buy = emb_share = 0
    bir_share = 0

with s1:
    st.markdown(f"""
    <div class="metric-card blue">
        <div class="metric-label">Total Signal Days</div>
        <div class="metric-value">{total_days}</div>
        <div class="metric-sub">Since agent started</div>
    </div>""", unsafe_allow_html=True)

with s2:
    rate = (actual_buys / total_days * 100) if total_days > 0 else 0
    st.markdown(f"""
    <div class="metric-card green">
        <div class="metric-label">Buy Rate</div>
        <div class="metric-value">{rate:.0f}%</div>
        <div class="metric-sub">{actual_buys} buys · {actual_skips} skips</div>
    </div>""", unsafe_allow_html=True)

with s3:
    st.markdown(f"""
    <div class="metric-card amber">
        <div class="metric-label">Avg Per Buy Day</div>
        <div class="metric-value">₹{avg_per_buy:,.0f}</div>
        <div class="metric-sub">Across all buy days</div>
    </div>""", unsafe_allow_html=True)

with s4:
    st.markdown(f"""
    <div class="metric-card purple">
        <div class="metric-label">Allocation Split</div>
        <div class="metric-value">{emb_share:.0f}/{bir_share:.0f}</div>
        <div class="metric-sub">EMBASSY / BIRET %</div>
    </div>""", unsafe_allow_html=True)


# ── Allocation pie chart ────────────────────────────────────────────────────────
if not purchases.empty and total_invested > 0:
    pie_col, trend_col = st.columns([1, 2])

    with pie_col:
        fig_pie = go.Figure(go.Pie(
            labels=["EMBASSY", "BIRET"],
            values=[total_emb_invested, total_bir_invested],
            hole=0.6,
            marker=dict(colors=["#3b82f6", "#8b5cf6"],
                        line=dict(color=CHART_BG, width=3)),
            textfont=dict(family=FONT_FAMILY, size=12),
            hovertemplate="<b>%{label}</b><br>₹%{value:,.0f}<br>%{percent}<extra></extra>"
        ))
        fig_pie.update_layout(
            plot_bgcolor=CHART_BG, paper_bgcolor=CHART_BG,
            height=260, margin=dict(l=0, r=0, t=40, b=0),
            title=dict(text="All-time allocation", font=dict(family="Syne", size=13, color="#8ba3cc")),
            legend=dict(font=dict(family=FONT_FAMILY, color=TEXT_COLOR), bgcolor="rgba(0,0,0,0)"),
            annotations=[dict(text=f"₹{total_invested:,.0f}", x=0.5, y=0.5,
                              font=dict(family="Syne", size=16, color="#f0f4ff"),
                              showarrow=False)]
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with trend_col:
        # Daily investment amounts over time
        df_bar = purchases.copy()
        df_bar["date"] = pd.to_datetime(df_bar["date"])
        fig_daily = go.Figure()
        fig_daily.add_trace(go.Bar(
            x=df_bar["date"], y=df_bar["embassy_amt"],
            name="EMBASSY", marker_color="#3b82f6", opacity=0.85
        ))
        fig_daily.add_trace(go.Bar(
            x=df_bar["date"], y=df_bar["biret_amt"],
            name="BIRET", marker_color="#8b5cf6", opacity=0.85
        ))
        layout_d = chart_layout("Daily Purchases", height=260)
        layout_d["yaxis"]["tickprefix"] = "₹"
        layout_d["barmode"] = "stack"
        fig_daily.update_layout(**layout_d)
        st.plotly_chart(fig_daily, use_container_width=True)


# ════════════════════════════════════════════════════════
#  SECTION 4 — TRANSACTION LOG
# ════════════════════════════════════════════════════════
st.markdown('<div class="section-header">Transaction Log</div>', unsafe_allow_html=True)

if not purchases.empty:
    df_display = purchases.copy()
    df_display["date"] = pd.to_datetime(df_display["date"]).dt.strftime("%d %b %Y")
    df_display = df_display.sort_values("date", ascending=False).head(20)

    for _, row in df_display.iterrows():
        e_amt = float(row["embassy_amt"])
        b_amt = float(row["biret_amt"])
        if e_amt == 0 and b_amt == 0:
            st.markdown(f"""
            <div class="tx-row">
                <span class="tx-date">{row['date']}</span>
                <span class="tx-skip">— skipped · no signal</span>
            </div>""", unsafe_allow_html=True)
        else:
            parts = []
            if e_amt > 0:
                units = e_amt / row["embassy_price"] if row["embassy_price"] > 0 else 0
                parts.append(f'<span class="tx-stock">EMBASSY</span>'
                             f'<span class="tx-amount">₹{e_amt:.0f}</span>'
                             f'<span class="tx-units">@ ₹{row["embassy_price"]:.2f} · {units:.3f} units</span>')
            if b_amt > 0:
                units = b_amt / row["biret_price"] if row["biret_price"] > 0 else 0
                parts.append(f'<span class="tx-stock">BIRET</span>'
                             f'<span class="tx-amount">₹{b_amt:.0f}</span>'
                             f'<span class="tx-units">@ ₹{row["biret_price"]:.2f} · {units:.3f} units</span>')

            total_day = e_amt + b_amt
            for p in parts:
                st.markdown(f"""
                <div class="tx-row">
                    <span class="tx-date">{row['date']}</span>
                    {p}
                    <span class="tx-units" style="margin-left:auto;color:#4b6cb7">₹{total_day:.0f} total</span>
                </div>""", unsafe_allow_html=True)
else:
    st.info("No transactions yet. The agent will start logging once you confirm your first purchase via Telegram.")


# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("<br><br>", unsafe_allow_html=True)
st.markdown("""
<div style="text-align:center; font-family:'DM Mono',monospace; font-size:11px; color:#2d3f5e; padding:20px 0;">
    REIT Agent · EMBASSY.NS · BIRET.NS · ₹5000/month SIP · Data via yFinance
</div>
""", unsafe_allow_html=True)