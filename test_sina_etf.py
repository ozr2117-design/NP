import requests

def test_sina_etf():
    # 纳指ETF (513100)
    symbol = "sh513100"
    url = f"http://hq.sinajs.cn/list={symbol}"
    headers = {"Referer": "https://finance.sina.com.cn/"}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        text = res.text
        if "~" in text:
            # Sina full format is different
            pass
        elif "=" in text:
            content = text.split('"')[1]
            parts = content.split(",")
            print(f"Sina Parts: {len(parts)}")
            for i, p in enumerate(parts):
                print(f"{i}: {p}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_sina_etf()
