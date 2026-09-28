import json
from datetime import datetime
import tushare as ts


# TuShare Token
TOKEN = "58ee04f469d088e0fc2c8812aff403a50c1fcd883854cdca5293ed9e"

ts.set_token(TOKEN)

pro = ts.pro_api()


# 股票列表
stocks = [
    {
        "code": "000001",
        "ts_code": "000001.SZ",
        "name": "平安银行"
    },
    {
        "code": "600519",
        "ts_code": "600519.SH",
        "name": "贵州茅台"
    }
]


quotes = []


today = datetime.now().strftime("%Y%m%d")


for stock in stocks:

    try:

        df = pro.daily(
            ts_code=stock["ts_code"],
            trade_date=today
        )


        if not df.empty:

            row = df.iloc[0]

            quotes.append(
                {
                    "code": stock["code"],
                    "name": stock["name"],
                    "price": float(row["close"]),
                    "change": float(row["pct_chg"])
                }
            )

        else:

            print(
                stock["name"],
                "今天没有交易数据"
            )


    except Exception as e:

        print(
            stock["name"],
            "获取失败:",
            e
        )



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


print("更新完成")
print(data)
