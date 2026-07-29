import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime

from path_config import DATA_DIR, OUTPUTS_DIR, CHARTS_DIR, ensure_dir

plt.rc('font', family='Malgun Gothic') 
plt.rcParams['axes.unicode_minus'] = False

def save_csv_safe(df: pd.DataFrame, filename: str) -> str:
    try:
        df.to_csv(filename, index=False, encoding="utf-8-sig")
        return filename
    except PermissionError:
        timestamp = datetime.now().strftime("%H%M%S")
        alt_name = filename.replace(".csv", f"_{timestamp}.csv")
        df.to_csv(alt_name, index=False, encoding="utf-8-sig")
        print(f"[알림] 엑셀이 열려 있어 '{alt_name}'으로 대체 저장했습니다.")
        return alt_name

def load_and_group_c002(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"PRDLST_REPORT_NO": str}, low_memory=False)
    df["PRDLST_REPORT_NO"] = df["PRDLST_REPORT_NO"].astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    
    if "CHNG_DT" in df.columns:
        df = df.sort_values(["CHNG_DT", "RAWMTRL_ORDNO"], na_position="first")
        df = df.drop_duplicates(subset=["PRDLST_REPORT_NO", "RAWMTRL_NM"], keep="last")
    
    agg_funcs = {
        "PRDLST_NM": "first", "BSSH_NM": "first", "PRDLST_DCNM": "first",
        "RAWMTRL_NM": lambda x: ", ".join(x.dropna().astype(str).unique())
    }
    df_grouped = df.groupby("PRDLST_REPORT_NO", as_index=False).agg(agg_funcs)
    return df_grouped.rename(columns={"PRDLST_REPORT_NO": "품목제조보고번호"})

def run_analysis(nutrition_path: str, c002_raw_path: str, sugar_threshold: float = 0.5):
    nutrition = pd.read_csv(nutrition_path, dtype={"품목제조보고번호": str})
    nutrition["품목제조보고번호"] = nutrition["품목제조보고번호"].astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    nutrition = nutrition.drop_duplicates(subset=["품목제조보고번호"], keep="first")
    
    c002_grouped = load_and_group_c002(c002_raw_path)
    
    pattern = "|".join(["제로", "슈가프리", "무설탕"])
    nutrition["제품명_강한제로표기"] = nutrition["식품명"].str.contains(pattern, na=False)

    df_merged = nutrition.merge(c002_grouped, on="품목제조보고번호", how="inner")
    df = df_merged.dropna(subset=["당류"]).copy()

    df["제로유형"] = "일반 식품"
    df.loc[df["당류"] < sugar_threshold, "제로유형"] = "진짜 제로 (Type A)"
    
    type_b_condition = (df["제품명_강한제로표기"] == True) & (df["당류"] >= sugar_threshold)
    df.loc[type_b_condition, "제로유형"] = "무늬만 제로 (Type B)"

    type_counts = df["제로유형"].value_counts()
    type_b_df = df[df["제로유형"] == "무늬만 제로 (Type B)"]
    
    plt.figure(figsize=(15, 10))

    plt.subplot(2, 2, 1)
    type_counts.plot.pie(autopct='%1.1f%%', startangle=90, colors=['#d3d3d3', '#2ca02c', '#d62728'])
    plt.title("전체 식품 중 제로 표기 실태")
    plt.ylabel('')

    plt.subplot(2, 2, 2)
    top_categories = type_b_df["식품대분류"].value_counts().head(5)
    if not top_categories.empty:
        sns.barplot(x=top_categories.values, y=top_categories.index, hue=top_categories.index, palette="Reds_r", legend=False)
    plt.title("'무늬만 제로'가 가장 많은 카테고리 Top 5")

    plt.subplot(2, 2, 3)
    type_a_df = df[df["제로유형"] == "진짜 제로 (Type A)"]
    sweeteners = ["수크랄로스", "에리스리톨", "알룰로스", "스테비아", "아스파탐"]
    sw_counts = {sw: type_a_df["RAWMTRL_NM"].str.contains(sw, na=False).sum() for sw in sweeteners}
    sw_series = pd.Series(sw_counts).sort_values(ascending=False)
    sns.barplot(x=sw_series.values, y=sw_series.index, hue=sw_series.index, palette="Greens_r", legend=False)
    plt.title("'진짜 제로' 제품의 주요 대체당 사용 빈도")

    plt.subplot(2, 2, 4)
    if not type_b_df.empty:
        sns.histplot(type_b_df["당류"], bins=20, color="red", kde=True)
        plt.axvline(x=0.5, color='black', linestyle='--', label='제로 기준(0.5g)')
    plt.title("'무늬만 제로' 제품들의 실제 당류 분포")
    plt.legend()

    plt.tight_layout()
    ensure_dir(CHARTS_DIR)
    plt.savefig(CHARTS_DIR / "zero_trend_dashboard.png", dpi=300)
    plt.show()

    print("\n" + "="*50)
    print(" [ChatGPT 시각화 요청용 수치 데이터 복사 영역]")
    print("="*50)
    print("1. 표기 실태:\n", type_counts.to_dict())
    print("2. 무늬만 제로 카테고리 Top 5:\n", top_categories.to_dict())
    print("3. 대체당 사용 빈도:\n", sw_counts)
    if not type_b_df.empty:
        print(f"4. 무늬만 제로 당류 분포:\n 최소 {type_b_df['당류'].min()}g, 최대 {type_b_df['당류'].max()}g, 평균 {type_b_df['당류'].mean():.2f}g")
    print("="*50 + "\n")
    
    return df

def export_fake_zero_blacklist(df: pd.DataFrame, output_path: str = "fake_zero_blacklist.csv") -> pd.DataFrame:
    blacklist = df[df["제로유형"] == "무늬만 제로 (Type B)"].copy()
    if len(blacklist) == 0:
        return blacklist

    cols_to_keep = ["품목제조보고번호", "식품대분류", "식품명", "BSSH_NM", "당류", "RAWMTRL_NM"]
    blacklist = blacklist[[col for col in cols_to_keep if col in blacklist.columns]]
    blacklist.rename(columns={"BSSH_NM": "제조사", "당류": "실제 당류량(g)", "RAWMTRL_NM": "전체 원재료명"}, inplace=True)
    
    if "실제 당류량(g)" in blacklist.columns:
        blacklist.sort_values(by="실제 당류량(g)", ascending=False, inplace=True)
    
    save_csv_safe(blacklist, output_path)
    return blacklist

if __name__ == "__main__":
    print("데이터 처리 및 분석 중...")
    df_result = run_analysis(DATA_DIR / "food_nutrition_raw.csv", DATA_DIR / "prdlst_rawmtrl_raw.csv")
    blacklist_df = export_fake_zero_blacklist(df_result)
    
    if len(blacklist_df) > 0:
        pattern_sugar = "|".join(["설탕", "물엿", "액상과당", "과당", "포도당", "조청",
    "당류가공품", "올리고당", "시럽", "벌꿀", "당밀", "원당",
    "흑설탕", "결정과당", "정제당"])
        blacklist_df["진짜당류_포함여부"] = blacklist_df["전체 원재료명"].str.contains(pattern_sugar, na=False)
        saved_file = save_csv_safe(blacklist_df, "fake_zero_blacklist_with_factcheck.csv")
        print(f"블랙리스트 저장 완료 ({saved_file})")