"""
영양DB(food_nutrition_raw.csv, 카테고리 3종 통합) + 식품안전나라 C002(prdlst_rawmtrl_raw.csv)를
품목제조보고번호 기준으로 병합해 '제로슈거 화이트리스트'를 만든다.

v4.1 변경점:
- 당류 < 0.5g 뿐만 아니라 에너지(kcal) < 5kcal 조건을 동시 적용하여 실질적인 제로 칼로리/슈거만 타겟팅.
- 대체당(에리스리톨, 수크랄로스 등)이 전혀 포함되지 않았고 '제로' 표기도 없는 
  일반 블랙커피, 생수, 차(Natural Zero) 등을 필터링하여 AI 판정 보류 최소화.
"""

import re
from collections import Counter

import pandas as pd

from src.config import DATA_DIR, OUTPUTS_DIR, ensure_dir

try:
    from sentence_transformers import SentenceTransformer
    from sklearn.cluster import AgglomerativeClustering
except Exception:
    SentenceTransformer = None
    AgglomerativeClustering = None

STRICT_ZERO_KEYWORDS = ["제로", "슈가프리", "무설탕", "0kcal", "영칼로리"]                      
ADDED_SUGAR_FREE_KEYWORDS = ["무가당"]
SUGAR_THRESHOLD = 0.5

# ✅ 대표적인 대체당/감미료 키워드 리스트 (자연 무당 제품 필터링용)
ARTIFICIAL_SWEETENERS = [
    "에리스리톨", "수크랄로스", "스테비아", "알룰로스", 
    "아스파탐", "아세설팜칼륨", "사카린", "나한과", 
    "말티톨", "소르비톨", "자일리톨", "효소처리스테비아"
]

def normalize_key(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)


def add_label_flags(df: pd.DataFrame) -> pd.DataFrame:
    strict_pattern = "|".join(STRICT_ZERO_KEYWORDS)
    added_pattern = "|".join(ADDED_SUGAR_FREE_KEYWORDS)
    df["제품명_강한제로표기"] = df["식품명"].str.contains(strict_pattern, na=False)
    df["제품명_무가당표기"] = df["식품명"].str.contains(added_pattern, na=False)
    return df


def load_nutrition(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"품목제조보고번호": str})
    df["품목제조보고번호"] = normalize_key(df["품목제조보고번호"])

    missing_key = df["품목제조보고번호"].isna().sum()
    if missing_key:
        print(f"[nutrition] 품목제조보고번호 결측이라 조인 불가능한 행: {missing_key}개 (제외)")
    df = df.dropna(subset=["품목제조보고번호"])

    df = add_label_flags(df)

    print(f"[nutrition] 카테고리 통합 전체: {len(df)}행")
    if "식품대분류" in df.columns:
        print(df["식품대분류"].value_counts().to_string())
    return df


def filter_zero_sugar(df: pd.DataFrame, threshold: float = SUGAR_THRESHOLD) -> pd.DataFrame:
    total = len(df)
    
    # 1. 당류 결측치(NaN) 제외
    valid = df[df["당류"].notna()]
    nan_count = total - len(valid)
    
    # 2. 식약처 무당/무열량 기준 적용 (당류 0.5g 미만 AND 에너지 5kcal 미만)
    is_zero_sugar = valid["당류"] < threshold
    # 에너지가 결측치(NaN)인 경우 안전하게 0으로 간주
    is_zero_calorie = valid["에너지"].fillna(0) < 5.0 
    
    # 두 조건을 모두 만족하는 제품만 True
    is_zero = is_zero_sugar & is_zero_calorie
    zero_sugar = valid[is_zero]

    print(f"\n[당류 및 에너지(칼로리) 필터] 전체 {total}행")
    print(f"  - 당류 결측(NaN, 판단 불가): {nan_count}개 ({nan_count/total*100:.1f}%) -> 제외")
    print(f"  - 당류 >= {threshold}g 또는 에너지 >= 5kcal: {(~is_zero).sum()}개 -> 제외")
    print(f"  - 제로슈거/칼로리 후보(당류 < {threshold}g & 에너지 < 5kcal): {len(zero_sugar)}개")

    print("\n[조건 B 참고 - 제품명 표기 vs 실제 영양성분 기준]")
    fake_zero = valid["제품명_강한제로표기"] & ~is_zero
    unlabeled_zero = ~valid["제품명_강한제로표기"] & is_zero
    print(f"  강한제로 표기인데 기준(당류/에너지) 미달 ('무늬만 제로' 후보): {fake_zero.sum()}개")
    print(f"  강한제로 표기는 없는데 기준 통과 (표기 안 된 자연 제로): {unlabeled_zero.sum()}개")

    return zero_sugar


