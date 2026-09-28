import json
import requests
from datetime import datetime
def get_price(code):
    url = f"https://qt.gtimg.cn/q=sh{code}"
    r = requests.get(url)
    data = r.text

    return data

stocks = [
    {
        "code": "000001",
        "name": "平安银行"
    },
    {
        "code": "600519",
        "name": "贵州茅台"
    }
]


quotes = []

for stock in stocks:
    quotes.append({
        "code": stock["code"],
        "name": stock["name"],
        "price": get_price(stock["code"])
    })


data = {
    "date": datetime.now().strftime("%Y-%m-%d"),
    "quotes": quotes
}
}


with open("public/data/quotes.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
