import os
import pandas as pd

# ==========================================
# 1. 환경 설정 및 데이터 로드
# ==========================================
PROCESSED_DATA_DIR = "./data/processed"
FINAL_DATA_DIR = "./data/final"
BASE_DATA_PATH = os.path.join(PROCESSED_DATA_DIR, "zeropick_base_data_v4.csv")
INGREDIENT_PATH = os.path.join(FINAL_DATA_DIR, "ingredient.csv")
FINAL_OUTPUT_PATH = os.path.join(PROCESSED_DATA_DIR, "product_seed_data.csv")

base_df = pd.read_csv(BASE_DATA_PATH)
ingredient_df = pd.read_csv(INGREDIENT_PATH)


# ==========================================
# 2. 안전 점수(Score) 계산 로직
# ==========================================
PENALTY_SCORES = {
    "PREMIUM": 0,    
    "GENERAL": -15,  
    "WARNING": -35   
}

ingredient_penalty_dict = (
    ingredient_df.set_index('name')['risk_level']
    .map(PENALTY_SCORES)
    .to_dict()
)

def calculate_score(ingredients_string):
    if pd.isna(ingredients_string) or not str(ingredients_string).strip():
        return 100
    
    ingredients_list = [ing.strip() for ing in str(ingredients_string).split(',')]
    score = 100
    
    for ing in ingredients_list:
        if ing in ingredient_penalty_dict:
            score += ingredient_penalty_dict[ing]
            
    return max(0, score) 

base_df['score'] = base_df['표준원재료명'].apply(calculate_score)

conflict = base_df[(base_df['최종등급'] == 1) & (base_df['혈당트랩_여부'] == True)]
print(f"최종등급 1 + 혈당트랩 동시발생: {len(conflict)}건 / {len(base_df)}건")


# ==========================================
# 3. 요약(Summary) 문구 생성 로직
# ==========================================
def generate_summary(row):
    score = row['score']
    grade = row['최종등급']
    has_blood_trap = row.get('혈당트랩_여부', False)
    has_additive_trap = row.get('첨가물트랩_여부', False)
    
    if has_blood_trap:
        return f"제로 마케팅을 하고 있지만 혈당을 올리는 성분이 포함되어 있습니다.\n엄격한 당질 제한 중이라면 피하세요. (안전 점수: {score}점)"
    if has_additive_trap:
        return f"당류는 낮지만 주의가 필요한 착색료/첨가물이 포함되어 있습니다.\n과다 섭취에 유의해주세요. (안전 점수: {score}점)"
    
    if score == 100:
        if grade == 1:
            return "완벽한 성분의 제로 식품입니다.\n혈당 걱정 없이 안심하고 드셔도 좋습니다."
        else:
            return "주의해야 할 대체당이나 첨가물은 발견되지 않은 무난한 제품입니다."
            
    if score >= 85:
        return f"합성 감미료가 일부 포함되어 있으나 대체로 무난한 제품입니다.\n가급적 적당량만 섭취하시길 권장합니다. (안전 점수: {score}점)"
    if score >= 70:
        return f"다수의 합성 감미료가 사용되어 주의가 필요합니다.\n민감하신 분들은 섭취량을 조절하세요. (안전 점수: {score}점)"
    
    return f"가짜 제로 마케팅이 의심되거나 다수의 주의 성분이 포함되어 있습니다.\n성분을 꼼꼼히 확인하세요. (안전 점수: {score}점)"

base_df['summary'] = base_df.apply(generate_summary, axis=1)


# ==========================================
# 4. 카테고리 ID 자동 매핑 로직
# ==========================================
def map_category_id(prdlst_dcnm):
    if pd.isna(prdlst_dcnm):
        return 1 
        
    type_name = str(prdlst_dcnm)
    
    if any(keyword in type_name for keyword in ["초콜릿", "코코아"]):
        return 3
    elif any(keyword in type_name for keyword in ["과자", "빵", "떡", "캔디", "젤리"]):
        return 2
    else:
        return 1


# ==========================================
# 5. DB 스키마 매핑 및 최종 데이터 Export
# ==========================================
product_df = pd.DataFrame()

product_df['category_id'] = base_df['PRDLST_DCNM'].apply(map_category_id).astype('int8')
product_df['external_code'] = base_df['품목제조보고번호'].astype(str)
product_df['name'] = base_df['식품명'].astype(str)
product_df['image_url'] = None 
product_df['raw_materials'] = base_df['표준원재료명'].astype(str)
product_df['grade'] = base_df['최종등급'].astype('int16')
product_df['score'] = base_df['score'].astype('int16')
product_df['summary'] = base_df['summary'].astype(str)
product_df['warning_additive'] = base_df['첨가물트랩_여부'].astype(bool)
product_df['calories'] = base_df['에너지'].fillna(0).astype(int) 
product_df['sugar'] = base_df['당류'].fillna(0.0).round(2).astype(float)
product_df['sodium'] = base_df['나트륨'].round(2).astype(float) 
product_df['deleted_at'] = None

product_df.to_csv(FINAL_OUTPUT_PATH, index=False, encoding='utf-8-sig')
print(f"✅ DB Insert용 최종 데이터 생성 완료: {FINAL_OUTPUT_PATH} ({len(product_df)}건)")