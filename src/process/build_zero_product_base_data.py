import os
import sys
import re
from collections import Counter
import pandas as pd
import numpy as np

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from src.config import DATA_DIR, ensure_dir

RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
FINAL_DATA_DIR = DATA_DIR / "final"
INGREDIENT_PATH = FINAL_DATA_DIR / "ingredient.csv"

try:
    from sentence_transformers import SentenceTransformer
    from sklearn.cluster import AgglomerativeClustering
except ImportError:
    SentenceTransformer = None
    AgglomerativeClustering = None

# =============================================================================
# 1. 마케팅 키워드 정의 (ingredient.csv에 없는, 식품명 문구 전용이라 하드코딩 유지)
# =============================================================================
ZERO_CAL_KEYWORDS = ["0kcal", "영칼로리", "제로칼로리", "무열량"]
ZERO_SUG_KEYWORDS = ["슈가프리", "무설탕", "제로슈거", "무당", "무가당"]
GENERAL_ZERO_KEYWORDS = ["제로"]
LOW_CLAIM_KEYWORDS = ["저당", "로우슈거", "저칼로리", "라이트"]


# =============================================================================
# 2. 데이터 로드 및 전처리 함수
# =============================================================================
def normalize_key(series: pd.Series) -> pd.Series:
    """품목제조보고번호 정규화 (문자열 변환, 공백 제거, .0 제거)"""
    return series.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)

def load_nutrition(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"품목제조보고번호": str})
    df["품목제조보고번호"] = normalize_key(df["품목제조보고번호"])
    df = df.dropna(subset=["품목제조보고번호"])
    return df

def load_c002(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"PRDLST_REPORT_NO": str}, low_memory=False)
    df["PRDLST_REPORT_NO"] = normalize_key(df["PRDLST_REPORT_NO"])

    if "CHNG_DT" in df.columns:
        df = df.sort_values(["CHNG_DT", "RAWMTRL_ORDNO"], na_position="first")
        df = df.drop_duplicates(subset=["PRDLST_REPORT_NO", "RAWMTRL_NM"], keep="last")

    agg_funcs = {
        "PRDLST_NM": "first",
        "BSSH_NM": "first",
        "PRDLST_DCNM": "first",
        "RAWMTRL_NM": lambda x: ", ".join(x.dropna().astype(str).unique())
    }
    df_grouped = df.groupby("PRDLST_REPORT_NO", as_index=False).agg(agg_funcs)
    return df_grouped.rename(columns={"PRDLST_REPORT_NO": "품목제조보고번호"})


def load_ingredient_keywords(path) -> dict[str, list[str]]:
    """
    ingredient.csv(risk_level/ingredient_type)를 등급 판정용 키워드 리스트로 변환.
    하드코딩 리스트 대신 이걸 쓰면, ingredient.csv 수정 시 등급 로직도 자동으로 최신화됨.

    NOTE: ALLERGEN(우유/계란/밀/대두/땅콩/아몬드/호두/복숭아)은 risk_level이
    WARNING이지만 등급 판정과는 무관한 개인화 정보라서, COLOR와 동일하게
    blood_sugar_traps 집계에서 제외해야 함. 제외하지 않으면 밀가루/우유가
    들어간 빵류가 전부 "혈당 트랩 성분 포함"으로 오판되어 3등급으로
    강등되는 문제가 생김 (알레르기 유무와 제로 등급은 별개 축).
    """
    ingredient_df = pd.read_csv(path)

    premium = ingredient_df.loc[ingredient_df["risk_level"] == "PREMIUM", "name"].tolist()
    synthetic = ingredient_df.loc[ingredient_df["risk_level"] == "GENERAL", "name"].tolist()
    blood_sugar_traps = ingredient_df.loc[
        (ingredient_df["risk_level"] == "WARNING")
        & (~ingredient_df["ingredient_type"].isin(["COLOR", "ALLERGEN"])),
        "name",
    ].tolist()
    additive_traps = ingredient_df.loc[ingredient_df["ingredient_type"] == "COLOR", "name"].tolist()

    return {
        "PREMIUM_SWEETENERS": premium,
        "SYNTHETIC_SWEETENERS": synthetic,
        "BLOOD_SUGAR_TRAPS": blood_sugar_traps,
        "ADDITIVE_TRAPS": additive_traps,
    }


