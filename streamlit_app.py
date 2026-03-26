import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
import pytz

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
    {"code": "513100", "xq_sym": "SH513100", "short": "纳指ETF(华泰)",   "category": "纳指"},
    {"code": "159941", "xq_sym": "SZ159941", "short": "纳指ETF(广发)",   "category": "纳指"},
    {"code": "513300", "xq_sym": "SH513300", "short": "纳指ETF(华夏)",   "category": "纳指"},
    {"code": "159659", "xq_sym": "SZ159659", "short": "纳指100ETF",      "category": "纳指"},
    {"code": "159632", "xq_sym": "SZ159632", "short": "纳指100ETF(国联)","category": "纳指"},
    # 标普类
    {"code": "513500", "xq_sym": "SH513500", "short": "标普ETF(易方达)", "category": "标普"},
    {"code": "159612", "xq_sym": "SZ159612", "short": "标普ETF(南方)",   "category": "标普"},
    {"code": "159655", "xq_sym": "SZ159655", "short": "标普ETF",          "category": "标普"},
    {"code": "513650", "xq_sym": "SH513650", "short": "标普ETF(汇添富)", "category": "标普"},
]

# ===============================
# 2. 从 st.secrets 中读取 Cookie
# ===============================
try:
    XUEQIU_COOKIE = st.secrets["XUEQIU_COOKIE"]
except Exception:
    st.error("请在 Streamlit Secrets 中配置 XUEQIU_COOKIE")
    st.stop()

# ===============================
# 3. 开盘时间判断（北京时间）
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
# 4. 数据获取（批量 quote）
#    market_cap 字段 = 总市值（元），即 总份额 × 最新价
#    对 ETF 而言即基金规模，换算成亿元展示
# ===============================
@st.cache_data(ttl=15)
def fetch_xueqiu_data():
    symbols = ",".join([item["xq_sym"] for item in MONITOR_LIST])
    url = f"https://stock.xueqiu.com/v5/stock/batch/quote.json?symbol={symbols}&extend=detail"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://xueqiu.com",
        "Cookie": XUEQIU_COOKIE,
    }
    try:
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code != 200:
            return None, f"雪球接口返回 {res.status_code}"
        items = res.json().get("data", {}).get("items", [])
        result = {}
        for item in items:
            q = item.get("quote", {})
            sym = q.get("symbol")
            # market_cap 单位：元；/1e8 → 亿元
            mc = q.get("market_cap")
            scale_yi = round(mc / 1e8, 2) if mc else None
            result[sym] = {
                "current":      q.get("current", 0),
                "last_close":   q.get("last_close", 0),
                "iopv":         q.get("iopv"),
                "premium_rate": q.get("premium_rate"),
                "percent":      q.get("percent", 0),
                "name":         q.get("name", ""),   # 雪球ETF全称
                "scale_yi":     scale_yi,             # 基金规模（亿元）
            }
        return result, None
    except Exception as e:
        return None, str(e)

# ===============================
# 5. 构建数据表
# ===============================
def build_df(data):
    rows = []
    for item in MONITOR_LIST:
        xq        = data.get(item["xq_sym"], {})
        current   = xq.get("current", 0)
        iopv      = xq.get("iopv")
        premium   = xq.get("premium_rate")
        pct       = xq.get("percent", 0)
        full_name = xq.get("name") or item["short"]
        scale_yi  = xq.get("scale_yi")

        if iopv and current and iopv > 0:
            premium_calc = round(((current / iopv) - 1) * 100, 2)
        elif premium is not None:
            premium_calc = round(float(premium), 2)
        else:
            premium_calc = None

        rows.append({
            "代码":       item["code"],
            "简称":       item["short"],
            "名称":       full_name,
            "分类":       item["category"],
            "最新价":     current,
            "IOPV":       round(iopv, 4) if iopv else None,
            "规模(亿元)": scale_yi,
            "涨跌幅(%)":  pct,
            "溢价率(%)":  premium_calc,
        })

    df = pd.DataFrame(rows)

    # 分类排序：先标普后纳指，各自内部按溢价率从低到高
    sp_df = df[df["分类"] == "标普"].sort_values("溢价率(%)", ascending=True, na_position="last")
    nd_df = df[df["分类"] == "纳指"].sort_values("溢价率(%)", ascending=True, na_position="last")
    return pd.concat([sp_df, nd_df]).reset_index(drop=True)

