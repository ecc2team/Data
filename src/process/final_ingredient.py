import pandas as pd

# 1. 파일 불러오기
final_df = pd.read_csv("final_grade_data.csv") 
base_df = pd.read_csv("zeropick_base_data_v4.csv") 

# 2. 추출할 대체당/첨가물
sweeteners = [
    "에리스리톨", "수크랄로스", "스테비아", "알룰로스", 
    "아스파탐", "아세설팜칼륨", "사카린", "나한과", 
    "말티톨", "소르비톨", "자일리톨", "효소처리스테비아"
]

# 3. 데이터 병합 (Merge)
merged_df = pd.merge(
    final_df, 
    base_df[['식품코드', '품목제조보고번호', 'RAWMTRL_NM', '표준원재료명']], 
    left_on='external_food_code',
    right_on='식품코드',      
    how='left'
)

# 4. 제품별 대체당 매핑 추출 
mapping_data = []

for index, row in merged_df.iterrows():
    ext_code = row['external_food_code']
    
    raw_text = str(row['표준원재료명']) if pd.notna(row['표준원재료명']) else str(row['RAWMTRL_NM'])
    
    if raw_text == 'nan':
        continue
        
    # 제품 하나당 발견된 대체당과 그 위치를 임시로 저장할 리스트
    found_ingredients = []
    
    # 텍스트 내에서 키워드가 등장하는 위치(인덱스) 찾기
    for s in sweeteners:
        pos = raw_text.find(s) # 단어가 시작되는 글자 위치 반환 (없으면 -1)
        if pos != -1:
            found_ingredients.append({"name": s, "position": pos})
            
    # 발견된 위치(position)가 빠른 순서대로 정렬 (즉, 원재료명 앞쪽에 적힌 순서)
    found_ingredients.sort(key=lambda x: x["position"])
    
    # 정렬된 순서대로 1, 2, 3... sequence 번호를 부여하며 최종 데이터에 추가
    for seq_num, item in enumerate(found_ingredients, start=1):
        mapping_data.append({
            "external_food_code": ext_code,
            "ingredient_name": item["name"],
            "sequence": seq_num  
        })

# 5. 결과 저장
product_ingredient_df = pd.DataFrame(mapping_data)
product_ingredient_df.to_csv("product_ingredient_mapping.csv", index=False, encoding='utf-8-sig')

print(f"추출 완료! 총 {len(product_ingredient_df)}건의 대체당 연결 데이터가 생성되었습니다.")
print(product_ingredient_df.head(10))