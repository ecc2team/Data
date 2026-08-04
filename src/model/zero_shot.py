import sys

import numpy as np
import pandas as pd
import torch
from transformers import pipeline

from src.config import DATA_DIR, OUTPUTS_DIR, ensure_dir

print("=== [시스템 실행 개시] 라이브러리 및 경로 설정 완료 ===")

def run_zero_shot_comparison(df: pd.DataFrame, sample_size: int = 200):
    """
    mDeBERTa 기반 Zero-shot 분류를 수행하고 룰 기반 평가와의 일치율을 계산합니다.
    """
    try:
        if torch.cuda.is_available():
            device = 0
            device_name = "CUDA (NVIDIA GPU - Colab T4 추천)"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = "mps"
            device_name = "MPS (Mac Apple Silicon)"
        else:
            device = -1
            device_name = "CPU"
    except Exception as e:
        device = -1
        device_name = f"CPU (디바이스 감지 예외: {e})"

    print(f"\n1. 다국어 Zero-shot 모델 로드 중... (사용 감지 기기: {device_name})")
    
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
    print(f"2. 총 {len(target_df)}개 제품 원재료에 대해 Zero-shot 판정 진행 중...")
    
    if "표준원재료명" in target_df.columns:
        raw_texts = target_df["표준원재료명"].fillna("").astype(str).str.strip()
    else:
        raw_texts = target_df["RAWMTRL_NM"].fillna("").astype(str).str.strip()
        
    valid_mask = raw_texts != ""
    texts_to_infer = raw_texts[valid_mask].str.slice(0, 250).tolist()
    
    batch_results = []
    if texts_to_infer:
        print(f"   └ 유효 텍스트 {len(texts_to_infer)}건 추론 시작 (Batch Size: 16)...")
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
        print(f"\n[Step 3 결과] 룰 기반 vs AI 판정 일치율: {match_rate:.2f}%")
    else:
        print("\n[Step 3 안내] '룰기반_등급' 컬럼이 없어 일치율 계산을 스킵합니다.")
        
    return target_df

def integrate_and_revalidate(df_with_ai: pd.DataFrame):
    print("\n3. 통합 검증 (Rule + AI Cross Validation) 진행 중...")
    
    rule_col = "제로유형" if "제로유형" in df_with_ai.columns else None
    
    if rule_col:
        conditions = [
            (df_with_ai[rule_col] == "무늬만 제로 (Type B)") & (df_with_ai["AI_판정"] == "Bad"),
            (df_with_ai[rule_col] == "진짜 제로 (Type A)") & (df_with_ai["AI_판정"] == "Good")
        ]
        choices = ["교차검증_확정_블랙리스트", "교차검증_확정_화이트리스트"]
        df_with_ai["최종_통합판정"] = np.select(conditions, choices, default="일반/검토대상")
    else:
        print("   └ '제로유형' 컬럼을 찾지 못해 AI 판정 기준으로 단순 매핑합니다.")
        df_with_ai["최종_통합판정"] = df_with_ai["AI_판정"]
    
    summary = df_with_ai["최종_통합판정"].value_counts()
    print("\n[Step 4 결과] 최종 통합 판정 수치 집계:")
    print(summary)
    
    ensure_dir(OUTPUTS_DIR)
    output_path = OUTPUTS_DIR / "integrated_final_validation.csv"
    df_with_ai.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n{output_path} 저장 완료!")
    
    return df_with_ai

if __name__ == "__main__":
    # 입력 파일 경로 설정 (outputs/ 또는 data/processed/ 중 실제 파일이 있는 곳 확인)
    INPUT_FILE = OUTPUTS_DIR / "zeropick_final_graded.csv" 
    
    # 만약 outputs에 없다면 processed 폴더도 함께 탐색
    if not INPUT_FILE.exists():
        alt_input = DATA_DIR / "processed" / "zeropick_final_graded.csv"
        if alt_input.exists():
            INPUT_FILE = alt_input

    print(f"파일 로딩 시도: {INPUT_FILE}")
    try:
        df = pd.read_csv(INPUT_FILE)
        print(f"데이터 로드 완료! (총 {len(df)}행)")
    except FileNotFoundError:
        print(f"[오류] '{INPUT_FILE}' 파일을 찾을 수 없습니다. 이전 단계(룰 기반 등급 분류)가 정상 실행되어 파일이 생성되었는지 확인해 주세요.")
        sys.exit(1)
        
    df_step3 = run_zero_shot_comparison(df, sample_size=200)
    df_step4 = integrate_and_revalidate(df_step3)
    print("\n=== 모든 작업이 정상 종료되었습니다 ===")