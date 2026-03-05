import pandas as pd
import requests
import time
import os

# 1. 설정
API_KEY = "여기에_인증키를_넣으세요"
FILE_PATH = r'C:\Users\alcls\Documents\tam-auto-dash\data.xlsx'
OUTPUT_PATH = 'coords.csv'

def get_vworld_coords(addr):
    url = "https://api.vworld.kr/req/address"
    params = {
        "service": "address", "request": "getcoord", "crs": "epsg:4326",
        "address": addr, "format": "json", "type": "road", "key": API_KEY
    }
    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        if data['response']['status'] == 'OK':
            return float(data['response']['result']['point']['y']), float(data['response']['result']['point']['x'])
    except: pass
    return None, None

# 2. 데이터 로드
df = pd.read_excel(FILE_PATH, sheet_name='출고건', header=13)
df['search_addr'] = df['주소'].apply(lambda x: ' '.join(str(x).split()[:4]))
unique_addrs = df['search_addr'].unique()
total_count = len(unique_addrs)

results = []
print(f"🚀 총 {total_count}건 변환 시작 (1건마다 실시간 저장)")

# 3. 변환 및 실시간 파일 쓰기
for i, addr in enumerate(unique_addrs):
    lat, lon = get_vworld_coords(addr)
    if lat:
        results.append({'search_addr': addr, 'lat': lat, 'lon': lon})
        
    # [핵심] 1건 할 때마다 파일 전체를 새로 씀 (가장 안전)
    # 3,000건 정도는 이 방식이 가장 확실합니다.
    pd.DataFrame(results).to_csv(OUTPUT_PATH, index=False, encoding='utf-8-sig')
    
    print(f"\r📦 진행: [ {i+1} / {total_count} ] - 저장완료", end='', flush=True)
    time.sleep(0.05)

print("\n🎉 모든 변환 및 저장 완료!")