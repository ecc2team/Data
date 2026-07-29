import pandas as pd
import numpy as np
import torch
import sys
import re
from transformers import pipeline

from src.config import OUTPUTS_DIR, ensure_dir

print("=== [시스템 실행 개시] 라이브러리 로드 완료 ===")

# --- 룰 기반 분류를 위한 키워드 설정 ---
# 인공 감미료 (보수적 접근: Bad 로 분류할 타겟)
RULE_BAD_SWEETENERS = ["수크랄로스", "아세설팜칼륨", "아스파탐", "사카린", "말티톨"]
# 천연/대체당 (긍정적 접근: Good 으로 분류할 타겟)
RULE_GOOD_SWEETENERS = ["알룰로스", "에리스리톨", "스테비아", "나한과", "효소처리스테비아"]


def apply_rule_based_grading(df: pd.DataFrame) -> pd.DataFrame:
    """
    원재료명(RAWMTRL_NM)에 포함된 감미료 키워드를 기반으로 
    1차적인 '룰기반_등급'과 '제로유형'을 부여합니다.
    """
    print("\n[Step 1] 룰 기반(Rule-based) 원재료 사전 분류 진행 중...")
    
    bad_pattern = "|".join(RULE_BAD_SWEETENERS)
    good_pattern = "|".join(RULE_GOOD_SWEETENERS)
    
    def get_rule_grade(text):
        if not isinstance(text, str) or text.strip() == "":
            return "보통"
        
        has_bad = bool(re.search(bad_pattern, text))
        has_good = bool(re.search(good_pattern, text))
        
        # 인공 감미료(Bad)가 하나라도 들어가면 일단 Bad로 편입 (보수적 룰)
        if has_bad:
            return "Bad"
        elif has_good:
            return "Good"
        else:
            return "보통"
            
    df["룰기반_등급"] = df["RAWMTRL_NM"].apply(get_rule_grade)
    
    # 룰기반 등급에 따른 제로유형 매핑 (이모지 및 특수문자 철저히 배제)
    conditions = [
        df["룰기반_등급"] == "Bad",
        df["룰기반_등급"] == "Good"
    ]
    choices = ["무늬만 제로 (Type B)", "진짜 제로 (Type A)"]
    df["제로유형"] = np.select(conditions, choices, default="일반 제로")
    
    print("  분류 결과 집계:")
    print(df["제로유형"].value_counts().to_string())
    
    return df


def run_zero_shot_comparison(df: pd.DataFrame, sample_size: int = None):
    """
    mDeBERTa 기반 Zero-shot 분류를 수행하고 룰 기반 평가와의 일치율을 계산합니다.
    """
    try:
        if torch.cuda.is_available():
            device = 0
            device_name = "CUDA (NVIDIA GPU)"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = "mps"
            device_name = "MPS (Mac Apple Silicon)"
        else:
            device = -1
            device_name = "CPU"
    except Exception as e:
        device = -1
        device_name = f"CPU (디바이스 감지 예외로 인한 fallback: {e})"

    print(f"\n[Step 2] 다국어 Zero-shot 모델 로드 중... (사용 감지 기기: {device_name})")
    
    classifier = pipeline(
        "zero-shot-classification", 
        model="MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",
        device=device
    )
    
    candidate_labels = ["건강에 좋은 원재료", "보통 수준의 원재료", "당류 및 인공첨가물이 많은 원재료"]
    label_mapping = {
        "건강에 좋은 원재료": "Good",
        "보통 수준의 원재료": "보통",
        "당류 및 인공첨가물이 많은 원재료": "Bad"
    }
    
    target_df = df.sample(n=min(sample_size, len(df)), random_state=42).copy() if sample_size else df.copy()
    print(f"  총 {len(target_df)}개 제품 원재료에 대해 Zero-shot 판정 진행 중...")
    
    if "표준원재료명" in target_df.columns:
        raw_texts = target_df["표준원재료명"].fillna("").astype(str).str.strip()
    else:
        raw_texts = target_df["RAWMTRL_NM"].fillna("").astype(str).str.strip()
        
    valid_mask = raw_texts != ""
    texts_to_infer = raw_texts[valid_mask].str.slice(0, 250).tolist()
    
    batch_results = []
    if texts_to_infer:
        print(f"  유효 텍스트 {len(texts_to_infer)}건 추론 시작 (Batch Size: 16)...")
        results = classifier(texts_to_infer, candidate_labels, batch_size=16)
        
        if isinstance(results, dict):
            results = [results]
            
        batch_results = [label_mapping[res['labels'][0]] for res in results]
    
    ai_results = []
    result_idx = 0
    for is_valid in valid_mask:
        if is_valid:
            ai_results.append(batch_results[result_idx])
            result_idx += 1
        else:
            ai_results.append("보통")
            
    target_df["AI_판정"] = ai_results
    
    if "룰기반_등급" in target_df.columns:
        match_rate = (target_df["룰기반_등급"] == target_df["AI_판정"]).mean() * 100
        print(f"\n[Step 2 결과] 룰 기반 vs AI 판정 일치율: {match_rate:.2f}%")
        
    return target_df


