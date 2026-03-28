import requests

def test_sina():
    symbols = "fx_susdcnh"
    url = f"http://hq.sinajs.cn/list={symbols}"
    headers = {"Referer": "https://finance.sina.com.cn/"}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        print(f"Sina Result: {res.text}")
    except Exception as e:
        print(f"Sina Error: {e}")

def test_tencent():
    symbol = "usdcnh"
    url = f"http://qt.gtimg.cn/q={symbol}"
    try:
        res = requests.get(url, timeout=5)
        print(f"Tencent Result: {res.content.decode('gbk')}")
    except Exception as e:
        print(f"Tencent Error: {e}")

if __name__ == "__main__":
    test_sina()
    test_tencent()
