"""
룰 기반 등급 라벨링 스크립트.

기존 grade_products_with_rules_and_ai.py에서 zero-shot AI 교차검증 단계를
제거한 버전. 이유:
- zero-shot(mDeBERTa) 판정은 애초에 룰기반_등급을 대체하지 않고 참고용
  일치율만 계산했음 (product.grade로 DB에 들어가는 값은 항상 룰기반_등급).
- 로컬 CPU 환경에서 zero-shot 추론이 오래 걸리는데, 데이터가 1,698건까지
  줄어든 상황에서는 그 비용 대비 얻는 검증 가치가 낮음. 이 정도 건수는
  zeropick_blacklist_candidates.csv(최종등급 3만 따로 뽑은 파일)를 사람이
  직접 훑어보는 게 더 빠르고 확실함.
- 그래서 Step 1(룰 기반 라벨링)만 남기고, Step 2/3(zero-shot 추론 및
  교차검증 라벨)는 제거함. torch/transformers 의존성도 더 이상 필요 없음.

입력: data/processed/zeropick_base_data_v4.csv (최종등급 컬럼 필요)
출력: data/processed/integrated_final_validation.csv
      (컬럼명은 다음 단계 스크립트와의 호환을 위해 그대로 유지 —
       prepare_product_table_data.py / build_product_ingredient_mapping.py가
       이 파일명과 룰기반_등급 컬럼을 그대로 참조함)
"""

import sys
import os
import numpy as np
import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from src.config import OUTPUTS_DIR, DATA_DIR, ensure_dir

PROCESSED_DATA_DIR = DATA_DIR / "processed"


def apply_rule_based_grading(df: pd.DataFrame) -> pd.DataFrame:
    print("\n[Step 1] v4 로직 기반 등급 맵핑 진행 중...")

    if "최종등급" not in df.columns:
        print("[경고] '최종등급' 컬럼이 없습니다. 이전 스크립트가 정상적으로 실행되었는지 확인하세요.")
        sys.exit(1)

    conditions = [
        df["최종등급"] == 1,
        df["최종등급"] == 2,
        df["최종등급"] == 3
    ]

    grade_choices = ["Good", "보통", "Bad"]
    type_choices = ["프리미엄 제로 (Type S)", "일반 제로 (Type A)", "무늬만 제로/트랩 (Type B)"]

    df["룰기반_등급"] = np.select(conditions, grade_choices, default="보통")
    df["제로유형"] = np.select(conditions, type_choices, default="미상")

    print("  분류 결과 집계:")
    print(df["제로유형"].value_counts().to_string())

    return df


if __name__ == "__main__":
    INPUT_FILE = PROCESSED_DATA_DIR / "zeropick_base_data_v4.csv"

    print(f"파일 로딩 시도: {INPUT_FILE}")
    try:
        df = pd.read_csv(INPUT_FILE)
        print(f"데이터 로드 완료! (총 {len(df)}행)")
    except FileNotFoundError:
        print(f"[오류] '{INPUT_FILE}' 파일을 찾을 수 없습니다.")
        sys.exit(1)

    df_result = apply_rule_based_grading(df)

    ensure_dir(PROCESSED_DATA_DIR)
    output_path = PROCESSED_DATA_DIR / "integrated_final_validation.csv"
    df_result.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n파일 저장 완료: {output_path}")

    print("\n=== 모든 작업이 정상 종료되었습니다 ===")
    print("\n※ 최종등급 3(Bad) 상품은 zeropick_blacklist_candidates.csv에서")
    print("  별도로 눈으로 검토하는 것을 권장합니다.")