def integrate_and_revalidate(df_with_ai: pd.DataFrame):
    """
    룰 기반 판정과 AI 판정을 교차 검증하여 최종 통합 판정을 내립니다.
    (데이터에는 어떠한 이모지나 시각적 장식도 들어가지 않음)
    """
    print("\n[Step 3] 통합 검증 (Rule + AI Cross Validation) 진행 중...")
    
    rule_col = "제로유형" if "제로유형" in df_with_ai.columns else None
    
    if rule_col:
        conditions = [
            (df_with_ai[rule_col] == "무늬만 제로 (Type B)") & (df_with_ai["AI_판정"] == "Bad"),
            (df_with_ai[rule_col] == "진짜 제로 (Type A)") & (df_with_ai["AI_판정"] == "Good")
        ]
        # 데이터베이스/CSV에 저장될 순수 텍스트 값
        choices = ["교차검증_확정_블랙리스트", "교차검증_확정_화이트리스트"]
        df_with_ai["최종_통합판정"] = np.select(conditions, choices, default="일반_검토대상")
    else:
        df_with_ai["최종_통합판정"] = df_with_ai["AI_판정"]
    
    summary = df_with_ai["최종_통합판정"].value_counts()
    print("\n[Step 3 결과] 최종 통합 판정 수치 집계:")
    print(summary.to_string())
    
    ensure_dir(OUTPUTS_DIR)
    output_path = OUTPUTS_DIR / "integrated_final_validation.csv"
    df_with_ai.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n파일 저장 완료: {output_path}")
    
    return df_with_ai


if __name__ == "__main__":
    # 방금 생성된 v4 병합 베이스 파일로 입력 타겟 수정
    INPUT_FILE = OUTPUTS_DIR / "zeropick_base_data_v4.csv"             
    
    print(f"파일 로딩 시도: {INPUT_FILE}")
    try:
        df = pd.read_csv(INPUT_FILE)
        print(f"데이터 로드 완료! (총 {len(df)}행)")
    except FileNotFoundError:
        print(f"[오류] '{INPUT_FILE}' 파일을 찾을 수 없습니다.")
        sys.exit(1)
        
    # 1. 룰 기반 사전 분류 실행 (키워드 매칭)
    df_step1 = apply_rule_based_grading(df)
    
    # 2. AI 제로샷 판정 (949개 전체 처리 위해 sample_size=None 적용)
    df_step2 = run_zero_shot_comparison(df_step1, sample_size=None)
    
    # 3. 교차 검증 및 최종 결과물 생성
    df_step3 = integrate_and_revalidate(df_step2)
    print("\n=== 모든 작업이 정상 종료되었습니다 ===")