import streamlit as st
import pandas as pd
import requests
import time
import os
from datetime import datetime
import pytz
from streamlit_autorefresh import st_autorefresh
import plotly.graph_objects as go
import plotly.express as px
import warnings
warnings.filterwarnings('ignore')


st.set_page_config(
    page_title="SPX & NASDAQ",
    page_icon="📊",
    layout="wide"
)

# ===============================
# 0. 投资假设参数调节 (侧边栏)
# ===============================
st.sidebar.markdown("## ⚙️ 场内 vs 南向通 决策参数")
st.sidebar.info("南向通免溢价但有20%利润税和1.5%管理费。此工具计算在特定预期下，**场内ETF溢价达到多少时，买南向通更划算**。")

hold_time_options = {
    "1个月": 1/12, "3个月": 3/12, "半年": 0.5, "1年": 1.0, 
    "2年": 2.0, "3年": 3.0, "5年": 5.0, "10年": 10.0
}
hold_time_label = st.sidebar.select_slider("预期持有时间", options=list(hold_time_options.keys()), value="3个月")
T_years = hold_time_options[hold_time_label]

period_return = st.sidebar.slider("期间预期总收益率 (%)", min_value=-30, max_value=100, value=10, step=1) / 100.0
exp_sell_prem = st.sidebar.slider("预期卖出时的场内溢价率 (%)", min_value=-5, max_value=10, value=0, step=1) / 100.0

with st.sidebar.expander("高级费率设置"):
    m_dom = st.number_input("场内ETF年管理费+托管费(%)", value=0.6, step=0.1) / 100.0
    m_south = st.number_input("南向通年管理费(%)", value=1.5, step=0.1) / 100.0
    tax_rate = st.number_input("南向通利润税率(%)", value=20.0, step=1.0) / 100.0

# 将期间收益率转化为年化收益率，以保持费率复利计算的严谨性
exp_return = (1 + period_return) ** (1 / T_years) - 1 if T_years > 0 else 0

g_dom = (1 + exp_return - m_dom) ** T_years
g_south = (1 + exp_return - m_south) ** T_years
v_south_ratio = 1 + (1 - tax_rate) * (g_south - 1)
breakeven_prem_rate = ((1 + exp_sell_prem) * g_dom / v_south_ratio) - 1
breakeven_prem_pct = breakeven_prem_rate * 100

