import pandas as pd
import holidays

def get_w_days(start, end):

    kr_hols = holidays.KR()

    days = pd.date_range(start, end)

    return len([
        d for d in days
        if d.weekday() != 6 and d not in kr_hols
    ])