# tabs/tab5_map.py
# 브이월드 API를 활용한 실시간 배송 지도 (v8.0: 배송 지연 집중 분석)

import streamlit as st
import pandas as pd
import requests
import folium
import os
from streamlit_folium import folium_static
from folium.plugins import HeatMap, FastMarkerCluster, MarkerCluster
from concurrent.futures import ThreadPoolExecutor
from services.map_ops import clean_address, mask_addr, mask_name, build_delay_df

try:
    from sklearn.cluster import DBSCAN
except Exception:
    DBSCAN = None

@st.cache_data(ttl=300, show_spinner=False)
def _prepare_map_base_cached(src_df: pd.DataFrame, csv_path: str, csv_mtime: float):
    df_map_base = src_df.copy()
    df_map_base["search_addr"] = df_map_base["주소"].apply(clean_address)
    target_addrs = [addr for addr in df_map_base["search_addr"].unique() if str(addr).strip()]

    if os.path.exists(csv_path):
        try:
            saved_coords = pd.read_csv(csv_path)
        except Exception:
            saved_coords = pd.DataFrame(columns=["search_addr", "lat", "lon"])
    else:
        saved_coords = pd.DataFrame(columns=["search_addr", "lat", "lon"])

    if not saved_coords.empty:
        saved_coords["lat"] = pd.to_numeric(saved_coords["lat"], errors="coerce")
        saved_coords["lon"] = pd.to_numeric(saved_coords["lon"], errors="coerce")
        saved_coords = saved_coords.dropna(subset=["lat", "lon"]).copy()

    final_map_df = pd.merge(df_map_base, saved_coords, on="search_addr", how="inner")
    return df_map_base, target_addrs, saved_coords, final_map_df


@st.cache_data(ttl=300, show_spinner=False)
def _build_delay_df_cached(df: pd.DataFrame) -> pd.DataFrame:
    return build_delay_df(df)


@st.cache_data(ttl=300, show_spinner=False)
def _map_side_summary(df: pd.DataFrame):
    carrier_counts = df["배송사_정제"].value_counts() if "배송사_정제" in df.columns else pd.Series(dtype="int64")
    item_counts = df["상품명"].value_counts().reset_index() if "상품명" in df.columns else pd.DataFrame(columns=["상품명", "수량"])
    if not item_counts.empty:
        item_counts.columns = ["상품명", "수량"]
    return carrier_counts, item_counts