st.sidebar.markdown("---")
st.sidebar.markdown(f"""
<div style='background:#fef3cd; padding:10px; border-radius:8px;'>
    <div style='font-size:13px; color:#856404; margin-bottom:5px;'>💡 临界买入溢价率 (南向通等效溢价)</div>
    <div style='font-size:24px; font-weight:bold; color:#d97706;'>{breakeven_prem_pct:.2f}%</div>
    <div style='font-size:12px; color:#856404; margin-top:5px;'>
        若场内溢价 <b>≤ {breakeven_prem_pct:.2f}%</b>，买场内ETF<br>
        若场内溢价 <b>> {breakeven_prem_pct:.2f}%</b>，买南向通基金
    </div>
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown("---")
with st.sidebar.expander("📖 科学参数设置实战指南"):
    st.markdown("""
**🎯 武器库配置**
- **南方 I 类(021000)**：0溢价、免税、单日限购5K。定位：长线底仓“运兵车”。
- **南向通/场内 ETF**：高弹性、大额度。定位：波段套利“狙击枪”。

**🟢 状态0：大牛市 (安全/新高)**
- **特征**：距高点 -5% 以内。
- **操作**：按兵不动或佛系定投，让底仓利润奔跑。

**⚡ 场景1：单日闪电暴跌 (-1.5% 到 -2%)**
- **逻辑**：散户恐慌，次日易爆炒出极端溢价。
- **参数参考**：3个月持有 + 10%预期收益
- **操作**：若场内实际溢价达 6%-8%（超越临界值），**果断卖场内 ➡️ 大额买南向通**，瞬间无风险套利！顺手将 021000 的 5K 额度打满。

**⚠️ 场景2：正常回调区 (-5% 到 -10%)**
- **逻辑**：通常横盘震荡 1-2 个月，反弹空间不足以抵消南向通20%税率。
- **操作**：**021000 的绝对主战场**！只要场内溢价未超越临界值，就每天无脑拉满 5K 额度，零溢价免税吸筹。

**🔥 场景3：修正大跌 (-10% 到 -20%)**
- **逻辑**：修复期 0.5-1年，反弹空间极大，高收益足以覆盖南向通税费。
- **操作**：021000 继续每天 5K。伴随极度恐慌的 V 型底部时，**掏出重金用南向通一把梭哈**，吃到大反弹后撤退。

**🩸 场景4：熊市大底 (< -20%)**
- **逻辑**：漫长熊市(1-3年)，南向通长期持有的复利摩擦和高额税费会吞噬大量本金。
- **参数参考**：临界溢价率算出来通常高达 **12% 以上**！
- **操作**：不论当下溢价多高，**必须死磕买场内 ETF** 或雷打不动定投 021000，在绝望岁月里收集长线免税筹码。
""")

# ===============================
# 1. 监控 ETF 列表（含分类标记）
# ===============================
MONITOR_LIST = [
    # 纳指类
    {"code": "513100", "prefix": "sh", "short": "纳指ETF(华泰)",   "category": "纳指"},
    {"code": "159941", "prefix": "sz", "short": "纳指ETF(广发)",   "category": "纳指"},
    {"code": "513300", "prefix": "sh", "short": "纳指ETF(华夏)",   "category": "纳指"},
    {"code": "159659", "prefix": "sz", "short": "纳指100ETF",      "category": "纳指"},
    {"code": "159632", "prefix": "sz", "short": "纳指100ETF(国联)","category": "纳指"},
    # 标普类
    {"code": "513500", "prefix": "sh", "short": "标普ETF(易方达)", "category": "标普"},
    {"code": "159612", "prefix": "sz", "short": "标普ETF(南方)",   "category": "标普"},
    {"code": "159655", "prefix": "sz", "short": "标普ETF",          "category": "标普"},
    {"code": "513650", "prefix": "sh", "short": "标普ETF(汇添富)", "category": "标普"},
]

# ===============================
# 2. 开盘时间判断（北京时间）
# ===============================
def is_trading_time():
    tz = pytz.timezone("Asia/Shanghai")
    now = datetime.now(tz)
    if now.weekday() >= 5:      # 周六=5, 周日=6
        return False
    t = now.hour * 60 + now.minute
    morning   = (9 * 60 + 30) <= t <= (11 * 60 + 30)
    afternoon = (13 * 60)      <= t <= (15 * 60)
    return morning or afternoon

# ===============================
# 3. 数据获取（全量从腾讯财经获取，无需Cookie）
# ===============================
@st.cache_data(ttl=10)
def fetch_etf_data():
    """从腾讯接口读取 ETF 行情"""
    symbols = [f"{i['prefix']}{i['code']}" for i in MONITOR_LIST]
    url = f"http://qt.gtimg.cn/q={','.join(symbols)}"
    try:
        res = requests.get(url, timeout=5)
        text = res.content.decode("gbk")
        result = {}
        for line in text.split(";"):
            if "~" not in line or "=" not in line: continue
            try:
                code_match = line.split("=")[0].strip()[-6:]
                parts = line.split('"')[1].split("~")
                if len(parts) > 85:
                    curr = float(parts[3])
                    result[code_match] = {
                        "name":         parts[1],
                        "current":      curr,
                        "percent":      float(parts[32]),
                        "scale_yi":     float(parts[72]) / 100000000 if parts[72] else 0.0,
                        "t1_nav":       float(parts[78]) if parts[78] else curr,
                        "static_premium": float(parts[77]) if parts[77] else 0.0, # 腾讯原始溢价
                    }
            except: continue
        return result
    except: return {}

@st.cache_data(ttl=10)
def fetch_market_data():
    """从新浪接口读取美股期货与汇率数据"""
    symbols = "hf_NQ,hf_ES,fx_susdcnh"
    url = f"http://hq.sinajs.cn/list={symbols}"
    headers = {"Referer": "https://finance.sina.com.cn/"}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        result = {}
        for line in res.text.split(";"):
            if "=" not in line: continue
            try:
                name_key = line.split("=")[0].split("_")[-1]
                content = line.split('"')[1]
                parts = content.split(",")
                if "NQ" in name_key or "ES" in name_key: # 期货格式
                    name = "纳指期货" if "NQ" in name_key else "标普期货"
                    curr = float(parts[0])
                    prev = float(parts[7])
                    pct = ((curr / prev) - 1) * 100 if prev > 0 else 0
                    result[name] = {"current": curr, "percent": pct}
                elif "susdcnh" in name_key: # 汇率格式
                    curr = float(parts[1])
                    prev = float(parts[3])
                    pct = ((curr / prev) - 1) * 100 if prev > 0 else 0
                    result["USD/CNH"] = {"current": curr, "percent": pct}
            except: continue
        return result
    except: return {}

@st.cache_data(ttl=10, show_spinner=False)
def fetch_market_drawdown_data():
    """从腾讯接口读取纳指和标普的大盘水位（回撤数据）"""
    url = "http://qt.gtimg.cn/q=usNDX,usINX"
    try:
        res = requests.get(url, timeout=5)
        text = res.content.decode("gbk")
        result = {}
        for line in text.split(";"):
            if "~" not in line or "=" not in line: continue
            try:
                parts = line.split('"')[1].split("~")
                name = "纳指100" if "NDX" in line else "标普500"
                current = float(parts[3])
                ath = float(parts[48])  # 52周最高价
                if ath > 0 and current > 0:
                    drawdown = ((current / ath) - 1) * 100
                    result[name] = {"ath": ath, "current": current, "drawdown": drawdown}
            except: continue
        return result
    except Exception as e:
        print(f"Tencent Drawdown fetch error: {e}")
        return {}

# ===============================
# 3b. 历史折溢价率数据获取（缓存12小时）
# ===============================
@st.cache_data(ttl=43200, show_spinner=False)
def get_clean_premium_data(symbol: str, prefix: str = "sh"):
    """获取并清洗指定 ETF 过去一年的历史折溢价率数据。
    使用 ttl=43200 (12h) 缓存，避免重复调用 API。
    """
    import akshare as ak

    # ── 场内日线收盘价（新浪源，规避东方财富 IP 风控）──
    df_price = ak.fund_etf_hist_sina(symbol=f"{prefix}{symbol}")
    df_price = df_price[['date', 'close']]
    df_price['date'] = pd.to_datetime(df_price['date'])

    # 历史深度：近五年 (1825天) 或成立至今
    five_years_ago = pd.Timestamp.now() - pd.DateOffset(days=1825)
    df_price = df_price[df_price['date'] >= five_years_ago]

    time.sleep(0.5)   # 防反爬熔断

    # ── 基金净值（东方财富）──
    df_nav = ak.fund_open_fund_info_em(symbol=symbol, indicator="单位净值走势")
    df_nav = df_nav[['净值日期', '单位净值']].rename(
        columns={'净值日期': 'date', '单位净值': 'nav'}
    )
    df_nav['date'] = pd.to_datetime(df_nav['date'])
    df_nav['nav'] = pd.to_numeric(df_nav['nav'], errors='coerce')

    # ── QDII 时差对齐：T日价格 对齐 T-1日净值 ──
    df_nav = df_nav.sort_values('date')
    df_nav['nav_shifted'] = df_nav['nav'].shift(1)
    df_nav['nav_date']    = df_nav['date'].shift(1)

    df = pd.merge(
        df_price,
        df_nav[['date', 'nav_shifted', 'nav_date']],
        on='date', how='left'
    )
    df['nav_shifted'] = df['nav_shifted'].ffill()
    df['nav_date']    = df['nav_date'].ffill()
    df = df.dropna(subset=['nav_shifted', 'nav_date', 'close'])

    df['premium_rate'] = (df['close'] - df['nav_shifted']) / df['nav_shifted'] * 100

    # 暴力剔除接口故障脏数据
    df = df[(df['premium_rate'] <= 15) & (df['premium_rate'] >= -15)]

    # ── 数据质量双重拦截 ──
    df['date_diff'] = (df['date'] - df['nav_date']).dt.days
    df = df[df['date_diff'] <= 4]

    if not df.empty:
        latest = df.iloc[-1]
        if latest['date'].dayofweek in [1, 2, 3, 4] and latest['date_diff'] > 1:
            df = df.iloc[:-1]

    return df


def plot_premium_chart(df: pd.DataFrame, etf_name: str, etf_code: str):
    """根据清洗后的 DataFrame 使用 Plotly 绘制互动式折溢价率走势图。
    Plotly 在浏览器端渲染，能完美支持中文显示。
    """
    fig = go.Figure()

    # 1. 绘制溢价区域 (填充红色)
    df_premium = df.copy()
    df_premium.loc[df_premium['premium_rate'] < 0, 'premium_rate'] = 0
    fig.add_trace(go.Scatter(
        x=df_premium['date'], y=df_premium['premium_rate'],
        fill='tozeroy', fillcolor='rgba(255, 205, 210, 0.5)',
        line=dict(color='#ef4444', width=0),
        name='溢价', hoverinfo='skip'
    ))

    # 2. 绘制折价区域 (填充绿色)
    df_discount = df.copy()
    df_discount.loc[df_discount['premium_rate'] > 0, 'premium_rate'] = 0
    fig.add_trace(go.Scatter(
        x=df_discount['date'], y=df_discount['premium_rate'],
        fill='tozeroy', fillcolor='rgba(200, 230, 201, 0.5)',
        line=dict(color='#2ca02c', width=0),
        name='折价', hoverinfo='skip'
    ))

    # 3. 绘制主线
    fig.add_trace(go.Scatter(
        x=df['date'], y=df['premium_rate'],
        mode='lines',
        line=dict(color='#4CAF50', width=1.8),
        name='折溢价率 (%)',
        hovertemplate='%{x|%Y-%m-%d}<br>折溢价率: %{y:.2f}%<extra></extra>'
    ))

    # 4. 绘制0轴基准线
    fig.add_shape(
        type="line", x0=df['date'].min(), x1=df['date'].max(), y0=0, y1=0,
        line=dict(color="red", width=1.5, dash="dash"),
    )

    # 5. 布局优化
    fig.update_layout(
        title=dict(
            text=f"{etf_code} ({etf_name}) 历史真实折溢价率走势 (近五年或成立至今)",
            x=0.5, xanchor='center', font=dict(size=16)
        ),
        xaxis=dict(
            title="交易日期", showgrid=True, gridcolor='rgba(0,0,0,0.05)', tickformat='%Y-%m-%d',
            rangeselector=dict(
                buttons=list([
                    dict(count=1, label="1年", step="year", stepmode="backward"),
                    dict(count=2, label="2年", step="year", stepmode="backward"),
                    dict(step="all", label="全部")
                ]),
                font=dict(size=11),
                x=0, y=1.05
            ),
            rangeslider=dict(visible=True, thickness=0.05),
            type="date"
        ),
        yaxis=dict(title="折溢价率 (%)", showgrid=True, gridcolor='rgba(0,0,0,0.05)'),
        hovermode="x unified",
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=40, r=40, t=80, b=40),
        height=500,
        showlegend=False
    )
    
    # 默认展示最近 1 年 (365天)，用户可通过按钮切换到 2 年
    one_year_ago_date = df['date'].max() - pd.DateOffset(days=365)
    fig.update_xaxes(range=[one_year_ago_date, df['date'].max()])

    return fig


# ===============================
# 4. 构建数据表 (计算实时预估估值)
# ===============================
def build_df(data_etf, data_market, breakeven_prem_pct):
    rows = []
    
    # 提取市场因子 (百分比)
    nq_pct = data_market.get("纳指期货", {}).get("percent", 0.0)
    es_pct = data_market.get("标普期货", {}).get("percent", 0.0)
    fx_pct = data_market.get("USD/CNH", {}).get("percent", 0.0)

    for item in MONITOR_LIST:
        tx = data_etf.get(item["code"], {})
        if not tx: continue

        # --- 实时估值核心算法 ---
        # 实时估值 = 昨收净值 * (1 + 指数波幅 + 汇率波幅)
        futures_pct = nq_pct if item["category"] == "纳指" else es_pct
        est_iopv = tx["t1_nav"] * (1 + (futures_pct + fx_pct) / 100)
        premium_rate = (tx["current"] / est_iopv - 1) * 100 if est_iopv > 0 else 0.0

        advise = "💎场内" if premium_rate <= breakeven_prem_pct else "✈️南向通"

        rows.append({
            "代码":           item["code"],
            "名称":           tx.get("name") or item["short"],
            "分类":           item["category"],
            "最新价":         tx.get("current", 0),
            "估值(EST)":      est_iopv,
            "涨跌幅(%)":      tx.get("percent", 0),
            "实时溢价(EST)":  premium_rate,
            "最优渠道":       advise,
            "券商参考溢价":    tx.get("static_premium", 0.0),
            "资产净值":       tx.get("scale_yi", 0),
        })

    df = pd.DataFrame(rows)
    if df.empty: return df

    # 分类排序：先标普后纳指，各自内部按溢价率从低到高
    sp_df = df[df["分类"] == "标普"].sort_values("实时溢价(EST)", ascending=True, na_position="last")
    nd_df = df[df["分类"] == "纳指"].sort_values("实时溢价(EST)", ascending=True, na_position="last")
    return pd.concat([sp_df, nd_df]).reset_index(drop=True)

# ===============================
# 5. 页面样式
# ===============================
st.markdown("""
<style>
body, .stApp { 
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background-color: #fbfbfd;
}
.main-title  { font-size:24px; font-weight:700; letter-spacing:-0.5px; text-align:center; margin-bottom:4px; color:#1d1d1f; }
.subtitle    { font-size:12px; text-align:center; color:#86868b; margin-bottom:14px; }
.section-hdr { font-size:14px; font-weight:600; color:#1d1d1f; margin:12px 0 8px 0; letter-spacing:-0.3px; }
.badge-sp { display:inline-block; padding:3px 10px; border-radius:12px;
            background:#f0f4ff; color:#0066cc; font-size:11px; font-weight:600; }
.badge-nd { display:inline-block; padding:3px 10px; border-radius:12px;
            background:#fff7e6; color:#d97706; font-size:11px; font-weight:600; }
.stat-card {
    background: #ffffff; 
    border-radius: 14px; 
    padding: 10px 14px; 
    min-width: 0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    border: 1px solid rgba(0,0,0,0.02);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.stat-card:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}
.stat-label  { font-size: 11px; color: #86868b; margin-bottom: 2px; white-space: nowrap; font-weight: 500; }
.stat-value  { font-size: 13px; font-weight: 600; color: #1d1d1f;
               white-space: nowrap; overflow: hidden; text-overflow: ellipsis; letter-spacing: -0.2px; }
.stat-delta-up   { font-size: 12px; font-weight: 500; color: #ff3b30; margin-top:2px; }
.stat-delta-down { font-size: 12px; font-weight: 500; color: #34c759; margin-top:2px; }
.fut-box {
    background: #ffffff; 
    border-radius: 14px; 
    padding: 8px 16px;
    display: flex; justify-content: space-between; align-items: center; height: 42px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    border: 1px solid rgba(0,0,0,0.02);
}
.fut-label { font-size: 12px; color: #86868b; font-weight: 500; }
.fut-price { font-size: 14px; font-weight: 600; color: #1d1d1f; margin: 0 10px; letter-spacing: -0.3px; }
.fut-pct   { font-size: 13px; font-weight: 600; }
.fx-box {
    background: rgba(255, 59, 48, 0.05); 
    border-radius: 12px; 
    padding: 6px 14px;
    display: flex; justify-content: center; align-items: center; margin-top: 0px;
    border: 1px solid rgba(255, 59, 48, 0.1);
}
.fx-label { font-size: 12px; color: #ff3b30; font-weight: 600; margin-right: 12px; letter-spacing: -0.2px; }
.fx-price { font-size: 14px; font-weight: 600; color: #1d1d1f; margin-right: 8px; }
</style>
<div class='main-title'>📊 SPX &amp; NASDAQ</div>
""", unsafe_allow_html=True)

# ===============================
# 7. 获取数据与交易状态
# ===============================
trading  = is_trading_time()
data_etf = fetch_etf_data()
data_market = fetch_market_data()
data_drawdown = fetch_market_drawdown_data()

if not data_drawdown:
    # 若拉取失败，则清除空缓存，避免接下来 12 小时都拉不到数据
    fetch_market_drawdown_data.clear()

if not data_etf:
    st.error("数据加载失败，请检查网络。(Tencent API Error)")
    st.stop()

def fut_html(name, data):
    if not data: return ""
    color = "#d62728" if data['percent'] >= 0 else "#2ca02c"
    pm    = "+" if data['percent'] >= 0 else ""
    return f"""
    <div class='fut-box'>
        <span class='fut-label'>{name}</span>
        <span class='fut-price'>{data['current']:.2f}</span>
        <span class='fut-pct' style='color:{color}'>{pm}{data['percent']:.2f}%</span>
    </div>"""

def fx_html(data):
    if not data: return ""
    color = "#d62728" if data['percent'] >= 0 else "#2ca02c"
    pm    = "+" if data['percent'] >= 0 else ""
    return f"""
    <div class='fx-box'>
        <span class='fx-label'>USD/CNH 离岸汇率</span>
        <span class='fx-price'>{data['current']:.4f}</span>
        <span class='fut-pct' style='color:{color}'>{pm}{data['percent']:.2f}%</span>
    </div>"""

def drawdown_html(name, data, daily_pct=0.0):
    if not data: 
        return f"<div style='font-size:11px; color:#888; margin-top:8px;'>⚠️ {name} 雷达数据拉取超时，请稍后刷新重试...</div>"
    
    dd = float(data['drawdown'])
    
    # 判定状态
    if dd <= -20:
        state = "🩸 熊市 (超跌)"
        bg = "#7f1d1d"; tc = "#fecaca"; border = "#ef4444"; icon = "🚨 极度恐慌"
    elif dd <= -10:
        state = "🔥 修正 (大跌)"
        bg = "#fff7ed"; tc = "#c2410c"; border = "#fdba74"; icon = "💡 南向通抄底窗口"
    elif dd <= -5:
        state = "⚠️ 回调 (Pullback)"
        bg = "#fefce8"; tc = "#a16207"; border = "#fef08a"; icon = "👀 观察期"
    else:
        state = "✅ 安全 (震荡/新高)"
        bg = "#f0fdf4"; tc = "#15803d"; border = "#bbf7d0"; icon = "💎 定投场内"

    alert_html = ""
    if daily_pct <= -1.5:
        alert_html = f"<div style='margin-top:8px; padding:4px 6px; background:#fee2e2; border-left:3px solid #dc2626; border-radius:4px; animation: pulse 2s infinite;'><span style='font-size:11px; font-weight:700; color:#991b1b;'>⚡ 单日暴跌 {daily_pct:.2f}%：留意极高溢价套利！</span></div>"

    return f"""
    <style>
    @keyframes pulse {{
        0% {{ box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.4); }}
        70% {{ box-shadow: 0 0 0 4px rgba(220, 38, 38, 0); }}
        100% {{ box-shadow: 0 0 0 0 rgba(220, 38, 38, 0); }}
    }}
    </style>
    <div style='background:{bg}; border:1px solid {border}; border-radius:8px; padding:8px 12px; margin-top:8px; display:flex; flex-direction:column; justify-content:center;'>
        <div style='display:flex; justify-content:space-between; align-items:center;'>
            <span style='font-size:12px; font-weight:700; color:{tc};'>{name} 水位雷达</span>
            <span style='font-size:11px; font-weight:600; color:{tc};'>{icon}</span>
        </div>
        <div style='margin-top:4px; display:flex; align-items:baseline;'>
            <span style='font-size:18px; font-weight:bold; color:{tc};'>{dd:+.2f}%</span>
            <span style='font-size:11px; color:{tc}; margin-left:6px; opacity:0.8;'>(距历史最高点)</span>
        </div>
        <div style='font-size:12px; font-weight:700; color:{tc}; margin-top:2px;'>状态：{state}</div>
        {alert_html}
    </div>
    """

# --- 市场行情栏 ---
c_f_left, c_f1, c_f2, c_f_right = st.columns([1, 4, 4, 1])
with c_f1:
    ndx_fut = data_market.get("纳指期货")
    st.markdown(fut_html("NAS100 Fut", ndx_fut), unsafe_allow_html=True)
    ndx_pct = ndx_fut['percent'] if ndx_fut else 0.0
    st.markdown(drawdown_html("纳指100", data_drawdown.get("纳指100"), ndx_pct), unsafe_allow_html=True)
with c_f2:
    spx_fut = data_market.get("标普期货")
    st.markdown(fut_html("SP500 Fut", spx_fut), unsafe_allow_html=True)
    spx_pct = spx_fut['percent'] if spx_fut else 0.0
    st.markdown(drawdown_html("标普500", data_drawdown.get("标普500"), spx_pct), unsafe_allow_html=True)

# --- 交易状态 & 自动刷新 (中置显示预留) ---
tz = pytz.timezone("Asia/Shanghai")
now_obj = datetime.now(tz)
now_str = now_obj.strftime("%H:%M:%S")

if trading:
    # 核心刷新逻辑：仅在交易时段触发 10s 刷新
    st_autorefresh(interval=10000, key="data_refresh")

# --- USD/CNH 汇率栏 (新增) ---
_, c_fx, _ = st.columns([1, 8, 1])
with c_fx:
    st.markdown(fx_html(data_market.get("USD/CNH")), unsafe_allow_html=True)

df = build_df(data_etf, data_market, breakeven_prem_pct)

# --- 情绪指数判定 (基于实时溢价 EST) ---
emotion_badge = ""
if not df.empty:
    min_p = df["实时溢价(EST)"].min()
    max_p = df["实时溢价(EST)"].max()
    
    if min_p < 0:
        emotion_badge = "<span style='margin-left:12px; padding:2px 8px; background:#ef4444; color:#fff; border-radius:4px; font-size:12px;'>🔥 情绪：恐慌（建议成交，坚定买入）</span>"
    elif min_p < 1 or (min_p >= 1 and max_p <= 2):
        emotion_badge = "<span style='margin-left:12px; padding:2px 8px; background:#f97316; color:#fff; border-radius:4px; font-size:12px;'>💎 情绪：比较恐慌（建议成交，适当加仓）</span>"

# 渲染居中状态栏
st_color = "#1a56db" if trading else "#ef4444"
st_txt   = "🕒 刷新中" if trading else "🔴 休市中"
status_html = f"""
    <div style='display:flex; justify-content:center; align-items:center; font-size:13px; font-weight:700; margin: 8px 0;'>
        <span style='color:{st_color};'>{st_txt} | {now_str}</span>
        {emotion_badge}
    </div>
"""
st.markdown(status_html, unsafe_allow_html=True)

if df.empty:
    st.warning("暂无数据，请稍后检查网络或接口状态。")
    st.stop()

sp_valid = df[(df["分类"] == "标普") & (df["实时溢价(EST)"] != 0)]
nd_valid = df[(df["分类"] == "纳指") & (df["实时溢价(EST)"] != 0)]

# ===============================
# 8. 统计卡片 (自定义小型)
# ===============================
def delta_html(pct):
    arrow = "↑" if pct >= 0 else "↓"
    cls   = "stat-delta-up" if pct >= 0 else "stat-delta-down"
    return f"<div class='{cls}'>{arrow} {pct:+.2f}%</div>"

def stat_card(label, code_short, pct):
    return f"""
    <div class='stat-card'>
        <div class='stat-label'>{label}</div>
        <div class='stat-value' title='{code_short}'>{code_short}</div>
        {delta_html(pct)}
    </div>"""

def avg_card(label, pct):
    arrow = "↑" if pct >= 0 else "↓"
    color = "#d62728" if pct >= 0 else "#2ca02c"
    return f"""
    <div class='stat-card'>
        <div class='stat-label'>{label}</div>
        <div style='font-size:15px;font-weight:700;color:{color};margin-top:4px;'>{arrow} {pct:+.2f}%</div>
    </div>"""

# --- 标普 ---
st.markdown("<div class='section-hdr'><span class='badge-sp'>标普 S&P</span></div>", unsafe_allow_html=True)
if not sp_valid.empty:
    sp_max = sp_valid.loc[sp_valid["实时溢价(EST)"].idxmax()]
    sp_min = sp_valid.loc[sp_valid["实时溢价(EST)"].idxmin()]
    sp_avg = sp_valid["实时溢价(EST)"].mean()
    c1, c2, c3 = st.columns(3)
    with c1: st.markdown(stat_card("溢价最高", sp_max["名称"], sp_max["实时溢价(EST)"]), unsafe_allow_html=True)
    with c2: st.markdown(stat_card("溢价最低", sp_min["名称"], sp_min["实时溢价(EST)"]), unsafe_allow_html=True)
    with c3: st.markdown(avg_card("平均溢价率", sp_avg), unsafe_allow_html=True)

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# --- 纳指 ---
st.markdown("<div class='section-hdr'><span class='badge-nd'>纳指 NASDAQ</span></div>", unsafe_allow_html=True)
if not nd_valid.empty:
    nd_max = nd_valid.loc[nd_valid["实时溢价(EST)"].idxmax()]
    nd_min = nd_valid.loc[nd_valid["实时溢价(EST)"].idxmin()]
    nd_avg = nd_valid["实时溢价(EST)"].mean()
    c4, c5, c6 = st.columns(3)
    with c4: st.markdown(stat_card("溢价最高", nd_max["名称"], nd_max["实时溢价(EST)"]), unsafe_allow_html=True)
    with c5: st.markdown(stat_card("溢价最低", nd_min["名称"], nd_min["实时溢价(EST)"]), unsafe_allow_html=True)
    with c6: st.markdown(avg_card("平均溢价率", nd_avg), unsafe_allow_html=True)

st.divider()

# ===============================
# 9. 数据表
# ===============================
def color_premium(val):
    try:
        v = float(val)
        if v < 0:   return "background-color:#ff4d4d;color:white;font-weight:bold"
        elif v < 2: return "background-color:#ffcccc"
        else:       return "background-color:#ccffcc"
    except: return ""

def color_pct(val):
    try: return "color:#d62728" if float(val) > 0 else "color:#2ca02c"
    except: return ""

def color_category(val):
    if val == "标普":   return "color:#1a56db;font-weight:600"
    elif val == "纳指": return "color:#b45309;font-weight:600"
    return ""

def color_advise(val):
    if "场内" in val: return "background-color:#e8f0fe;color:#1a56db;font-weight:bold"
    if "南向通" in val: return "background-color:#ffeedd;color:#d97706;font-weight:bold"
    return ""

display_cols = ["代码", "名称", "分类", "最新价", "估值(EST)", "涨跌幅(%)", "实时溢价(EST)", "最优渠道", "券商参考溢价", "资产净值"]

styled = df[display_cols].style \
    .map(color_premium,  subset=["实时溢价(EST)", "券商参考溢价"]) \
    .map(color_pct,      subset=["涨跌幅(%)"]) \
    .map(color_category, subset=["分类"]) \
    .map(color_advise,   subset=["最优渠道"]) \
    .format({
        "最新价":         "{:.3f}",
        "估值(EST)":      "{:.3f}",
        "涨跌幅(%)":      "{:+.2f}%",
        "实时溢价(EST)":  "{:+.2f}%",
        "券商参考溢价":    "{:+.2f}%",
        "资产净值":       "{:.2f} 亿",
    })

st.dataframe(styled, use_container_width=True, hide_index=True)

# ===============================
# 9b. 历史折溢价走势图（懒加载）
# ===============================
st.markdown("---")
st.markdown("""
<div style='font-size:15px; font-weight:700; margin-bottom:10px;'>
    📈 历史折溢价率走势图（阅表顺序·点击展开后手动加载，避免卡顿）
</div>
""", unsafe_allow_html=True)

# expander 顺序跟随表格排序（df 已按标普/纳指分组、各组内按溢价率升序排列）
_monitor_dict = {item["code"]: item for item in MONITOR_LIST}

for _, row in df.iterrows():
    etf_code   = row["代码"]
    etf_name   = row["名称"]
    item       = _monitor_dict.get(etf_code)
    if not item:
        continue
    etf_prefix = item["prefix"]

    with st.expander(f"📊 查看 {etf_name} ({etf_code}) 历史折溢价走势"):
        btn_key = f"load_chart_{etf_code}"
        if st.button("加载走势图", key=btn_key):
            with st.spinner(f"正在获取 {etf_code} 的历史数据（首次约需 5–10 秒，之后命中缓存秒开）..."):
                try:
                    df_hist = get_clean_premium_data(etf_code, etf_prefix)
                    if df_hist.empty:
                        st.warning(f"{etf_code} 暂无可用历史净值数据，请稍后再试。")
                    else:
                        fig = plot_premium_chart(df_hist, etf_name, etf_code)
                        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                        latest_premium = df_hist['premium_rate'].iloc[-1]
                        avg_premium    = df_hist['premium_rate'].mean()
                        max_premium    = df_hist['premium_rate'].max()
                        min_premium    = df_hist['premium_rate'].min()
                        c_s1, c_s2, c_s3, c_s4 = st.columns(4)
                        c_s1.metric("最新折溢价率", f"{latest_premium:+.2f}%")
                        c_s2.metric("历史平均值",   f"{avg_premium:+.2f}%")
                        c_s3.metric("历史最高值",   f"{max_premium:+.2f}%")
                        c_s4.metric("历史最低值",   f"{min_premium:+.2f}%")
                except Exception as e:
                    st.error(f"数据获取失败：{e}")

# ===============================
# 10. 底栏
# ===============================
tz = pytz.timezone("Asia/Shanghai")
now_bj = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
st.caption(f"最后更新: {now_bj} (北京时间) · 每 10 秒自动刷新一次 (仅开盘期间)")

# ===============================
# 11. 底栏
# ===============================
