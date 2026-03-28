import requests

def test_all_etfs():
    symbols = ["sh513100", "sz159941", "sh513300", "sz159659", "sz159632", "sh513500", "sz159612", "sz159655", "sh513650"]
    url = f"http://qt.gtimg.cn/q={','.join(symbols)}"
    try:
        res = requests.get(url, timeout=5)
        text = res.content.decode("gbk")
        for line in text.split(";"):
            if "~" not in line: continue
            code = line.split("=")[0].strip()[-6:]
            parts = line.split('"')[1].split("~")
            if len(parts) > 85:
                price = float(parts[3])
                iopv = float(parts[85])
                premium = ((price / iopv) - 1) * 100
                size = float(parts[72]) / 1e8 if parts[72] else 0
                print(f"Code: {code}, Price: {price}, IOPV: {iopv}, Premium: {premium:.2f}%, Size: {size:.2f}Yi")
            else:
                print(f"Code: {code}, Parts count {len(parts)} TOO SHORT")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_all_etfs()
