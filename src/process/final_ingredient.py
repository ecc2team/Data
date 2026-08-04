import pandas as pd
import numpy as np

from src.config import DATA_DIR, ensure_dir

# ==========================================
# 지수 표기법 복구 함수 (이미 손상된 문자열 복구용)
# ==========================================
def fix_scientific_notation(val):
    if pd.isna(val):
        return val
    val_str = str(val).strip()
    try:
        # 2E+13 같은 형태를 다시 숫자로 폈다가 문자열로 변환
        return str(int(float(val_str)))
    except ValueError:
        return val_str

def main():
    print("🚀 대체당 및 트랩 성분 매핑 데이터 추출을 시작합니다...")

    # 2. 프로젝트 구조에 맞춘 파일 경로 설정
    interim_dir = DATA_DIR / "interim"
    processed_dir = DATA_DIR / "processed"
    ensure_dir(processed_dir)

    final_grade_file = processed_dir / "integrated_final_validation.csv"
    base_data_file = interim_dir / "zeropick_base_data_v4.csv"
    output_file = processed_dir / "product_ingredient_mapping.csv"

    if not final_grade_file.exists():
        raise FileNotFoundError(f"[에러] {final_grade_file} 파일이 없습니다.")
    if not base_data_file.exists():
        raise FileNotFoundError(f"[에러] {base_data_file} 파일이 없습니다.")

    # 3. 데이터 불러오기
    print("데이터를 불러오는 중...")
    final_df = pd.read_csv(final_grade_file, dtype=str)
    base_df = pd.read_csv(base_data_file, dtype=str)

    # 4. 스마트 조인(Merge) 키 감지 로직
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

    # Merge 전/후에 조인 키의 지수 표기법을 온전한 숫자로 복구
    final_df[left_key] = final_df[left_key].apply(fix_scientific_notation)
    base_df[right_key] = base_df[right_key].apply(fix_scientific_notation)

    # 5. 컬럼 충돌 방지 및 안전한 병합
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
    # [핵심 수정] 새로운 16종 마스터 매핑 딕셔너리 반영
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
    
    # 딕셔너리 키(한글명)를 기반으로 긴 단어부터 검색 (예: '효소처리스테비아'가 '스테비아'보다 먼저 검색되도록)
    sweeteners_sorted = sorted(sweetener_mapping.keys(), key=len, reverse=True)

    # 7. 제품별 대체당 매핑 추출
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
        
        # 텍스트 탐색 (중복 포함 방지)
        for s in sweeteners_sorted:
            start = 0
            while True:
                pos = raw_text.find(s, start)
                if pos == -1:
                    break
                
                end = pos + len(s)
                is_overlapping = any(
                    existing_start <= pos and end <= existing_end 
                    for existing_start, existing_end, _ in found_spans
                )
                
                if not is_overlapping:
                    found_spans.append((pos, end, s))
                    
                start = pos + 1

        # 원재료명에 적힌 순서대로 정렬
        found_spans.sort(key=lambda x: x[0])
        
        # Sequence 번호 부여
        for seq_num, (_, _, name) in enumerate(found_spans, start=1):
            mapping_data.append({
                "external_food_code": ext_code,
                "ingredient_code": sweetener_mapping[name], 
                "ingredient_name": name,
                "sequence": seq_num  
            })

    # 8. 결과 저장 (utf-8-sig로 저장하여 텍스트 에디터에서 한글 깨짐 방지)
    product_ingredient_df = pd.DataFrame(mapping_data)
    product_ingredient_df.to_csv(output_file, index=False, encoding='utf-8-sig')

    print("\n" + "="*50)
    print(f"✅ 추출 완료! 총 {len(product_ingredient_df)}건의 매핑 데이터가 생성되었습니다.")
    print(f"✅ 저장 위치: {output_file}")
    print("="*50)
    print(product_ingredient_df.head(5))

if __name__ == "__main__":
    main()