import akshare as ak
import json
from datetime import datetime


codes = [
    "000001",
    "600519"
]


result = []


for code in codes:

    df = ak.stock_zh_a_spot_em()

    row = df[df["代码"] == code].iloc[0]

    result.append(
        {
            "code": code,
            "name": row["名称"],
            "price": float(row["最新价"]),
            "change": float(row["涨跌幅"])
        }
    )


data = {
    "date": datetime.now().strftime("%Y-%m-%d"),
    "quotes": result
}


with open(
    "public/data/quotes/latest.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        data,
        f,
        ensure_ascii=False,
        indent=2
    )


print("real market data updated")