# =============================================================================
# 3. 원재료명 텍스트 정규화 및 클러스터링 함수
# =============================================================================
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
    ingredient_tokens = []
    for raw_text in df["RAWMTRL_NM"].dropna():
        ingredient_tokens.extend(split_ingredients(str(raw_text)))

    ingredient_tokens = [token for token in ingredient_tokens if token]
    if not ingredient_tokens:
        return pd.DataFrame(columns=["원재료명", "Cluster_ID", "표준원재료명"]), {}

    unique_tokens = sorted(set(ingredient_tokens), key=lambda item: (len(item), item))
    if len(unique_tokens) < 2 or SentenceTransformer is None or AgglomerativeClustering is None:
        alias_map = {normalize_ingredient_name(t): t for t in unique_tokens}
        cluster_df = pd.DataFrame({
            "원재료명": unique_tokens,
            "Cluster_ID": [0] * len(unique_tokens),
            "표준원재료명": unique_tokens,
        })
        return cluster_df, alias_map

    model = SentenceTransformer("jhgan/ko-sroberta-multitask")
    embeddings = model.encode(unique_tokens, normalize_embeddings=True)
    cluster_model = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=threshold,
        metric="cosine",
        linkage="average"
    )
    cluster_labels = cluster_model.fit_predict(embeddings)

    cluster_groups = {}
    for token, label in zip(unique_tokens, cluster_labels):
        cluster_groups.setdefault(int(label), []).append(token)

    alias_map = {}
    rows = []
    token_counts = Counter(ingredient_tokens)

    for label, group in cluster_groups.items():
        canonical_name = select_canonical_name(group, token_counts)
        for token in group:
            alias_map[normalize_ingredient_name(token)] = canonical_name
            rows.append({
                "원재료명": token,
                "Cluster_ID": label,
                "표준원재료명": canonical_name
            })

    cluster_df = pd.DataFrame(rows).sort_values(by=["Cluster_ID", "원재료명"], kind="stable")
    return cluster_df.reset_index(drop=True), alias_map

def standardize_ingredient_text(raw_text: str, alias_map: dict[str, str]) -> str:
    ingredients = split_ingredients(raw_text)
    if not ingredients:
        return ""
    standardized = [alias_map.get(normalize_ingredient_name(ing), ing) for ing in ingredients]
    return ", ".join(standardized)


# =============================================================================
# 4. 제로 식품 핵심 분석 및 평가 로직
# =============================================================================
def is_relevant_to_zero_marketing(df: pd.DataFrame) -> pd.Series:
    """
    제품명에 '제로/무설탕/슈가프리/저당' 등 마케팅 키워드가 포함된 제품만 추출.
    일반 빵이나 반찬 등에 단순히 대체당/첨가물이 쓰였다고 해서 타겟으로 잡지 않음.
    """
    food_names = df["식품명"].fillna("").astype(str)

    has_cal_claim = food_names.str.contains("|".join(ZERO_CAL_KEYWORDS), regex=True)
    has_sug_claim = food_names.str.contains("|".join(ZERO_SUG_KEYWORDS), regex=True)
    has_gen_claim = food_names.str.contains("|".join(GENERAL_ZERO_KEYWORDS), regex=True)
    has_low_claim = food_names.str.contains("|".join(LOW_CLAIM_KEYWORDS), regex=True)

    return has_cal_claim | has_sug_claim | has_gen_claim | has_low_claim


