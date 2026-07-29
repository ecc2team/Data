import sys
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

from src.config import DATA_DIR, OUTPUTS_DIR, ensure_dir

plt.rc('font', family='Malgun Gothic') 
plt.rcParams['axes.unicode_minus'] = False

CHARTS_DIR = OUTPUTS_DIR / "charts"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
ensure_dir(CHARTS_DIR)

def save_csv_safe(df: pd.DataFrame, filename: str) -> str:
    filepath = OUTPUTS_DIR / filename
    try:
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
        return str(filepath)
    except PermissionError:
        timestamp = datetime.now().strftime("%H%M%S")
        alt_name = str(filepath).replace(".csv", f"_{timestamp}.csv")
        df.to_csv(alt_name, index=False, encoding="utf-8-sig")
        return alt_name

def run_analysis_on_processed_data(input_path: str):
    df = pd.read_csv(input_path)
    
    # 1. 3단계 등급 체계 매핑
    conditions = [
        df["최종등급"] == 1,
        df["최종등급"] == 2,
        df["최종등급"] == 3
    ]
    choices = ["프리미엄 제로 (1등급)", "일반 제로 (2등급)", "가짜·주의 제로 (3등급)"]
    df["제로등급명"] = np.select(conditions, choices, default="분류 불가")

    type_counts = df["제로등급명"].value_counts()
    grade_1_df = df[df["최종등급"] == 1]
    grade_3_df = df[df["최종등급"] == 3]
    
    if "가짜제로_여부" not in df.columns:
        df["가짜제로_여부"] = (df["당류"] >= 0.5) | (df["에너지"] >= 5)
    
    fake_zero_df = grade_3_df[grade_3_df["가짜제로_여부"] == True] if not grade_3_df.empty else pd.DataFrame()

    print("\n" + "="*70)
    print(" [통계 데이터 요약] 등급별 당류(g) 및 에너지(kcal) 분포 상세 수치")
    print("="*70)
    
    sugar_stats = df.groupby("제로등급명")["당류"].agg([
        'count', 'mean', 'std', 'min', 
        lambda x: x.quantile(0.25), 'median', 
        lambda x: x.quantile(0.75), 'max'
    ])
    sugar_stats.columns = ['건수', '평균', '표준편차', '최소값', '25%(Q1)', '중앙값(Q2)', '75%(Q3)', '최대값']
    
    energy_stats = df.groupby("제로등급명")["에너지"].agg([
        'mean', 'std', 'min', 'median', 'max'
    ])
    energy_stats.columns = ['평균에너지', '표준편차', '최소에너지', '중앙사에너지', '최대에너지']
    
    print("\n[1] 당류(g) 분포 상세 수치")
    print(sugar_stats.round(2).to_string())
    
    print("\n" + "-"*70)
    print("\n[2] 에너지(kcal) 분포 상세 수치")
    print(energy_stats.round(2).to_string())
    print("="*70 + "\n")

    plt.figure(figsize=(16, 12))

    # [Subplot 1] 전체 제로 식품 등급 분포 파이 차트
    plt.subplot(2, 2, 1)
    colors_pie = ['#2ca02c', '#1f77b4', '#d62728'] 
    type_counts.plot.pie(autopct='%1.1f%%', startangle=90, colors=colors_pie)
    plt.title("전체 제로 표기 식품 등급 분포", fontsize=14)
    plt.ylabel('')

    # [Subplot 2] 3등급 최다 적발 카테고리 Top 5
    plt.subplot(2, 2, 2)
    top_categories = pd.Series(dtype=int)
    if "식품대분류" in grade_3_df.columns:
        top_categories = grade_3_df["식품대분류"].value_counts().head(5)
        if not top_categories.empty:
            sns.barplot(x=top_categories.values, y=top_categories.index, palette="Reds_r")
            plt.title("가짜·주의 제로(3등급) 최다 적발 카테고리 Top 5", fontsize=14)
            plt.xlabel("적발 건수")
            plt.ylabel("식품대분류")

    # [Subplot 3] 1등급(프리미엄) 제품의 고급 감미료 사용 빈도
    plt.subplot(2, 2, 3)
    sweeteners = ["알룰로스", "스테비아", "에리스리톨", "나한과", "스테비올배당체"]
    sw_counts = {sw: grade_1_df["RAWMTRL_NM"].astype(str).str.contains(sw, na=False).sum() for sw in sweeteners}
    sw_series = pd.Series(sw_counts).sort_values(ascending=False)
    sns.barplot(x=sw_series.values, y=sw_series.index, palette="Greens_r")
    plt.title("1등급(프리미엄) 제품의 고급 감미료 사용 빈도", fontsize=14)
    plt.xlabel("사용 건수")
    plt.ylabel("대체당 종류")

    # [Subplot 4] 3등급 제품의 당류 vs 칼로리 트랩 산점도
    plt.subplot(2, 2, 4)
    if not grade_3_df.empty and "당류" in grade_3_df.columns and "에너지" in grade_3_df.columns:
        sns.scatterplot(
            data=grade_3_df, 
            x="당류", 
            y="에너지", 
            hue="가짜제로_여부", 
            palette={True: '#d62728', False: '#ff7f0e'}, 
            alpha=0.7,
            s=60
        )
        plt.axvline(x=0.5, color='black', linestyle='--', label='당류 기준선 (0.5g)')
        plt.axhline(y=5, color='blue', linestyle='--', label='칼로리 기준선 (5kcal)')
        plt.title("3등급 제품의 당류 vs 칼로리 트랩 분포", fontsize=14)
        plt.xlabel("실제 당류량 (g)")
        plt.ylabel("에너지 (kcal)")
        plt.legend(loc='upper right', fontsize=9)
    else:
        plt.title("3등급 제품 데이터 없음", fontsize=14)

    plt.tight_layout()
    chart_path = CHARTS_DIR / "zero_grade_dashboard.png"
    plt.savefig(chart_path, dpi=300)
    plt.close()

    # 3. 콘솔 요약 리포트 출력
    print("\n" + "="*50)
    print(" [Zeropick 프로젝트 보고서용 데이터 요약]")
    print("="*50)
    print("1. 등급 분포:\n", type_counts.to_dict())
    if not top_categories.empty:
        print("2. 3등급 최다 카테고리 Top 5:\n", top_categories.to_dict())
    print("3. 1등급 고급 감미료 빈도:\n", sw_counts)
    if not fake_zero_df.empty:
        print(f"4. 가짜 제로 평균 스펙: 당류 평균 {fake_zero_df['당류'].mean():.2f}g, 칼로리 평균 {fake_zero_df['에너지'].mean():.2f}kcal")
    print("="*50 + "\n")
    
    return df

