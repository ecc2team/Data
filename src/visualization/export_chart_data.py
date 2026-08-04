import pandas as pd

from src.config import DATA_DIR

PROCESSED_DIR = DATA_DIR / "processed"

def export_chart_datasets():
    # 1순위: 등급 정보가 포함된 base_data_v4 파일 지정
    input_path = PROCESSED_DIR / "zeropick_base_data_v4.csv"
    if not input_path.exists():
        input_path = PROCESSED_DIR / "integrated_final_validation.csv"
    
    if not input_path.exists():
        print(f"[오류] 데이터 파일을 찾을 수 없습니다. 경로를 확인해주세요: {PROCESSED_DIR}")
        return

    df = pd.read_csv(input_path)
    print(f"데이터 로드 완료: {input_path.name} (총 {len(df):,}행)")

    # 컬럼명 유연성 확보 ('최종등급'이 없으면 대체 컬럼 탐색)
    grade_col = None
    for col in ["최종등급", "grade", "판정등급", "v4_grade"]:
        if col in df.columns:
            grade_col = col
            break

    if grade_col is None:
        print(f"[오류] 등급을 나타내는 컬럼을 찾을 수 없습니다. 현재 파일의 컬럼 목록: {df.columns.tolist()}")
        return

    # -------------------------------------------------------------
    # Chart 1: 3등급(위험/가짜 제로) 제품들의 카테고리별 칼로리/당류 분포 분석
    # -------------------------------------------------------------
    grade_3_df = df[df[grade_col] == 3].copy()
    if not grade_3_df.empty:
        grade_3_df["고위험_이상치"] = (grade_3_df["당류"] >= 0.5) | (grade_3_df["에너지"] >= 100)
        
        cols_chart1 = ["품목제조보고번호", "식품대분류", "식품명", "당류", "에너지", "고위험_이상치"]
        chart1_df = grade_3_df[[col for col in cols_chart1 if col in grade_3_df.columns]]
        
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        chart1_output = PROCESSED_DIR / "chart1_scatter_data.csv"
        chart1_df.to_csv(chart1_output, index=False, encoding="utf-8-sig")
        print(f"✅ Chart 1 데이터 저장 완료: {chart1_output} (총 {len(chart1_df):,}행)")
    else:
        print("[경고] 3등급(위험/가짜 제로)으로 분류된 데이터가 없습니다.")

    # -------------------------------------------------------------
    # Chart 2: 카테고리별 대체당 사용 빈도 (히트맵용)
    # -------------------------------------------------------------
    sweeteners = ["알룰로스", "스테비아", "에리스리톨", "나한과", "스테비올배당체", "수크랄로스", "아세설팜칼륨", "아스파탐"]
    
    chart2_rows = []
    if "식품대분류" in df.columns and "RAWMTRL_NM" in df.columns:
        for category, group in df.groupby("식품대분류"):
            for sw in sweeteners:
                count = group["RAWMTRL_NM"].astype(str).str.contains(sw, na=False).sum()
                chart2_rows.append({
                    "식품대분류": category,
                    "대체당": sw,
                    "건수": count
                })
        
        chart2_df = pd.DataFrame(chart2_rows)
        chart2_output = PROCESSED_DIR / "chart2_sweetener_trend.csv"
        chart2_df.to_csv(chart2_output, index=False, encoding="utf-8-sig")
        print(f"✅ Chart 2 데이터 저장 완료: {chart2_output}")

if __name__ == "__main__":
    export_chart_datasets()