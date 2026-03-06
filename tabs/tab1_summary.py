import streamlit as st

def render_tab1(order_df, delivery_df):

    st.title("🏛️ 종합 현황")

    st.write("주문 데이터")

    st.dataframe(order_df.head())

    st.write("출고 데이터")

    st.dataframe(delivery_df.head())