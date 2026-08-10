import sys
from pathlib import Path

# 프로젝트 루트 경로를 sys.path에 추가
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

import pandas as pd
import numpy as np
from src.config import DATA_DIR, ensure_dir

# ==========================================
# 지수 표기법 복구 함수
# ==========================================
def fix_scientific_notation(val):
    if pd.isna(val):
        return val
    val_str = str(val).strip()
    try:
        return str(int(float(val_str)))
    except ValueError:
        return val_str

def main():
    print("🚀 대체당/트랩 성분 + 알레르기 유발물질 매핑 데이터 추출을 시작합니다...")

    # 2. 파일 경로 설정
    # NOTE: base_data_file은 원래 interim_dir을 참조했으나,
    # build_zero_product_base_data.py는 zeropick_base_data_v4.csv를
    # PROCESSED_DATA_DIR(data/processed/)에 저장함. interim_dir에는
    # 해당 파일이 애초에 생성되지 않으므로 processed_dir로 통일함.
    processed_dir = DATA_DIR / "processed"
    ensure_dir(processed_dir)

    final_grade_file = processed_dir / "integrated_final_validation.csv"
    base_data_file = processed_dir / "zeropick_base_data_v4.csv"
    output_file = processed_dir / "product_ingredient_mapping.csv"

    if not final_grade_file.exists():
        raise FileNotFoundError(f"[에러] {final_grade_file} 파일이 없습니다.")
    if not base_data_file.exists():
        raise FileNotFoundError(f"[에러] {base_data_file} 파일이 없습니다.")

    # 3. 데이터 불러오기
    print("데이터를 불러오는 중...")
    final_df = pd.read_csv(final_grade_file, dtype=str)
    base_df = pd.read_csv(base_data_file, dtype=str)

    # 4. 스마트 조인 키 감지 로직
    id_candidates = ['품목제조보고번호', 'external_food_code', '식품코드', 'PRDLST_REPORT_NO']
    
    common_keys = [c for c in id_candidates if c in final_df.columns and c in base_df.columns]
    
    if common_keys:
        left_key = common_keys[0]
        right_key = common_keys[0]
    else:
        left_key = next((c for c in id_candidates if c in final_df.columns), None)
        right_key = next((c for c in id_candidates if c in base_df.columns), None)

    if not left_key or not right_key:
        raise KeyError("제품 식별자 컬럼을 찾을 수 없습니다. 데이터 원본을 확인해주세요.")

    print(f"✅ 기준 키 감지 완료: final_df['{left_key}'] <-> base_df['{right_key}']")

    final_df[left_key] = final_df[left_key].apply(fix_scientific_notation)
    base_df[right_key] = base_df[right_key].apply(fix_scientific_notation)

    # 5. 병합
    merge_cols = [right_key]
    if 'RAWMTRL_NM' in base_df.columns and 'RAWMTRL_NM' not in final_df.columns:
        merge_cols.append('RAWMTRL_NM')
    if '표준원재료명' in base_df.columns and '표준원재료명' not in final_df.columns:
        merge_cols.append('표준원재료명')

    if len(merge_cols) > 1:
        print("원재료명 데이터를 병합하는 중...")
        merged_df = pd.merge(
            final_df, 
            base_df[merge_cols], 
            left_on=left_key,
            right_on=right_key,      
            how='left'
        )
    else:
        merged_df = final_df

    # ==========================================
    # 6. 마스터 매핑 딕셔너리
    # ==========================================
    sweetener_mapping = {
        "알룰로스": "ALLULOSE", "알룰로오스": "ALLULOSE", "액상알룰로스": "ALLULOSE", "d-알룰로스": "ALLULOSE", "D-알룰로스": "ALLULOSE",
        "에리스리톨": "ERYTHRITOL", "에리스리톨분말": "ERYTHRITOL", "에리쓰리톨": "ERYTHRITOL",
        "스테비아": "STEVIA", "스테비올배당체": "STEVIA", "효소처리스테비아": "STEVIA", "스테비아추출물": "STEVIA", "리바우디오사이드": "STEVIA",
        "나한과": "MONK_FRUIT", "나한과추출물": "MONK_FRUIT",
        "수크랄로스": "SUCRALOSE", "수크랄로오스": "SUCRALOSE", "액상수크랄로스": "SUCRALOSE",
        "아세설팜칼륨": "ACESULFAME_K", "아세설팜k": "ACESULFAME_K", "아세설팜K": "ACESULFAME_K",
        "아스파탐": "ASPARTAME", "L-아스파탐": "ASPARTAME",
        "자일리톨": "XYLITOL",
        "소르비톨": "SORBITOL", "d-소르비톨": "SORBITOL", "D-소르비톨": "SORBITOL", "디소디톨": "SORBITOL",
        "말티톨": "MALTITOL", "말티톨시럽": "MALTITOL",
        "포도당": "GLUCOSE", "무수포도당": "GLUCOSE", "함수포도당": "GLUCOSE",
        "말토덱스트린": "MALTODEXTRIN", "덱스트린": "MALTODEXTRIN",
        "타피오카전분": "TAPIOCA_STARCH", "타피오카": "TAPIOCA_STARCH", "변성전분": "TAPIOCA_STARCH",
        "과당": "FRUCTOSE", "액상과당": "FRUCTOSE", "기타과당": "FRUCTOSE", "고과당": "FRUCTOSE",
        "아가베시럽": "AGAVE_SYRUP", "아가베": "AGAVE_SYRUP",
        "카라멜색소": "CARAMEL_COLOR", "캐러멜색소": "CARAMEL_COLOR", "카라멜색소I": "CARAMEL_COLOR", "카라멜색소IV": "CARAMEL_COLOR"
    }

    # 알레르기 유발물질(ALLERGEN) 동의어 매핑.
    # zeropick_base_data_v4.csv RAWMTRL_NM 실측 토큰 빈도 기준으로 선정한
    # 상위 8종(우유/계란/밀/대두/땅콩/아몬드/호두/복숭아)만 포함.
    # ingredient.csv의 ALLERGEN 타입 코드와 1:1로 맞춰야 함.
    allergen_mapping = {
        "우유": "MILK", "탈지분유": "MILK", "전지분유": "MILK", "가공유크림": "MILK",
        "유크림": "MILK", "가공버터": "MILK", "버터": "MILK", "무염버터": "MILK",
        "치즈": "MILK", "연유": "MILK", "유청단백분말": "MILK", "유청단백": "MILK", "카제인": "MILK",
        "계란": "EGG", "달걀": "EGG", "전란": "EGG",
        "난백액": "EGG", "난황액": "EGG", "난황": "EGG", "난백": "EGG",
        "난백분": "EGG", "건조난백분말": "EGG",
        "밀가루": "WHEAT", "통밀가루": "WHEAT", "발아통밀가루": "WHEAT", "맥아호밀가루": "WHEAT",
        "밀글루텐": "WHEAT", "활성글루텐": "WHEAT", "영양강화밀가루": "WHEAT", "소맥분": "WHEAT",
        "대두": "SOYBEAN", "대두유": "SOYBEAN", "분리대두단백": "SOYBEAN", "분리대두단백분말": "SOYBEAN",
        "대두단백분말": "SOYBEAN", "대두단백": "SOYBEAN", "대두레시틴": "SOYBEAN",
        "땅콩": "PEANUT", "땅콩버터": "PEANUT", "땅콩분태": "PEANUT", "땅콩페이스트": "PEANUT",
        "볶음땅콩분태": "PEANUT", "땅콩기름": "PEANUT",
        "아몬드": "ALMOND", "아몬드분말": "ALMOND", "통아몬드": "ALMOND", "아몬드분태": "ALMOND",
        "아몬드페이스트": "ALMOND", "아몬드슬라이스": "ALMOND", "구운아몬드분말": "ALMOND", "아몬드향": "ALMOND",
        "호두": "WALNUT", "호두분태": "WALNUT", "호두페이스트": "WALNUT", "깐호두": "WALNUT",
        "복숭아향": "PEACH", "천연복숭아향": "PEACH", "복숭아농축액": "PEACH",
        "복숭아향분말": "PEACH", "액상복숭아향": "PEACH", "복숭아과즙분말": "PEACH",
    }

    # 대체당/첨가물 + 알레르기 매핑을 하나의 딕셔너리로 통합해서 같은 텍스트 탐색
    # 루프에서 한 번에 처리 (product_ingredient는 성분 종류 구분 없이 동일 스키마이므로
    # ingredient.code만 맞으면 되고, 매핑 테이블만 합치면 나머지 탐색 로직은 그대로 재사용 가능).
    ingredient_mapping = {**sweetener_mapping, **allergen_mapping}

    sweeteners_sorted = sorted(ingredient_mapping.keys(), key=len, reverse=True)

    # ==========================================
    # 7. 제품별 대체당 매핑 및 순서(Sequence) 추출
    # ==========================================
    print("원재료명에서 타겟 성분을 추출하고 순서를 부여하는 중...")
    mapping_data = []

    for index, row in merged_df.iterrows():
        ext_code = fix_scientific_notation(row[left_key])
        
        raw_text = ""
        if '표준원재료명' in row and pd.notna(row['표준원재료명']):
            raw_text = str(row['표준원재료명'])
        elif 'RAWMTRL_NM' in row and pd.notna(row['RAWMTRL_NM']):
            raw_text = str(row['RAWMTRL_NM'])
            
        if not raw_text or raw_text == 'nan':
            continue
            
        found_spans = [] 
        
        # 텍스트 탐색
        for s in sweeteners_sorted:
            start = 0
            while True:
                pos = raw_text.find(s, start)
                if pos == -1:
                    break
                
                end = pos + len(s)
                
                # [수정] 교집합 기반 정확한 겹침 판별
                is_overlapping = any(
                    pos < existing_end and end > existing_start 
                    for existing_start, existing_end, _ in found_spans
                )
                
                if not is_overlapping:
                    found_spans.append((pos, end, s))
                    
                start = pos + 1

        # 원재료명에 적힌 순서대로 1차 정렬 (pos 기준)
        found_spans.sort(key=lambda x: x[0])
        
        # [추가] DB 다대다 매핑 무결성을 위한 중복 성분 코드 필터링
        # 앞쪽 순서에 등장한 타겟 성분만 취하고, 뒤에 나오는 동의어/파생어는 무시
        unique_ingredients = set()
        final_sequence_spans = []
        
        for pos, end, name in found_spans:
            target_code = ingredient_mapping[name]
            if target_code not in unique_ingredients:
                unique_ingredients.add(target_code)
                final_sequence_spans.append((pos, end, name, target_code))
        
        # Sequence 번호 부여
        for seq_num, (_, _, name, code) in enumerate(final_sequence_spans, start=1):
            mapping_data.append({
                "external_food_code": ext_code,
                "ingredient_code": code, 
                "ingredient_name": name,
                "sequence": seq_num  
            })

    # 8. 결과 저장
    product_ingredient_df = pd.DataFrame(mapping_data)
    product_ingredient_df.to_csv(output_file, index=False, encoding='utf-8-sig')

    print("\n" + "="*50)
    print(f"✅ 추출 완료! 총 {len(product_ingredient_df)}건의 매핑 데이터가 생성되었습니다.")
    print(f"✅ 저장 위치: {output_file}")
    print("="*50)
    print(product_ingredient_df.head(5))

if __name__ == "__main__":
    main()