def load_c002(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"PRDLST_REPORT_NO": str}, low_memory=False)
    df["PRDLST_REPORT_NO"] = normalize_key(df["PRDLST_REPORT_NO"])
    print(f"\n[C002] 원본: {len(df)}행")

    if "CHNG_DT" in df.columns:
        na_chng = df["CHNG_DT"].isna().sum()
        if na_chng:
            print(f"  CHNG_DT 결측: {na_chng}개")
        
        df = df.sort_values(["CHNG_DT", "RAWMTRL_ORDNO"], na_position="first")
        df = df.drop_duplicates(subset=["PRDLST_REPORT_NO", "RAWMTRL_NM"], keep="last")

    agg_funcs = {
        "PRDLST_NM": "first",
        "BSSH_NM": "first",
        "PRDLST_DCNM": "first",
        "RAWMTRL_NM": lambda x: ", ".join(x.dropna().astype(str).unique())
    }
    df_grouped = df.groupby("PRDLST_REPORT_NO", as_index=False).agg(agg_funcs)
    print(f"  품목별 병합(Groupby) 후 1:1 데이터: {len(df_grouped)}행")

    return df_grouped.rename(columns={"PRDLST_REPORT_NO": "품목제조보고번호"})


def normalize_ingredient_name(value: str) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", "", value).strip()


def split_ingredients(raw_text: str) -> list[str]:
    if not isinstance(raw_text, str) or not raw_text.strip():
        return []
    parts = re.split(r"[,/・]+", raw_text)
    return [part.strip() for part in parts if part and part.strip()]


def select_canonical_name(group: list[str], token_counts: Counter) -> str:
    if not group:
        return ""
    ranked = sorted(group, key=lambda item: (-token_counts[item], len(item), item))
    return ranked[0]


def create_cluster_aliases(df: pd.DataFrame, threshold: float = 0.25) -> tuple[pd.DataFrame, dict[str, str]]:
    ingredient_tokens: list[str] = []
    for raw_text in df["RAWMTRL_NM"].dropna():
        ingredient_tokens.extend(split_ingredients(str(raw_text)))

    ingredient_tokens = [token for token in ingredient_tokens if token]
    if not ingredient_tokens:
        return pd.DataFrame(columns=["원재료명", "Cluster_ID", "표준원재료명"]), {}

    unique_tokens = sorted(set(ingredient_tokens), key=lambda item: (len(item), item))
    if len(unique_tokens) < 2:
        alias_map = {normalize_ingredient_name(token): token for token in unique_tokens}
        cluster_df = pd.DataFrame({
            "원재료명": unique_tokens,
            "Cluster_ID": [0] * len(unique_tokens),
            "표준원재료명": unique_tokens,
        })
        return cluster_df, alias_map

    token_counts = Counter(ingredient_tokens)
    if SentenceTransformer is None or AgglomerativeClustering is None:
        alias_map = {normalize_ingredient_name(token): token for token in unique_tokens}
        cluster_df = pd.DataFrame({
            "원재료명": unique_tokens,
            "Cluster_ID": [0] * len(unique_tokens),
            "표준원재료명": unique_tokens,
        })
        return cluster_df, alias_map

    print("[클러스터링] Hugging Face 임베딩 기반 원재료 클러스터링 진행 중...")
    model = SentenceTransformer("jhgan/ko-sroberta-multitask")
    embeddings = model.encode(unique_tokens, normalize_embeddings=True)

    cluster_model = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=threshold,
        metric="cosine",
        linkage="average",
    )
    cluster_labels = cluster_model.fit_predict(embeddings)

    cluster_groups: dict[int, list[str]] = {}
    for token, label in zip(unique_tokens, cluster_labels):
        cluster_groups.setdefault(int(label), []).append(token)

    alias_map: dict[str, str] = {}
    rows: list[dict] = []
    for label, group in cluster_groups.items():
        canonical_name = select_canonical_name(group, token_counts)
        for token in group:
            normalized_token = normalize_ingredient_name(token)
            alias_map[normalized_token] = canonical_name
            rows.append({
                "원재료명": token,
                "Cluster_ID": label,
                "표준원재료명": canonical_name,
            })

    cluster_df = pd.DataFrame(rows).sort_values(by=["Cluster_ID", "원재료명"], kind="stable")
    return cluster_df.reset_index(drop=True), alias_map


