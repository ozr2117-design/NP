import requests

def test_sina_iopv():
    symbol = "sh513100,sh513100_i"
    url = f"http://hq.sinajs.cn/list={symbol}"
    headers = {"Referer": "https://finance.sina.com.cn/"}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        print(f"Sina Result:\n{res.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_sina_iopv()
