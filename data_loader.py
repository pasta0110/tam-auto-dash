import pandas as pd
import requests
from io import BytesIO
import streamlit as st
from config import DATA_URL

@st.cache_data(ttl=300)
def load_data():

    response = requests.get(DATA_URL, timeout=15)
    response.raise_for_status()

    with BytesIO(response.content) as f:

        ord_df = pd.read_excel(f, sheet_name='주문건')

        f.seek(0)

        del_df = pd.read_excel(
            f,
            sheet_name='출고건',
            skiprows=13
        )

    ord_df.columns = [str(c).strip() for c in ord_df.columns]
    del_df.columns = [str(c).strip() for c in del_df.columns]

    return ord_df, del_df