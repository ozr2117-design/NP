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
@st.cache_data(ttl=15)
def fetch_all_data():
    """从腾讯接口获取所有 ETF 实时行情、IOPV、溢价率和规模"""
    symbols = [f"{i['prefix']}{i['code']}" for i in MONITOR_LIST]
    url = f"http://qt.gtimg.cn/q={','.join(symbols)}"
    try:
        # 腾讯接口返回 GBK 编码
        res = requests.get(url, timeout=5)
        text = res.content.decode("gbk")
        
        result = {}
        # 结果格式: v_sh513100="1~纳指ETF~513100...~3.13~1.6640...~";
        for line in text.split(";"):
            if "~" not in line or "=" not in line: continue
            try:
                # 提取代码
                code_match = line.split("=")[0].strip()[-6:]
                # 提取数据部分
                data_str = line.split('"')[1]
                parts = data_str.split("~")
                
                if len(parts) > 68:
                    result[code_match] = {
                        "name":         parts[1],            # 官方名称
                        "current":      float(parts[3]),     # 最新价
                        "percent":      float(parts[32]),    # 涨跌幅 (%)
                        "scale_yi":     float(parts[45]) if parts[45] else 0.0, # 总市值 (亿元)
                        "premium_rate": float(parts[67]),    # 溢价率 (%)
                        "iopv":         float(parts[68]),    # IOPV
                    }
            except: continue
        return result, None
    except Exception as e:
        return None, f"腾讯接口访问失败: {e}"

# ===============================
# 4. 构建数据表
# ===============================
def build_df(data):
    rows = []
    for item in MONITOR_LIST:
        tx = data.get(item["code"], {})
        if not tx: continue

        rows.append({
            "代码":       item["code"],
            "简称":       item["short"],
            "名称":       tx.get("name") or item["short"],
            "分类":       item["category"],
            "最新价":     tx.get("current", 0),
            "IOPV":       tx.get("iopv", 0),
            "涨跌幅(%)":  tx.get("percent", 0),
            "溢价率(%)":  tx.get("premium_rate", 0),
            "资产净值":   tx.get("scale_yi", 0),
        })

    df = pd.DataFrame(rows)
    if df.empty: return df

    # 分类排序：先标普后纳指，各自内部按溢价率从低到高
    sp_df = df[df["分类"] == "标普"].sort_values("溢价率(%)", ascending=True, na_position="last")
    nd_df = df[df["分类"] == "纳指"].sort_values("溢价率(%)", ascending=True, na_position="last")
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
.closed-banner {
    text-align:center; padding:10px 0; font-size:13px;
    color:#888; background:#f5f5f5; border-radius:8px; margin-bottom:12px;
}
</style>
<div class='main-title'>📊 纳指 &amp; 标普 ETF 实时溢价监控</div>
<div class='subtitle'>数据源：腾讯财经 (零 Cookie 自动刷新版)</div>
""", unsafe_allow_html=True)

# ===============================
# 6. 状态判断
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
# 7. 获取数据
# ===============================
data, err = fetch_all_data()

if err or not data:
    st.error(f"数据加载失败: {err}")
    st.stop()

df = build_df(data)

if df.empty:
    st.warning("暂无数据，请稍后检查网络或接口状态。")
    st.stop()

sp_valid = df[(df["分类"] == "标普") & (df["溢价率(%)"] != 0)]
nd_valid = df[(df["分类"] == "纳指") & (df["溢价率(%)"] != 0)]

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
    sp_max = sp_valid.loc[sp_valid["溢价率(%)"].idxmax()]
    sp_min = sp_valid.loc[sp_valid["溢价率(%)"].idxmin()]
    sp_avg = sp_valid["溢价率(%)"].mean()
    c1, c2, c3 = st.columns(3)
    with c1: st.markdown(stat_card("溢价最高", sp_max["名称"], sp_max["溢价率(%)"]), unsafe_allow_html=True)
    with c2: st.markdown(stat_card("溢价最低", sp_min["名称"], sp_min["溢价率(%)"]), unsafe_allow_html=True)
    with c3: st.markdown(avg_card("平均溢价率", sp_avg), unsafe_allow_html=True)

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# --- 纳指 ---
st.markdown("<div class='section-hdr'><span class='badge-nd'>纳指 NASDAQ</span></div>", unsafe_allow_html=True)
if not nd_valid.empty:
    nd_max = nd_valid.loc[nd_valid["溢价率(%)"].idxmax()]
    nd_min = nd_valid.loc[nd_valid["溢价率(%)"].idxmin()]
    nd_avg = nd_valid["溢价率(%)"].mean()
    c4, c5, c6 = st.columns(3)
    with c4: st.markdown(stat_card("溢价最高", nd_max["名称"], nd_max["溢价率(%)"]), unsafe_allow_html=True)
    with c5: st.markdown(stat_card("溢价最低", nd_min["名称"], nd_min["溢价率(%)"]), unsafe_allow_html=True)
    with c6: st.markdown(avg_card("平均溢价率", nd_avg), unsafe_allow_html=True)

st.divider()

# ===============================
# 9. 数据表
# ===============================
def color_premium(val):
    try:
        v = float(val)
        if v > 2:   return "background-color:#ff4d4d;color:white;font-weight:bold"
        elif v > 0: return "background-color:#ffcccc"
        elif v < 0: return "background-color:#ccffcc"
        return ""
    except: return ""

def color_pct(val):
    try: return "color:#d62728" if float(val) > 0 else "color:#2ca02c"
    except: return ""

def color_category(val):
    if val == "标普":   return "color:#1a56db;font-weight:600"
    elif val == "纳指": return "color:#b45309;font-weight:600"
    return ""

display_cols = ["代码", "名称", "分类", "最新价", "涨跌幅(%)", "溢价率(%)", "资产净值"]

styled = df[display_cols].style \
    .applymap(color_premium,  subset=["溢价率(%)"]) \
    .applymap(color_pct,      subset=["涨跌幅(%)"]) \
    .applymap(color_category, subset=["分类"]) \
    .format({
        "最新价":     "{:.3f}",
        "涨跌幅(%)":  "{:+.2f}%",
        "溢价率(%)":  "{:+.2f}%",
        "资产净值":   "{:.2f} 亿",
    })

st.dataframe(styled, use_container_width=True, height=420, hide_index=True)

# ===============================
# 10. 底栏
# ===============================
tz = pytz.timezone("Asia/Shanghai")
now_bj = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
st.caption(f"最后更新: {now_bj} (北京时间) · 每 30 秒自动刷新一次 (仅开盘期间)")

# ===============================
# 11. 自动刷新
# ===============================
if trading:
    st.markdown("""
<script>
setTimeout(function(){ window.location.reload(); }, 30000);
</script>
""", unsafe_allow_html=True)
