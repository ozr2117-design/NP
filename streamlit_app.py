import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
import pytz
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title="ETF 溢价实时监控",
    page_icon="📊",
    layout="wide"
)

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

# ===============================
# 4. 构建数据表 (计算实时预估估值)
# ===============================
def build_df(data_etf, data_market):
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

        rows.append({
            "代码":           item["code"],
            "名称":           tx.get("name") or item["short"],
            "分类":           item["category"],
            "最新价":         tx.get("current", 0),
            "估值(EST)":      est_iopv,
            "涨跌幅(%)":      tx.get("percent", 0),
            "实时溢价(EST)":  premium_rate,
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
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
body, .stApp { font-family: 'Inter', sans-serif; }
.main-title  { font-size:22px; font-weight:700; text-align:center; margin-bottom:4px; }
.subtitle    { font-size:12px; text-align:center; color:#888; margin-bottom:14px; }
.section-hdr { font-size:13px; font-weight:600; color:#555; margin:8px 0 6px 0; }
.badge-sp { display:inline-block; padding:2px 8px; border-radius:10px;
            background:#e8f0fe; color:#1a56db; font-size:11px; font-weight:700; }
.badge-nd { display:inline-block; padding:2px 8px; border-radius:10px;
            background:#fef3cd; color:#b45309; font-size:11px; font-weight:700; }
.stat-card {
    background: #f8f9fa; border-radius: 10px; padding: 8px 12px; min-width: 0;
}
.stat-label  { font-size: 10px; color: #888; margin-bottom: 1px; white-space: nowrap; }
.stat-value  { font-size: 11px; font-weight: 600; color: #1a1a1a;
               white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.stat-delta-up   { font-size: 11px; color: #d62728; margin-top:1px; }
.stat-delta-down { font-size: 11px; color: #2ca02c; margin-top:1px; }
.fut-box {
    background: #ffffff; border: 1px solid #eee; border-radius: 8px; padding: 6px 12px;
    display: flex; justify-content: space-between; align-items: center; height: 36px;
}
.fut-label { font-size: 11px; color: #666; font-weight: 600; }
.fut-price { font-size: 13px; font-weight: 700; color: #1a1a1a; margin: 0 8px; }
.fut-pct   { font-size: 12px; font-weight: 600; }
.fx-box {
    background: #fff5f5; border: 1px solid #ffdada; border-radius: 8px; padding: 4px 12px;
    display: flex; justify-content: center; align-items: center; margin-top: 6px;
}
.fx-label { font-size: 11px; color: #c53030; font-weight: 700; margin-right: 12px; }
.fx-price { font-size: 13px; font-weight: 700; color: #1a1a1a; margin-right: 8px; }
</style>
<div class='main-title'>📊 纳指 &amp; 标普 ETF 实时溢价监控</div>
""", unsafe_allow_html=True)

# ===============================
# 7. 获取数据与交易状态
# ===============================
trading  = is_trading_time()
data_etf = fetch_etf_data()
data_market = fetch_market_data()

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

# --- 市场行情栏 ---
c_f_left, c_f1, c_f2, c_f_right = st.columns([1, 4, 4, 1])
with c_f1:
    st.markdown(fut_html("NAS100 Fut", data_market.get("纳指期货")), unsafe_allow_html=True)
with c_f2:
    st.markdown(fut_html("SP500 Fut", data_market.get("标普期货")), unsafe_allow_html=True)
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

df = build_df(data_etf, data_market)

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

display_cols = ["代码", "名称", "分类", "最新价", "估值(EST)", "涨跌幅(%)", "实时溢价(EST)", "券商参考溢价", "资产净值"]

styled = df[display_cols].style \
    .applymap(color_premium,  subset=["实时溢价(EST)", "券商参考溢价"]) \
    .applymap(color_pct,      subset=["涨跌幅(%)"]) \
    .applymap(color_category, subset=["分类"]) \
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
# 10. 底栏
# ===============================
tz = pytz.timezone("Asia/Shanghai")
now_bj = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
st.caption(f"最后更新: {now_bj} (北京时间) · 每 10 秒自动刷新一次 (仅开盘期间)")

# ===============================
# 11. 底栏
# ===============================