def render(ana_df, cache_key=None):
    st.title("📍 전국 실시간 배송 밀집도 (AI 분석)")
    st.markdown("브이월드 API와 AI 알고리즘을 활용하여 **배송 속도(영업일 기준), 물류사 분포, 상품별 수요**를 시각적으로 분석합니다.")

    # [보안] 1. API 키 관리
    try:
        VWORLD_API_KEY = str(st.secrets.get("VWORLD_API_KEY", "")).strip()
    except Exception:
        VWORLD_API_KEY = ""
    if not VWORLD_API_KEY:
        st.error("VWORLD_API_KEY가 설정되지 않았습니다. Streamlit secrets에 키를 등록하세요.")
        return

    if '주소' in ana_df.columns:
        # 데이터 정제 및 복사
        # 고객명, 배송메세지 등 상세 정보가 원본 데이터프레임에 있는지 확인 필요
        # 없다면 ana_df 생성 시 포함되었는지 data_processor.py 확인 필요하지만, 일단 있는 컬럼 최대한 활용
        cols_to_use = [c for c in ['주소', '상품명', '배송사_정제', '배송예정일', '주문등록일'] if c in ana_df.columns]
        if '주소' not in cols_to_use:
            st.error("데이터에 '주소' 컬럼이 없습니다.")
            return
        # ana_df에 '성명', '배송메세지' 등이 있다면 추가
        for col in ['성명', '수령인', '주문자', '배송메세지', '배송메모', '비고']:
            if col in ana_df.columns:
                cols_to_use.append(col)
        
        df_map_base = ana_df[cols_to_use].copy()
        
        # [저장] 4. CSV 경로 설정
        CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "coords.csv")
        
        csv_mtime = os.path.getmtime(CSV_PATH) if os.path.exists(CSV_PATH) else 0.0
        df_map_base, target_addrs, saved_coords, final_map_df = _prepare_map_base_cached(df_map_base, CSV_PATH, csv_mtime)
        
        # 저장된 좌표에 없는 주소만 추출
        if not saved_coords.empty:
            existing_set = set(saved_coords['search_addr'].values)
            missing_addrs = [addr for addr in target_addrs if addr not in existing_set]
        else:
            missing_addrs = target_addrs

        # [HTTPS] 8. API URL HTTPS 적용
        def vworld_geocode(addr_str):
            if not addr_str: return None, None
            url = "https://api.vworld.kr/req/address"
            params = {
                "service": "address", "request": "getcoord", "version": "2.0",
                "crs": "epsg:4326", "address": addr_str, "refine": "true",
                "simple": "false", "format": "json", "type": "ROAD", "key": VWORLD_API_KEY
            }
            try:
                response = requests.get(url, params=params, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('response', {}).get('status') == 'OK':
                        x = data.get('response', {}).get('result', {}).get('point', {}).get('x')
                        y = data.get('response', {}).get('result', {}).get('point', {}).get('y')
                        if x is None or y is None:
                            return None, None
                        return float(y), float(x)
            except Exception:
                pass
            return None, None

        # [속도] 기본 렌더에서는 지오코딩 자동 실행을 막고, 필요 시 수동 실행
        new_coords_list = []
        run_geocode = False
        if len(missing_addrs) > 0:
            st.info(f"좌표 누락 주소 {len(missing_addrs):,}건이 있습니다. 지도 속도를 위해 자동 변환은 비활성화되어 있습니다.")
            run_geocode = st.button(f"🌐 누락 주소 좌표 보완 실행 ({len(missing_addrs):,}건)", key="tab5_run_geocode")

        if run_geocode:
            with st.spinner(f'🌐 고속 변환 중... ({len(missing_addrs)}건)'):
                worker_n = max(1, min(8, len(missing_addrs)))
                with ThreadPoolExecutor(max_workers=worker_n) as executor:
                    results = list(executor.map(vworld_geocode, missing_addrs))
                for addr, (lat, lon) in zip(missing_addrs, results):
                    if lat is not None and lon is not None:
                        new_coords_list.append({'search_addr': addr, 'lat': lat, 'lon': lon})

        # 데이터 병합 및 저장
        if new_coords_list:
            new_coords_df = pd.DataFrame(new_coords_list)
            combined_coords = pd.concat([saved_coords, new_coords_df], ignore_index=True).drop_duplicates(subset=['search_addr'])
            combined_coords["lat"] = pd.to_numeric(combined_coords["lat"], errors="coerce")
            combined_coords["lon"] = pd.to_numeric(combined_coords["lon"], errors="coerce")
            combined_coords = combined_coords.dropna(subset=["lat", "lon"]).copy()
            try:
                combined_coords.to_csv(CSV_PATH, index=False, encoding='utf-8-sig')
                # st.toast(f"✅ {len(new_coords_list)}건 좌표 신규 등록 완료!")
                saved_coords = combined_coords
            except Exception as e:
                st.error(f"좌표 파일 저장 실패: {e}")
        else:
            combined_coords = saved_coords

        # [성능] 7. 지도 렌더링 최적화
        if new_coords_list:
            final_map_df = pd.merge(df_map_base, combined_coords, on='search_addr', how='inner')

        if not final_map_df.empty:
            
            # 분석 모드 선택 UI (라디오 버튼)
            analysis_mode = st.radio(
                "📊 분석 모드 선택",
                ["🔥 주문 밀집도 (기본)", "🚚 배송 소요시간 분석", "🏢 배송사별 분포", "📦 상품별 수요 분석"],
                horizontal=True
            )
            
            # 상품 선택 필터
            selected_product = "전체"
            if analysis_mode == "📦 상품별 수요 분석":
                products = final_map_df['상품명'].dropna().astype(str).unique().tolist()
                product_list = sorted(products)
                product_list.insert(0, "전체")
                selected_product = st.selectbox("📦 분석할 상품 선택", product_list)
                
                if selected_product != "전체":
                    final_map_df = final_map_df[final_map_df['상품명'].astype(str) == selected_product]
                    st.info(f"🔎 **{selected_product}** 주문 {len(final_map_df):,}건을 분석합니다.")

            carrier_counts, item_counts = _map_side_summary(final_map_df)

            if "tab5_render_map" not in st.session_state:
                st.session_state["tab5_render_map"] = False
            c_btn1, c_btn2, _ = st.columns([1, 1, 3])
            if c_btn1.button("🗺️ 지도 렌더링", key="tab5_render_on"):
                st.session_state["tab5_render_map"] = True
            if c_btn2.button("⏹️ 지도 숨기기", key="tab5_render_off"):
                st.session_state["tab5_render_map"] = False

            # 레이아웃 분할
            col_map, col_stat = st.columns([3, 1])
            max_points = st.slider("🗺️ 지도 표시 최대 포인트", 800, 8000, 2500, 400, key="tab5_max_points")
            map_df = final_map_df if len(final_map_df) <= max_points else final_map_df.sample(max_points, random_state=42)
            if len(final_map_df) > max_points:
                st.caption(f"성능 최적화를 위해 지도 표시는 {len(final_map_df):,}건 중 {max_points:,}건만 샘플링합니다.")
            
            # ─────────────────────────────────────────────────────────────
            # [기능 개선] 배송 소요시간 분석 전용 로직 (필터링 및 상세 팝업)
            # ─────────────────────────────────────────────────────────────
            
            delay_df_final = pd.DataFrame() # 초기화
            
            if analysis_mode == "🚚 배송 소요시간 분석":
                if "주문등록일" not in final_map_df.columns:
                    st.warning("주문등록일 컬럼이 없어 배송 소요시간 분석을 실행할 수 없습니다.")
                    delay_df_final = pd.DataFrame()
                else:
                    delay_df = _build_delay_df_cached(final_map_df)

                    # [UI] 상태별 필터링
                    with col_map:
                        st.write("🔽 **지도 표시 필터**")
                        c1, c2, c3 = st.columns(3)
                        show_green = c1.checkbox("🟢 정상 표시", value=True)
                        show_orange = c2.checkbox("🟠 주의 표시", value=True)
                        c3.checkbox("🔴 지연 표시(필수)", value=True, disabled=True)

                    # 필터 적용
                    target_colors = []
                    if show_green: target_colors.append('green')
                    if show_orange: target_colors.append('orange')
                    target_colors.append('red') # 항상 포함

                    delay_df_final = delay_df[delay_df['상태'].isin(target_colors)]

            with col_map:
                if not st.session_state.get("tab5_render_map", False):
                    st.info("지도 렌더링이 비활성화되어 있습니다. 우측 통계는 즉시 갱신됩니다.")
                else:
                    center_lat = map_df['lat'].mean()
                    center_lon = map_df['lon'].mean()

                    m = folium.Map(
                        location=[center_lat, center_lon],
                        zoom_start=7,
                        tiles="CartoDB positron",
                        prefer_canvas=True
                    )

                    if analysis_mode == "🔥 주문 밀집도 (기본)":
                        heat_data = map_df[['lat', 'lon']].values.tolist()
                        HeatMap(heat_data, radius=15, blur=10, min_opacity=0.3).add_to(m)

                        coords = map_df[['lat', 'lon']].values
                        if len(coords) > 0 and DBSCAN is not None:
                            cluster_src = map_df if len(map_df) <= 4500 else map_df.sample(4500, random_state=42)
                            c_coords = cluster_src[['lat', 'lon']].values
                            dbscan = DBSCAN(eps=0.05, min_samples=10).fit(c_coords)
                            cluster_src = cluster_src.copy()
                            cluster_src['cluster'] = dbscan.labels_
                            cluster_centers = cluster_src[cluster_src['cluster'] != -1].groupby('cluster')[['lat', 'lon']].mean().reset_index()
                            cluster_centers['count'] = cluster_src[cluster_src['cluster'] != -1].groupby('cluster')['search_addr'].count().values

                            for _, row in cluster_centers.iterrows():
                                folium.Marker(
                                    location=[row['lat'], row['lon']],
                                    popup=folium.Popup(f"<b>⭐ 거점 C{int(row['cluster'])}</b><br>물량: {int(row['count'])}건", max_width=200),
                                    icon=folium.Icon(color='red', icon='star', prefix='fa')
                                ).add_to(m)
                        elif len(coords) > 0 and DBSCAN is None:
                            st.caption("참고: sklearn 미설치로 군집 거점 표시는 생략됩니다.")

                    elif analysis_mode == "🚚 배송 소요시간 분석":
                        non_red_df = delay_df_final[delay_df_final['상태'] != 'red']
                        if not non_red_df.empty:
                            FastMarkerCluster(data=non_red_df[['lat', 'lon']].values.tolist()).add_to(m)

                        red_df = delay_df_final[delay_df_final['상태'] == 'red']
                        if len(red_df) > 800:
                            red_df = red_df.sort_values("영업배송일수", ascending=False).head(800)
                            st.caption("성능 최적화를 위해 지연 마커는 상위 800건만 표시합니다.")
                        marker_cluster = MarkerCluster().add_to(m)

                        for _, row in red_df.iterrows():
                            name = row.get('수령인', row.get('성명', '고객'))
                            msg = row.get('배송메세지', row.get('배송메모', '-'))
                            masked_name = mask_name(name)
                            masked_addr = mask_addr(row.get('주소', row.get('search_addr', '')))

                            popup_html = f"""
                            <div style="width:250px; font-size:13px;">
                                <b style="color:red;">🔴 배송 지연 ({int(row['영업배송일수'])}일 소요)</b><br>
                                <hr style="margin:5px 0;">
                                <b>고객명:</b> {masked_name}<br>
                                <b>주소:</b> {masked_addr}<br>
                                <b>상품:</b> {row['상품명']}<br>
                                <b>배송사:</b> {row['배송사_정제']}<br>
                                <b>메세지:</b> {msg}
                            </div>
                            """

                            folium.Marker(
                                location=[row['lat'], row['lon']],
                                popup=folium.Popup(popup_html, max_width=300),
                                icon=folium.Icon(color='red', icon='exclamation-triangle', prefix='fa')
                            ).add_to(marker_cluster)

                    elif analysis_mode == "🏢 배송사별 분포":
                        unique_carriers = map_df['배송사_정제'].unique()
                        colors = ['blue', 'green', 'red', 'purple', 'orange', 'darkblue', 'darkgreen', 'cadetblue']
                        carrier_colors = {carrier: colors[i % len(colors)] for i, carrier in enumerate(unique_carriers)}

                        plot_df = map_df if len(map_df) <= 2500 else map_df.sample(2500, random_state=42)
                        for _, row in plot_df.iterrows():
                            carrier = row['배송사_정제']
                            color = carrier_colors.get(carrier, 'gray')
                            folium.CircleMarker(
                                location=[row['lat'], row['lon']],
                                radius=5, color=color, fill=True, fill_opacity=0.7, popup=f"배송사: {carrier}"
                            ).add_to(m)

                        legend_html = '<div style="position: fixed; bottom: 50px; left: 50px; z-index:9999; font-size:14px; background-color:white; opacity:0.8; padding: 10px; border:2px solid grey;">'
                        for carrier, color in carrier_colors.items():
                            legend_html += f'&nbsp; <span style="color:{color}">●</span> {carrier} <br>'
                        legend_html += '</div>'
                        m.get_root().html.add_child(folium.Element(legend_html))

                    elif analysis_mode == "📦 상품별 수요 분석":
                        marker_cluster = FastMarkerCluster(data=map_df[['lat', 'lon']].values.tolist())
                        marker_cluster.add_to(m)

                    folium_static(m, width=900, height=600)
            
            with col_stat:
                st.subheader(f"📊 {analysis_mode}")
                st.markdown("---")
                
                if analysis_mode == "🚚 배송 소요시간 분석":
                    if not delay_df_final.empty:
                        # 1. 요약 메트릭
                        red_count = len(delay_df_final[delay_df_final['상태']=='red'])
                        st.metric("🔴 현재 표시된 지연 건수", f"{red_count}건")
                    else:
                        st.info("표시할 데이터가 없습니다.")

                elif analysis_mode == "🏢 배송사별 분포":
                    st.write("**배송사 점유율**")
                    st.bar_chart(carrier_counts)
                    
                else:
                    st.dataframe(item_counts, height=400, hide_index=True)
            
            # [기능 추가] 지연 상세 리스트 (지도 아래 배치)
            if analysis_mode == "🚚 배송 소요시간 분석":
                st.markdown("---")
                with st.expander("🚨 지연 배송 건 상세 목록 (검색/정렬 가능)", expanded=True):
                    if not delay_df_final.empty:
                        red_items = delay_df_final[delay_df_final['상태']=='red']
                        if not red_items.empty:
                            # 표시할 컬럼 정리
                            display_cols = ['주소', '상품명', '배송사_정제', '영업배송일수']
                            # 추가 정보 있으면 포함
                            for col in ['수령인', '성명', '배송메세지']:
                                if col in red_items.columns: display_cols.append(col)
                                
                            view_df = red_items[display_cols].copy()
                            if "주소" in view_df.columns:
                                view_df["주소"] = view_df["주소"].apply(mask_addr)
                            for c in ["수령인", "성명"]:
                                if c in view_df.columns:
                                    view_df[c] = view_df[c].apply(mask_name)
                            view_df.rename(columns={'배송사_정제':'배송사', '영업배송일수':'지연일수(영업일)'}, inplace=True)
                            
                            st.dataframe(
                                view_df.sort_values('지연일수(영업일)', ascending=False),
                                use_container_width=True,
                                hide_index=True
                            )
                        else:
                            st.success("✅ 선택된 조건 내 심각한 지연(빨강) 건이 없습니다.")
                    else:
                        st.info("지도 필터에 의해 모든 데이터가 숨겨졌습니다.")

        else:
            st.warning("지도에 표시할 데이터가 없습니다.")
    else:
        st.error("데이터에 '주소' 컬럼이 없습니다.")