def evaluate_zero_products(df: pd.DataFrame, keywords: dict[str, list[str]]) -> pd.DataFrame:
    """제로 마케팅 식품의 영양성분 및 원재료를 바탕으로 1, 2, 3등급 판정"""
    df = df.copy()
    sugars = df["당류"].fillna(999.0)
    calories = df["에너지"].fillna(999.0)
    food_names = df["식품명"].fillna("").astype(str)
    raw_materials = df["RAWMTRL_NM"].fillna("").astype(str)

    premium_sweeteners = keywords["PREMIUM_SWEETENERS"]
    synthetic_sweeteners = keywords["SYNTHETIC_SWEETENERS"]
    blood_sugar_traps = keywords["BLOOD_SUGAR_TRAPS"]
    additive_traps = keywords["ADDITIVE_TRAPS"]

    # 법적 '제로' 기준 (100ml/100g 당 기준이지만 일단 1회 제공량 등으로 보수적 판별)
    pass_sugar = sugars < 0.5
    pass_calorie = calories < 5.0

    has_cal_claim = food_names.str.contains("|".join(ZERO_CAL_KEYWORDS), regex=True)
    has_sug_claim = food_names.str.contains("|".join(ZERO_SUG_KEYWORDS), regex=True)
    has_gen_claim = food_names.str.contains("|".join(GENERAL_ZERO_KEYWORDS), regex=True)
    has_low_claim = food_names.str.contains("|".join(LOW_CLAIM_KEYWORDS), regex=True)

    has_blood_sugar_trap = raw_materials.str.contains("|".join(blood_sugar_traps), regex=True)
    has_additive_trap = raw_materials.str.contains("|".join(additive_traps), regex=True)
    has_premium_sweetener = raw_materials.str.contains("|".join(premium_sweeteners), regex=True)
    has_synthetic_sweetener = raw_materials.str.contains("|".join(synthetic_sweeteners), regex=True)
    has_any_sweetener = raw_materials.str.contains(
        "|".join(premium_sweeteners + synthetic_sweeteners + blood_sugar_traps), regex=True
    )

    # 가짜 제로 판별 (마케팅은 '제로'인데 실제 성분은 제로 기준치 초과)
    # 저당/저칼로리(has_low_claim) 표기 제품은 제로 기준(0.5)을 넘어도 합법이므로 가짜 제로에서 예외 처리
    is_fake_zero_cal = (has_cal_claim | (has_gen_claim & ~has_sug_claim & ~has_low_claim)) & (~(pass_sugar & pass_calorie))
    is_fake_zero_sug = has_sug_claim & (~pass_sugar)
    is_fake_zero = is_fake_zero_cal | is_fake_zero_sug

    # 표기도 없고 감미료도 없는데 영양성분만 낮은 자연제품 판별 (타겟 필터링에 의해 실질적으론 False)
    is_natural_zero = pass_sugar & pass_calorie & (~has_gen_claim) & (~has_cal_claim) & (~has_sug_claim) & (~has_any_sweetener) & (~has_low_claim)

    # [3등급 조건]: 가짜 제로이거나, 혈당 트랩 성분이 있거나, 우려 첨가물이 있는 경우
    cond_grade_3 = is_fake_zero | has_blood_sugar_trap | has_additive_trap

    # 합성 감미료 없이 프리미엄 대체당만 사용한 경우
    is_premium_ingredients = has_premium_sweetener & (~has_synthetic_sweetener)

    # [1등급 조건]: 3등급이 아니면서, 제로 기준치를 만족하고 프리미엄 감미료만 사용한 경우
    cond_grade_1 = (~cond_grade_3) & (
        is_natural_zero |
        (has_cal_claim & pass_sugar & pass_calorie & is_premium_ingredients) |
        (has_sug_claim & pass_sugar & is_premium_ingredients) |
        (has_gen_claim & pass_sugar & pass_calorie & is_premium_ingredients) |
        (has_low_claim & pass_sugar & is_premium_ingredients)
    )

    # [2등급 조건]: 1/3등급이 아니면서, 당류 기준(pass_sugar)을 만족하거나
    # 저당 표기(has_low_claim) 제품인 경우 (저당은 0.5g 기준 적용 대상이 아니므로,
    # pass_sugar를 못 넘는다고 default=3으로 새면 안 됨 -> 최소 grade_2는 보장)
    cond_grade_2 = (~cond_grade_3) & (~cond_grade_1) & (pass_sugar | has_low_claim)

    df["최종등급"] = np.select([cond_grade_3, cond_grade_1, cond_grade_2], [3, 1, 2], default=3)
    df["가짜제로_여부"] = is_fake_zero
    df["자연제로_여부"] = is_natural_zero
    df["혈당트랩_여부"] = has_blood_sugar_trap
    df["첨가물트랩_여부"] = has_additive_trap

    return df


