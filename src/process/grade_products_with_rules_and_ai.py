import pandas as pd
import numpy as np
import torch
import sys
from transformers import pipeline
import os

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

def run_zero_shot_comparison(df: pd.DataFrame, sample_size: int = None):
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
        device_name = f"CPU (디바이스 감지 예외: {e})"

    print(f"\n[Step 2] 다국어 Zero-shot 모델 로드 중... (사용 기기: {device_name})")
    
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
    
    match_rate = (target_df["룰기반_등급"] == target_df["AI_판정"]).mean() * 100
    print(f"\n[Step 2 결과] 룰 기반 vs AI 판정 일치율: {match_rate:.2f}%")
    
    return target_df

def integrate_and_revalidate(df_with_ai: pd.DataFrame):
    print("\n[Step 3] 통합 검증 (Rule + AI Cross Validation) 진행 중...")
    
    conditions = [
        (df_with_ai["최종등급"] == 3) & (df_with_ai["AI_판정"] == "Bad"),
        (df_with_ai["최종등급"] == 1) & (df_with_ai["AI_판정"] == "Good")
    ]
    choices = ["교차검증_확정_블랙리스트", "교차검증_확정_프리미엄"]
    df_with_ai["최종_통합판정"] = np.select(conditions, choices, default="일반_검토대상")
    
    summary = df_with_ai["최종_통합판정"].value_counts()
    print("\n[Step 3 결과] 최종 통합 판정 수치 집계:")
    print(summary.to_string())
    
    ensure_dir(OUTPUTS_DIR)
    output_path = OUTPUTS_DIR / "integrated_final_validation.csv"
    df_with_ai.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n파일 저장 완료: {output_path}")
    
    return df_with_ai

if __name__ == "__main__":
    INPUT_FILE = PROCESSED_DATA_DIR / "zeropick_base_data_v4.csv"
    
    print(f"파일 로딩 시도: {INPUT_FILE}")
    try:
        df = pd.read_csv(INPUT_FILE)
        print(f"데이터 로드 완료! (총 {len(df)}행)")
    except FileNotFoundError:
        print(f"[오류] '{INPUT_FILE}' 파일을 찾을 수 없습니다.")
        sys.exit(1)
        
    df_step1 = apply_rule_based_grading(df)
    df_step2 = run_zero_shot_comparison(df_step1, sample_size=None)
    df_step3 = integrate_and_revalidate(df_step2)
    
    print("\n=== 모든 작업이 정상 종료되었습니다 ===")