import json
from datetime import datetime


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


# 更新股票列表
with open(
    "public/data/stocks.json",
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        {
            "stocks": stocks
        },
        f,
        ensure_ascii=False,
        indent=2
    )


# 更新行情
quotes = {
    "date": datetime.now().strftime("%Y-%m-%d"),
    "quotes": [
        {
            "code": "000001",
            "name": "平安银行",
            "price": 12.35,
            "change": 1.25
        },
        {
            "code": "600519",
            "name": "贵州茅台",
            "price": 1450,
            "change": -0.35
        }
    ]
}


with open(
    "public/data/quotes/latest.json",
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        quotes,
        f,
        ensure_ascii=False,
        indent=2
    )


print("data update success")