def build_base_dataset(nutrition_path, c002_path, ingredient_path) -> pd.DataFrame:
    nutrition = load_nutrition(nutrition_path)
    c002 = load_c002(c002_path)
    keywords = load_ingredient_keywords(ingredient_path)
    print(f"[join 전] nutrition(dropna 이후): {len(nutrition)}건")
    print(f"[join 전] c002(품목번호 기준 groupby 이후): {len(c002)}건")

    c002_cols = ["품목제조보고번호", "PRDLST_NM", "BSSH_NM", "RAWMTRL_NM", "PRDLST_DCNM"]
    base_data = nutrition.merge(c002[c002_cols], on="품목제조보고번호", how="inner")
    print(f"[join 후] base_data: {len(base_data)}건")

    # 제로/저당 마케팅을 하지 않은 일반 식품 제외
    n_before_exclude = len(base_data)
    relevant_mask = is_relevant_to_zero_marketing(base_data)
    excluded_count = int((~relevant_mask).sum())
    base_data = base_data[relevant_mask].copy()
    print(f"[일반/자연 식품 제외] {excluded_count}건 제외 (제외 전 {n_before_exclude}건) "
          f"→ 최종 평가 타겟 {len(base_data)}건 확정")

    # 남은 타겟 제품들에 대해 등급 및 트랩 여부 평가
    base_data = evaluate_zero_products(base_data, keywords)

    # 원재료명 클러스터링을 통한 표준화
    cluster_df, alias_map = create_cluster_aliases(base_data)
    cluster_output = PROCESSED_DATA_DIR / "ingredient_clusters_result.csv"
    cluster_df.to_csv(cluster_output, index=False, encoding="utf-8-sig")

    base_data["표준원재료명"] = base_data["RAWMTRL_NM"].apply(lambda value: standardize_ingredient_text(value, alias_map))

    return base_data


# =============================================================================
# 5. 실행부
# =============================================================================
if __name__ == "__main__":
    ensure_dir(PROCESSED_DATA_DIR)

    nutrition_file = RAW_DATA_DIR / "food_nutrition_raw.csv"
    c002_file = RAW_DATA_DIR / "prdlst_rawmtrl_raw.csv"

    base_df = build_base_dataset(nutrition_file, c002_file, INGREDIENT_PATH)

    base_output = PROCESSED_DATA_DIR / "zeropick_base_data_v4.csv"
    base_df.to_csv(base_output, index=False, encoding="utf-8-sig")
    print(f"최종 베이스 데이터 저장 완료: {base_output} ({len(base_df)}건)")

    blacklist_candidates = base_df[base_df["최종등급"] == 3]
    if not blacklist_candidates.empty:
        blacklist_output = PROCESSED_DATA_DIR / "zeropick_blacklist_candidates.csv"
        blacklist_candidates.to_csv(blacklist_output, index=False, encoding="utf-8-sig")
        print(f"블랙리스트 데이터 저장 완료: {blacklist_output} ({len(blacklist_candidates)}건)")