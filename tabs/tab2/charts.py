import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def paged_bar_figure(df_view: pd.DataFrame, view_months: list[str], month_labels: list[str], monthly_totals: pd.Series, active_centers: list[str]) -> go.Figure:
    fig_bar = go.Figure()
    colors = px.colors.qualitative.Pastel

    for i, center in enumerate(active_centers):
        center_data = df_view[df_view["지역센터"] == center]
        y_vals = []
        texts = []

        for m in view_months:
            val = center_data[center_data["연월_키"] == m]["완료건수"].sum()
            total = monthly_totals.get(m, 1)
            share = round((val / total) * 100, 1)
            y_vals.append(val)
            texts.append(f"{val:,}건<br>({share}%)")

        fig_bar.add_trace(
            go.Bar(
                name=center,
                x=[month_labels, [center for _ in view_months]],
                y=y_vals,
                text=texts,
                textposition="outside",
                marker_color=colors[i % len(colors)],
                textfont=dict(size=15, family="Malgun Gothic", color="#2f3e46"),
                customdata=[monthly_totals.get(m, 0) for m in view_months],
                hovertemplate=(
                    "월: %{x[0]}<br>"
                    "배송사: %{x[1]}<br>"
                    "완료건수: %{y:,}건<br>"
                    "월 총합: %{customdata:,}건<extra></extra>"
                ),
            )
        )

    fig_bar.update_layout(
        barmode="group",
        margin=dict(t=80, b=80),
        xaxis=dict(title="", tickfont=dict(size=15, family="Malgun Gothic")),
        yaxis_title="완료건수",
        legend=dict(orientation="h", yanchor="bottom", y=1.1, xanchor="right", x=1),
        font=dict(family="Malgun Gothic"),
        uniformtext_minsize=11,
        uniformtext_mode="hide",
    )
    fig_bar.update_xaxes(type="multicategory")
    return fig_bar


def dual_axis_figure(df_combined: pd.DataFrame, sel_v: str) -> go.Figure:
    fig_dual = make_subplots(specs=[[{"secondary_y": True}]])

    fig_dual.add_trace(
        go.Bar(
            x=df_combined["월일자"],
            y=df_combined["전체건수"],
            name="전체 출고건수",
            marker_color="rgba(180, 180, 180, 0.5)",
            text=df_combined["전체건수"],
            textposition="inside",
            insidetextanchor="end",
            textfont=dict(size=11, color="white", family="Malgun Gothic"),
            hovertemplate="전체: %{y}건",
        ),
        secondary_y=False,
    )

    fig_dual.add_trace(
        go.Scatter(
            x=df_combined["월일자"],
            y=df_combined["지역건수"],
            name=f"{sel_v} 건수",
            mode="lines+markers+text",
            line=dict(color="#0077b6", width=3),
            marker=dict(size=10, symbol="circle"),
            text=df_combined["지역건수"].astype(int),
            textposition="top center",
            textfont=dict(size=14, color="#0077b6"),
            hovertemplate=f"{sel_v}: %{{y}}건",
        ),
        secondary_y=True,
    )

    max_total = df_combined["전체건수"].max() if not df_combined.empty else 100
    max_region = df_combined["지역건수"].max() if not df_combined.empty else 100
    right_axis_max = max(10, max_region * 1.3)

    fig_dual.update_layout(
        title=dict(text=f"<b>📊 {sel_v} 지역 vs 전체 출고 추이 비교</b>", font=dict(size=20)),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=100, b=20),
        height=500,
        font=dict(family="Malgun Gothic"),
    )

    fig_dual.update_xaxes(tickformat="%y년 %m월", dtick="M1", title_text="출고 연월")
    fig_dual.update_yaxes(title_text="전체 물량 (막대)", secondary_y=False, showgrid=False, range=[0, max_total * 1.3])
    fig_dual.update_yaxes(title_text=f"{sel_v} 물량 (선)", secondary_y=True, showgrid=True, range=[-200, right_axis_max])
    return fig_dual