# ===============================
# 6. 页面样式（含自定义卡片样式）
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
/* 自定义小型统计卡片 */
.stat-card {
    background: #f8f9fa;
    border-radius: 10px;
    padding: 10px 14px;
    min-width: 0;
}
.stat-label  { font-size: 11px; color: #888; margin-bottom: 2px; white-space: nowrap; }
.stat-value  { font-size: 13px; font-weight: 600; color: #1a1a1a;
               white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.stat-delta-up   { font-size: 12px; color: #d62728; margin-top:2px; }
.stat-delta-down { font-size: 12px; color: #2ca02c; margin-top:2px; }
.stat-delta-avg  { font-size: 14px; font-weight:700; color: #d62728; margin-top:2px; }
.closed-banner {
    text-align:center; padding:10px 0; font-size:13px;
    color:#888; background:#f5f5f5; border-radius:8px; margin-bottom:12px;
}
</style>
<div class='main-title'>📊 纳指 &amp; 标普 ETF 实时溢价监控</div>
<div class='subtitle'>数据源：雪球财经</div>
""", unsafe_allow_html=True)

# ===============================
# 7. 刷新按钮 & 开盘状态
# ===============================
trading = is_trading_time()

col_btn1, col_btn2, col_btn3 = st.columns([2, 1, 2])
with col_btn2:
    refresh = st.button("🔄 立即刷新", use_container_width=True)
if refresh:
    st.cache_data.clear()
    st.rerun()

if not trading:
    tz = pytz.timezone("Asia/Shanghai")
    now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    st.markdown(f"""
    <div class='closed-banner'>🔴 <b>休市中</b>（{now_str} 北京时间）&nbsp;·&nbsp;开盘时段：09:30–11:30 / 13:00–15:00（周一至周五）</div>
    """, unsafe_allow_html=True)

# ===============================
# 8. 获取数据
# ===============================
data, err = fetch_xueqiu_data()

if err or not data:
    st.error(f"数据获取失败：{err}")
    st.info("可能是 Cookie 已过期，请重新抓取雪球 Cookie 并在 Streamlit Secrets 中更新 XUEQIU_COOKIE。")
    st.stop()

df = build_df(data)

sp_valid = df[(df["分类"] == "标普") & df["溢价率(%)"].notna()]
nd_valid = df[(df["分类"] == "纳指") & df["溢价率(%)"].notna()]

# ===============================
# 9. 自定义小型统计卡片
# ===============================
def delta_html(pct, cls_extra=""):
    arrow = "↑" if pct >= 0 else "↓"
    cls   = "stat-delta-up" if pct >= 0 else "stat-delta-down"
    if cls_extra:
        cls = cls_extra
    return f"<div class='{cls}'>{arrow} {pct:+.2f}%</div>"

def stat_card(label, code_short, pct):
    delta = delta_html(pct)
    return f"""
    <div class='stat-card'>
        <div class='stat-label'>{label}</div>
        <div class='stat-value' title='{code_short}'>{code_short}</div>
        {delta}
    </div>"""

def avg_card(label, pct):
    arrow = "↑" if pct >= 0 else "↓"
    color = "#d62728" if pct >= 0 else "#2ca02c"
    return f"""
    <div class='stat-card'>
        <div class='stat-label'>{label}</div>
        <div style='font-size:16px;font-weight:700;color:{color};margin-top:4px;'>{arrow} {pct:+.2f}%</div>
    </div>"""

# --- 标普卡片 ---
st.markdown("<div class='section-hdr'><span class='badge-sp'>标普 S&P</span></div>", unsafe_allow_html=True)
if not sp_valid.empty:
    sp_max = sp_valid.loc[sp_valid["溢价率(%)"].idxmax()]
    sp_min = sp_valid.loc[sp_valid["溢价率(%)"].idxmin()]
    sp_avg = sp_valid["溢价率(%)"].mean()
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(stat_card("溢价最高",
            f"{sp_max['代码']} {sp_max['简称']}", sp_max["溢价率(%)"]),
            unsafe_allow_html=True)
    with c2:
        st.markdown(stat_card("溢价最低",
            f"{sp_min['代码']} {sp_min['简称']}", sp_min["溢价率(%)"]),
            unsafe_allow_html=True)
    with c3:
        st.markdown(avg_card("平均溢价率 (标普)", sp_avg), unsafe_allow_html=True)

st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

# --- 纳指卡片 ---
st.markdown("<div class='section-hdr'><span class='badge-nd'>纳指 NASDAQ</span></div>", unsafe_allow_html=True)
if not nd_valid.empty:
    nd_max = nd_valid.loc[nd_valid["溢价率(%)"].idxmax()]
    nd_min = nd_valid.loc[nd_valid["溢价率(%)"].idxmin()]
    nd_avg = nd_valid["溢价率(%)"].mean()
    c4, c5, c6 = st.columns(3)
    with c4:
        st.markdown(stat_card("溢价最高",
            f"{nd_max['代码']} {nd_max['简称']}", nd_max["溢价率(%)"]),
            unsafe_allow_html=True)
    with c5:
        st.markdown(stat_card("溢价最低",
            f"{nd_min['代码']} {nd_min['简称']}", nd_min["溢价率(%)"]),
            unsafe_allow_html=True)
    with c6:
        st.markdown(avg_card("平均溢价率 (纳指)", nd_avg), unsafe_allow_html=True)

st.divider()

# ===============================
# 10. 数据表
# ===============================
def color_premium(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    try:
        v = float(val)
        if v > 2:   return "background-color:#ff4d4d;color:white;font-weight:bold"
        elif v > 0: return "background-color:#ffcccc"
        elif v < 0: return "background-color:#ccffcc"
        return ""
    except:
        return ""

def color_pct(val):
    try:
        return "color:#d62728" if float(val) > 0 else "color:#2ca02c"
    except:
        return ""

def color_category(val):
    if val == "标普":   return "color:#1a56db;font-weight:600"
    elif val == "纳指": return "color:#b45309;font-weight:600"
    return ""

display_cols = ["代码", "简称", "名称", "分类", "最新价", "IOPV", "规模(亿元)", "涨跌幅(%)", "溢价率(%)"]

styled = df[display_cols].style \
    .applymap(color_premium,  subset=["溢价率(%)"]) \
    .applymap(color_pct,      subset=["涨跌幅(%)"]) \
    .applymap(color_category, subset=["分类"]) \
    .format({
        "最新价":     "{:.3f}",
        "IOPV":       lambda x: f"{x:.4f}" if isinstance(x, (int, float)) and not pd.isna(x) else "-",
        "规模(亿元)": lambda x: f"{x:.2f}" if isinstance(x, (int, float)) and not pd.isna(x) else "-",
        "涨跌幅(%)":  "{:+.2f}%",
        "溢价率(%)":  lambda x: f"{x:+.2f}%" if isinstance(x, (int, float)) and not pd.isna(x) else "-",
    })

st.dataframe(styled, use_container_width=True, height=400, hide_index=True)

# ===============================
# 11. 底栏时间戳
# ===============================
tz = pytz.timezone("Asia/Shanghai")
now_bj = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
st.caption(f"最后更新: {now_bj} (北京时间) · Cookie 有效期至 2026-04-20")

# ===============================
# 12. 仅开盘时段自动刷新（30秒）
# ===============================
if trading:
    st.markdown("""
<script>
setTimeout(function(){ window.location.reload(); }, 30000);
</script>
""", unsafe_allow_html=True)
