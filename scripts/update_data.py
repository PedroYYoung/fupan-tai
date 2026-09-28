import json
from datetime import datetime

import akshare as ak


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


try:
    df = ak.stock_zh_a_spot_em()

    for stock in stocks:

        row = df[df["代码"] == stock["code"]]

        if not row.empty:

            quotes.append(
                {
                    "code": stock["code"],
                    "name": stock["name"],
                    "price": float(row.iloc[0]["最新价"]),
                    "change": float(row.iloc[0]["涨跌幅"])
                }
            )

except Exception as e:

    print("AkShare接口失败:")
    print(e)

    # 防止接口失败导致整个任务失败
    quotes = [
        {
            "code": "000001",
            "name": "平安银行",
            "price": None,
            "change": None
        },
        {
            "code": "600519",
            "name": "贵州茅台",
            "price": None,
            "change": None
        }
    ]


data = {
    "date": datetime.now().strftime("%Y-%m-%d"),
    "quotes": quotes
}


with open(
    "public/data/quotes.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        data,
        f,
        ensure_ascii=False,
        indent=2
    )


print("数据更新完成")
