import sys
from pathlib import Path

# 1. ModuleNotFoundError 원천 차단
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

import pandas as pd
from src.config import DATA_DIR, ensure_dir

def main():
    print("🚀 대체당 매핑 데이터 추출을 시작합니다...")

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

    # 4. 스마트 조인(Merge) 키 감지 로직 (KeyError 원천 차단)
    id_candidates = ['품목제조보고번호', 'external_food_code', '식품코드', 'PRDLST_REPORT_NO']
    
    # 두 데이터프레임에 공통으로 있는 식별자(예: 품목제조보고번호)를 최우선으로 찾음
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

    # 5. 컬럼 충돌 방지 및 안전한 병합
    merge_cols = [right_key]
    if 'RAWMTRL_NM' in base_df.columns and 'RAWMTRL_NM' not in final_df.columns:
        merge_cols.append('RAWMTRL_NM')
    if '표준원재료명' in base_df.columns and '표준원재료명' not in final_df.columns:
        merge_cols.append('표준원재료명')

    # 원재료명 컬럼이 final_df에 없는 경우에만 병합 수행
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
        # 이미 final_df 안에 원재료명이 포함되어 있다면 병합 생략
        merged_df = final_df

    # 6. 추출할 대체당 목록 
    sweeteners = [
        "에리스리톨", "수크랄로스", "스테비아", "알룰로스", 
        "아스파탐", "아세설팜칼륨", "사카린", "나한과", 
        "말티톨", "소르비톨", "자일리톨", "효소처리스테비아"
    ]
    # 긴 단어부터 검색하여 '효소처리스테비아' 중복 감지 방지
    sweeteners_sorted = sorted(sweeteners, key=len, reverse=True)

    # 7. 제품별 대체당 매핑 추출
    print("원재료명에서 대체당을 추출하고 순서를 부여하는 중...")
    mapping_data = []

    for index, row in merged_df.iterrows():
        ext_code = row[left_key]
        
        # 원재료명 텍스트 추출 (표준원재료명 우선)
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