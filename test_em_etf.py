import requests
import json

def test_eastmoney_etf():
    # 纳指ETF (513100) -> secid: 1.513100 (SH) or 0.159941 (SZ)
    secids = ["1.513100", "0.159941", "1.513500"]
    headers = {"User-Agent": "Mozilla/5.0"}
    for secid in secids:
        # f43: current, f184: iopv, f187: premium_rate (maybe)
        url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&ut=fa5fd1943c7b386f172d6893dbf24471&fields=f43,f57,f58,f170,f45,f188,f187,f184,f183,f62"
        try:
            res = requests.get(url, headers=headers, timeout=5)
            data = res.json().get("data", {})
            if data:
                print(f"\nSecid: {secid}")
                print(f"Price (f43): {data.get('f43', 0) / 1000}")
                print(f"IOPV (f184): {data.get('f184', 0) / 1000}")
                print(f"IOPV (f183): {data.get('f183', 0) / 1000} (maybe fallback?)")
                print(f"Premium Rate (f187): {data.get('f187', 0) / 100}%")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    test_eastmoney_etf()
