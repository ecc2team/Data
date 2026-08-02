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

try:
    from sentence_transformers import SentenceTransformer
    from sklearn.cluster import AgglomerativeClustering
except ImportError:
    SentenceTransformer = None
    AgglomerativeClustering = None

ZERO_CAL_KEYWORDS = ["0kcal", "영칼로리", "제로칼로리", "무열량"]
ZERO_SUG_KEYWORDS = ["슈가프리", "무설탕", "제로슈거", "무당", "무가당"]
GENERAL_ZERO_KEYWORDS = ["제로"]

PREMIUM_SWEETENERS = ["스테비아", "에리스리톨", "알룰로스", "나한과", "스테비올배당체"]
SYNTHETIC_SWEETENERS = ["수크랄로스", "아세설팜칼륨", "아세설팜k", "아스파탐", "자일리톨", "소르비톨", "d-소르비톨", "효소처리스테비아"]
BLOOD_SUGAR_TRAPS = ["말티톨", "포도당", "말토덱스트린", "타피오카전분", "타피오카", "과당", "아가베시럽"]
ADDITIVE_TRAPS = ["카라멜색소", "캐러멜색소"]

def normalize_key(series: pd.Series) -> pd.Series:
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

def evaluate_zero_products(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    sugars = df["당류"].fillna(999.0)
    calories = df["에너지"].fillna(999.0)
    food_names = df["식품명"].fillna("").astype(str)
    raw_materials = df["RAWMTRL_NM"].fillna("").astype(str)

    pass_sugar = sugars < 0.5
    pass_calorie = calories < 5.0  

    has_cal_claim = food_names.str.contains("|".join(ZERO_CAL_KEYWORDS), regex=True)
    has_sug_claim = food_names.str.contains("|".join(ZERO_SUG_KEYWORDS), regex=True)
    has_gen_claim = food_names.str.contains("|".join(GENERAL_ZERO_KEYWORDS), regex=True)

    has_blood_sugar_trap = raw_materials.str.contains("|".join(BLOOD_SUGAR_TRAPS), regex=True)
    has_additive_trap = raw_materials.str.contains("|".join(ADDITIVE_TRAPS), regex=True)
    has_premium_sweetener = raw_materials.str.contains("|".join(PREMIUM_SWEETENERS), regex=True)
    has_synthetic_sweetener = raw_materials.str.contains("|".join(SYNTHETIC_SWEETENERS), regex=True)
    has_any_sweetener = raw_materials.str.contains("|".join(PREMIUM_SWEETENERS + SYNTHETIC_SWEETENERS + BLOOD_SUGAR_TRAPS), regex=True)

    is_fake_zero_cal = (has_cal_claim | (has_gen_claim & ~has_sug_claim)) & (~(pass_sugar & pass_calorie))
    is_fake_zero_sug = has_sug_claim & (~pass_sugar)
    is_fake_zero = is_fake_zero_cal | is_fake_zero_sug

    is_natural_zero = pass_sugar & pass_calorie & (~has_gen_claim) & (~has_cal_claim) & (~has_sug_claim) & (~has_any_sweetener)

    cond_grade_3 = is_fake_zero | has_blood_sugar_trap | has_additive_trap
    is_premium_ingredients = has_premium_sweetener & (~has_synthetic_sweetener)
    
    cond_grade_1 = (~cond_grade_3) & (
        is_natural_zero | 
        (has_cal_claim & pass_sugar & pass_calorie & is_premium_ingredients) |
        (has_sug_claim & pass_sugar & is_premium_ingredients) |
        (has_gen_claim & pass_sugar & pass_calorie & is_premium_ingredients)
    )
    
    cond_grade_2 = (~cond_grade_3) & (~cond_grade_1) & pass_sugar

    df["최종등급"] = np.select([cond_grade_3, cond_grade_1, cond_grade_2], [3, 1, 2], default=3)
    df["가짜제로_여부"] = is_fake_zero
    df["자연제로_여부"] = is_natural_zero
    df["혈당트랩_여부"] = has_blood_sugar_trap
    df["첨가물트랩_여부"] = has_additive_trap

    return df

def build_base_dataset(nutrition_path, c002_path) -> pd.DataFrame:
    nutrition = load_nutrition(nutrition_path)
    c002 = load_c002(c002_path)
    print(f"[join 전] nutrition(dropna 이후): {len(nutrition)}건")
    print(f"[join 전] c002(품목번호 기준 groupby 이후): {len(c002)}건")
    
    c002_cols = ["품목제조보고번호", "PRDLST_NM", "BSSH_NM", "RAWMTRL_NM", "PRDLST_DCNM"]
    base_data = nutrition.merge(c002[c002_cols], on="품목제조보고번호", how="inner")
    print(f"[join 후] base_data: {len(base_data)}건")
    
    base_data = evaluate_zero_products(base_data)

    cluster_df, alias_map = create_cluster_aliases(base_data)
    cluster_output = PROCESSED_DATA_DIR / "ingredient_clusters_result.csv"
    cluster_df.to_csv(cluster_output, index=False, encoding="utf-8-sig")
    
    base_data["표준원재료명"] = base_data["RAWMTRL_NM"].apply(lambda value: standardize_ingredient_text(value, alias_map))
    
    return base_data

if __name__ == "__main__":
    ensure_dir(PROCESSED_DATA_DIR)
    
    nutrition_file = RAW_DATA_DIR / "food_nutrition_raw.csv"
    c002_file = RAW_DATA_DIR / "prdlst_rawmtrl_raw.csv"
    
    base_df = build_base_dataset(nutrition_file, c002_file)
    
    base_output = PROCESSED_DATA_DIR / "zeropick_base_data_v4.csv"
    base_df.to_csv(base_output, index=False, encoding="utf-8-sig")
    print(f"{base_output} ({len(base_df)})")
    
    blacklist_candidates = base_df[base_df["최종등급"] == 3]
    if not blacklist_candidates.empty:
        blacklist_output = PROCESSED_DATA_DIR / "zeropick_blacklist_candidates.csv"
        blacklist_candidates.to_csv(blacklist_output, index=False, encoding="utf-8-sig")
        print(f"{blacklist_output} ({len(blacklist_candidates)})")