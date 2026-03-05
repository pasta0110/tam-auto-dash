import pandas as pd

df = pd.read_excel("data.xlsx", sheet_name="주문건")

def get_cat(name):
    n = str(name).replace(" ", "").replace("-", "").replace("+", "").strip()
    if "판넬01" in n:
        return "판넬01"
    elif "판넬05" in n:
        return "판넬05"
    elif "매트리스" in n:
        return "매트리스"
    elif "파운데이션" in n:
        return "파운데이션"
    elif "프레임" in n:
        return "프레임"
    else:
        return "기타"

df["품목구분"] = df["상품명"].apply(get_cat)
df["등록일_DT"] = pd.to_datetime(df["등록일"], errors="coerce")

this_month_key = "2026-03"
yesterday_str = "2026-03-05"

curr_order = df[df["등록일_DT"].dt.strftime("%Y-%m") == this_month_key]
day_order = curr_order[curr_order["등록일_DT"].dt.strftime("%Y-%m-%d") == yesterday_str]

# 합계를 day_order 기준으로 계산 (스트림릿에서 발생하는 문제 재현)
wrong_total = day_order.groupby("품목구분").size()

# 합계를 curr_order 기준으로 계산 (올바른 방식)
correct_total = curr_order.groupby("품목구분").size()

print("=== 잘못된 합계 (day_order 기준) ===")
print(wrong_total)

print("\n=== 올바른 합계 (curr_order 기준) ===")
print(correct_total)