def standardize_ingredient_text(raw_text: str, alias_map: dict[str, str]) -> str:
    ingredients = split_ingredients(raw_text)
    if not ingredients:
        return ""

    standardized = []
    for ingredient in ingredients:
        normalized = normalize_ingredient_name(ingredient)
        standardized.append(alias_map.get(normalized, ingredient))
    return ", ".join(standardized)


def build_base_dataset(nutrition_path: str, c002_path: str) -> pd.DataFrame:
    nutrition = load_nutrition(nutrition_path)
    zero_sugar = filter_zero_sugar(nutrition)

    c002 = load_c002(c002_path)
    c002_cols = ["품목제조보고번호", "PRDLST_NM", "BSSH_NM", "RAWMTRL_NM", "PRDLST_DCNM"]

    base_data = zero_sugar.merge(c002[c002_cols], on="품목제조보고번호", how="inner")

    # ✅ 원재료명에 대체당이 포함되어 있는지 검사 (자연 무당 필터링용)
    sweetener_pattern = "|".join(ARTIFICIAL_SWEETENERS)
    base_data["대체당_포함여부"] = base_data["RAWMTRL_NM"].str.contains(sweetener_pattern, na=False, regex=True)

    # ✅ 필터링: 블랙커피 등 '자연 무당(대체당 없음 + 제로표기 없음)' 걸러내기
    is_natural_zero = (~base_data["제품명_강한제로표기"]) & (~base_data["대체당_포함여부"])
    
    print(f"\n[데이터 정제] 대체당도 없고 '제로' 표기도 없는 자연 무당 제품(블랙커피 등): {is_natural_zero.sum()}개 발견 -> 제외 처리")
    
    # 베이스 데이터 업데이트 (자연 무당 제외)
    base_data = base_data[~is_natural_zero].copy()

    coverage = len(base_data) / len(zero_sugar) * 100 if len(zero_sugar) else 0
    print(f"\n[최종 merge 결과] 진짜 제로슈거 후보(원재료 매칭 완료): {len(base_data)}개")

    empty_raw = base_data["RAWMTRL_NM"].isna() | (base_data["RAWMTRL_NM"].astype(str).str.strip() == "")
    print(f"  그중 원재료 텍스트(RAWMTRL_NM) 결측/공백: {empty_raw.sum()}개 ({empty_raw.mean()*100:.1f}%)")

    cluster_df, alias_map = create_cluster_aliases(base_data)
    cluster_output = OUTPUTS_DIR / "ingredient_clusters_result.csv"
    cluster_df.to_csv(cluster_output, index=False, encoding="utf-8-sig")
    print(f"  [클러스터링 결과] {cluster_output} 저장 완료")

    base_data["표준원재료명"] = base_data["RAWMTRL_NM"].apply(lambda value: standardize_ingredient_text(value, alias_map))

    if len(base_data) > 0 and "식품대분류" in base_data.columns:
        print("\n최종 기초 데이터 - 식품대분류별 건수:")
        print(base_data["식품대분류"].value_counts().to_string())

    return base_data


if __name__ == "__main__":
    ensure_dir(OUTPUTS_DIR)
    base_df = build_base_dataset(DATA_DIR / "food_nutrition_raw.csv", DATA_DIR / "prdlst_rawmtrl_raw.csv")
    base_output = OUTPUTS_DIR / "zeropick_base_data_v4.csv"
    base_df.to_csv(base_output, index=False, encoding="utf-8-sig")
    print(f"\n기초 병합 데이터 저장 완료 -> {base_output} ({len(base_df)}행)")
    
    # 무늬만 제로 검출 (기준: 당류 >= 0.5g OR 에너지 >= 5kcal)
    fake_zero_condition = (base_df["제품명_강한제로표기"] == True) & ((base_df["당류"] >= SUGAR_THRESHOLD) | (base_df["에너지"].fillna(0) >= 5.0))
    blacklist_candidates = base_df[fake_zero_condition]
    
    if len(blacklist_candidates) > 0:
        blacklist_candidates.to_csv(OUTPUTS_DIR / "zeropick_blacklist_candidates.csv", index=False, encoding="utf-8-sig")
        print(f"블랙리스트(무늬만 제로) 1차 후보 저장 완료 -> zeropick_blacklist_candidates.csv ({len(blacklist_candidates)}행)")