def export_fake_zero_blacklist(df: pd.DataFrame, output_name: str = "zero_blacklist_grade3.csv") -> pd.DataFrame:
    blacklist = df[df["최종등급"] == 3].copy()
    if blacklist.empty:
        return blacklist

    cols_to_keep = ["품목제조보고번호", "식품대분류", "식품명", "BSSH_NM", "당류", "에너지", "RAWMTRL_NM", "가짜제로_여부", "혈당트랩_여부", "첨가물트랩_여부"]
    blacklist = blacklist[[col for col in cols_to_keep if col in blacklist.columns]]
    blacklist.rename(columns={"BSSH_NM": "제조사", "당류": "실제 당류량(g)", "에너지": "칼로리(kcal)", "RAWMTRL_NM": "전체 원재료명"}, inplace=True)
    
    pattern_sugar = "|".join(["설탕", "물엿", "액상과당", "과당", "포도당", "조청", "당류가공품", "올리고당", "시럽", "벌꿀", "당밀", "원당", "흑설탕", "결정과당", "정제당"])
    blacklist["진짜당류_포함여부"] = blacklist["전체 원재료명"].astype(str).str.contains(pattern_sugar, na=False)

    sort_cols = [col for col in ["가짜제로_여부", "혈당트랩_여부", "실제 당류량(g)"] if col in blacklist.columns]
    if sort_cols:
        blacklist.sort_values(by=sort_cols, ascending=[False]*len(sort_cols), inplace=True)
    
    save_csv_safe(blacklist, output_name)
    return blacklist

if __name__ == "__main__":
    processed_data_file = PROCESSED_DATA_DIR / "zeropick_base_data_v4.csv"
    
    if not processed_data_file.exists():
        print(f"[에러] {processed_data_file} 파일이 없습니다. Merge 코드가 완료되었는지 확인하세요.")
    else:
        df_result = run_analysis_on_processed_data(processed_data_file)
        blacklist_df = export_fake_zero_blacklist(df_result)