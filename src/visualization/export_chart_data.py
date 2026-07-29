import pandas as pd

from src.config import CHARTS_DIR, DATA_DIR, OUTPUTS_DIR, ensure_dir
from src.process.merge_whitelist_v4 import build_base_dataset

SUGAR_THRESHOLD = 0.5

SWEETENER_SYNONYMS = {
    "스테비아": ["스테비아", "스테비올배당체"],
    "에리스리톨": ["에리스리톨"],
    "알룰로스": ["알룰로스", "알룰로오스"],
    "나한과": ["나한과", "나한과추출물"],
    "수크랄로스": ["수크랄로스"],
    "아스파탐": ["아스파탐"],
    "말티톨": ["말티톨"],
    "자일리톨": ["자일리톨"],
    "이소말트": ["이소말트"],
    "아세설팜칼륨": ["아세설팜칼륨", "아세설팜K"],
}


def load_filtered_base_dataset() -> pd.DataFrame:
    base_path = OUTPUTS_DIR / "zeropick_base_data_v4.csv"
    if not base_path.exists():
        print(f"[chart data] 기준 데이터가 없어 새로 생성합니다: {base_path}")
        base_df = build_base_dataset(DATA_DIR / "food_nutrition_raw.csv", DATA_DIR / "prdlst_rawmtrl_raw.csv")
        base_df.to_csv(base_path, index=False, encoding="utf-8-sig")
        print(f"[chart data] 생성 완료: {base_path} ({len(base_df)}행)")
    else:
        print(f"[chart data] 기존 기준 데이터 사용: {base_path}")

    df = pd.read_csv(base_path, dtype={"품목제조보고번호": str}, low_memory=False)
    for col in ["당류", "에너지"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.dropna(subset=["당류", "에너지"]).copy()


def main():
    df = load_filtered_base_dataset()

    zero = df[df["당류"] < SUGAR_THRESHOLD].copy()
    zero["칼로리이상치"] = False
    for cat, group in zero.groupby("식품대분류"):
        cutoff = group["에너지"].quantile(0.90)
        zero.loc[group.index, "칼로리이상치"] = group["에너지"] >= cutoff

    scatter_cols = ["식품명", "식품대분류", "당류", "에너지", "칼로리이상치"]
    ensure_dir(CHARTS_DIR)
    zero[scatter_cols].to_csv(CHARTS_DIR / "chart1_scatter_data.csv", index=False, encoding="utf-8-sig")
    print(f"[1] {CHARTS_DIR / 'chart1_scatter_data.csv'} 저장 ({len(zero)}행)")
    print(f"    칼로리 이상치(카테고리 내 상위 10%): {zero['칼로리이상치'].sum()}개")

    ingredient_col = "표준원재료명" if "표준원재료명" in df.columns else "RAWMTRL_NM"
    rows = []
    for cat, group in df.groupby("식품대분류"):
        for canonical, synonyms in SWEETENER_SYNONYMS.items():
            pattern = "|".join(synonyms)
            count = group[ingredient_col].astype(str).str.contains(pattern, na=False).sum()
            if count > 0:
                rows.append({
                    "식품대분류": cat,
                    "대체당": canonical,
                    "건수": count,
                    "비율(%)": round(count / len(group) * 100, 1),
                })

    trend_df = pd.DataFrame(rows).sort_values(["식품대분류", "건수"], ascending=[True, False])
    trend_df.to_csv(CHARTS_DIR / "chart2_sweetener_trend.csv", index=False, encoding="utf-8-sig")
    print(f"\n[2] chart2_sweetener_trend.csv 저장")
    print(trend_df.pivot(index="식품대분류", columns="대체당", values="건수").fillna(0).astype(int))


if __name__ == "__main__":
    main()