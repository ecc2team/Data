"""
Supabase 통합 로더.

ingredient.csv, product_table_data.csv, product_ingredient_mapping.csv
3개 파일을 FK 순서에 맞춰 적재하고, 마지막으로 product.score/summary까지
계산해서 채우는 5단계 파이프라인을 한 번에 실행한다.

  1. ingredient 적재
  2. category 적재(upsert) + category_id 매핑
  3. product 적재 (score/summary는 임시 placeholder로 채움 - 아래 설명)
  4. product_ingredient 적재
  5. product.score / product.summary 계산 및 UPDATE (구 product_score.py)

score/summary를 마지막 단계로 분리한 이유
----------------------------------------
product.score/summary 계산은 product_ingredient 매핑이 몇 개 붙어있는지
(premium_count/warning_count)를 기준으로 하는 로직이라, product_ingredient가
먼저 다 들어가 있어야 정확히 계산된다. 그런데 product.score/summary 컬럼은
DDL상 NOT NULL이라 3단계(product insert) 시점에 값이 없으면 그 자체로
insert가 실패한다. 그래서:
  - 3단계에서는 score=0, summary=''로 임시 채워서 NOT NULL만 통과시키고
  - 4단계(product_ingredient)까지 다 넣은 뒤
  - 5단계에서 실제 계산값으로 UPDATE 한다.
중간에 스크립트가 5단계 전에 죽으면 score=0/summary=''인 상태로 남을 수
있으니, 실패 시 5단계부터 재실행하면 된다(product/product_ingredient는
그대로 두고 score만 다시 계산하면 되므로 --no-truncate와 함께 사용).

재실행 안전성
------------
COPY는 순수 INSERT라 이미 데이터가 있는 상태로 재실행하면 uk_ingredient_name,
uk_ingredient_code, uk_product_external_code, uk_product_ingredient 유니크
제약 위반으로 실패한다. 그래서 이 스크립트는 매 실행마다 기존 데이터를
자식->부모 순으로 먼저 비우고(product_ingredient -> product -> ingredient),
그다음 부모->자식 순으로 다시 채운다. --no-truncate 옵션을 주면 이 초기화를
건너뛰고 이어서 INSERT만 시도한다(빈 테이블 최초 적재, 혹은 5단계만 다시
돌리고 싶을 때 사용).

score/summary 계산 방식 (5단계, 구 product_score.py 로직 그대로)
------------------------------------------------------------
1. product.grade(1~3)로 점수 밴드를 정함: 1->90~100, 2->70~89, 3->40~69
2. 밴드 안에서 ingredient.risk_level 분포(PREMIUM/WARNING 개수)를
   log1p로 점감시켜 세부 점수를 조정
3. warning_additive면 밴드 안에서 추가 감점 (밴드를 벗어나진 않음)
4. ALLERGEN 타입(우유/계란/밀/대두/땅콩/아몬드/호두/복숭아)은 COLOR와
   동일하게 premium/warning 집계에서 제외 - 알레르기 유무는 개인화
   정보라 전체 상품 점수에 섞이면 안 됨

category_id 매핑
----------------
prepare_product_table_data.py의 출력(product_table_data.csv)에는
category_name(예: "음료류")만 있고 category_id는 없다. 이 스크립트가
category 테이블을 먼저 upsert(이미 있는 이름은 재사용, 없으면 새로 insert)해서
이름 -> id 매핑을 만든 뒤 product insert 시 사용한다.

사전 조건
--------
1. product/ingredient/product_ingredient DDL 및 마이그레이션이 이미 적용돼 있어야 함
   (sodium NULL 허용 마이그레이션 등)
2. data/final/ingredient.csv, data/processed/product_table_data.csv,
   data/processed/product_ingredient_mapping.csv 세 파일이 모두 최신 상태로 준비돼 있어야 함
3. .env 또는 환경변수에 SUPABASE_DB_URL 설정
   예: postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres
4. pip install python-dotenv psycopg2-binary pandas --break-system-packages

사용법
------
python src/loader/load_all_to_supabase.py                # 기존 데이터 정리 후 전체 재적재 (1~5단계)
python src/loader/load_all_to_supabase.py --no-truncate   # 정리 없이 이어서 insert (빈 테이블 최초 적재, 또는 재시도용)
"""

import argparse
import io
import math
import os
import sys
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from src.config import DATA_DIR, PROCESSED_DATA_DIR

load_dotenv()

INGREDIENT_CSV = DATA_DIR / "final" / "ingredient.csv"
PRODUCT_CSV = PROCESSED_DATA_DIR / "product_table_data.csv"
MAPPING_CSV = PROCESSED_DATA_DIR / "product_ingredient_mapping.csv"

INGREDIENT_COLUMNS = ["code", "name", "ingredient_type", "risk_level", "summary", "description"]
# score/summary는 3단계에서 placeholder(0, '')로 채워서 NOT NULL만 통과시키고,
# 5단계에서 실제 값으로 UPDATE함 (파일 상단 설명 참고)
PRODUCT_COLUMNS = [
    "category_id", "external_code", "name", "raw_materials",
    "grade", "score", "summary", "warning_additive", "calories", "sugar", "sodium",
]

GRADE_BANDS = {1: (90, 100), 2: (70, 89), 3: (40, 69)}
GRADE_VERDICT = {
    1: "믿고 선택할 수 있는 프리미엄 제로 상품입니다.",
    2: "일반적인 수준의 제로 상품입니다.",
    3: "가짜 제로일 가능성이 있으니 성분표를 꼭 확인하세요.",
}
# 성분 개수가 이 percentile에 도달하면 밴드 끝(ceiling/floor)에 도달.
# 등급별 실제 분포에서 자동으로 뽑음 (product_score.py와 동일 기준)
SATURATION_PERCENTILE = 0.95


# =====================================================
# 공통 유틸
# =====================================================
def _assert_not_lfs_pointer(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"파일이 없습니다: {path}")
    with open(path, "rb") as f:
        head = f.read(200)
    if head.startswith(b"version https://git-lfs.github.com"):
        raise RuntimeError(
            f"{path} 가 Git LFS 포인터 파일입니다. 터미널에서 `git lfs pull` 먼저 실행하세요."
        )


def get_dsn() -> str:
    dsn = os.environ.get("SUPABASE_DB_URL")
    if not dsn:
        raise EnvironmentError(
            "SUPABASE_DB_URL 환경변수가 없습니다. "
            "Supabase 대시보드 > Project Settings > Database > Connection string 값을 설정하세요."
        )
    return dsn


def copy_dataframe(conn, df: pd.DataFrame, table: str, columns: list[str]) -> None:
    buf = io.StringIO()
    df[columns].to_csv(buf, index=False, header=False, na_rep="\\N")
    buf.seek(0)
    col_list = ", ".join(columns)
    with conn.cursor() as cur:
        cur.copy_expert(
            f"COPY {table} ({col_list}) FROM STDIN WITH (FORMAT csv, NULL '\\N')",
            buf,
        )


def truncate_all(conn) -> None:
    """자식 -> 부모 순으로 정리. ingredient는 user_allergy/user_preferred_ingredient가
    참조하므로 CASCADE 시 그쪽 사용자 데이터도 같이 삭제됨에 유의."""
    print("\n[초기화] 기존 데이터 정리 중 (자식 -> 부모 순)...")
    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE product_ingredient")
        cur.execute("TRUNCATE TABLE product RESTART IDENTITY CASCADE")
        cur.execute("TRUNCATE TABLE ingredient RESTART IDENTITY CASCADE")
    conn.commit()
    print("  product_ingredient, product, ingredient 테이블 초기화 완료")


# =====================================================
# 1. ingredient 적재
# =====================================================
def load_ingredient(conn) -> None:
    print("\n[1/5] ingredient 적재 중...")
    _assert_not_lfs_pointer(INGREDIENT_CSV)
    df = pd.read_csv(INGREDIENT_CSV, encoding="utf-8-sig")

    missing = set(INGREDIENT_COLUMNS) - set(df.columns)
    if missing:
        raise KeyError(f"ingredient.csv에 없는 컬럼: {missing}")

    copy_dataframe(conn, df, "ingredient", INGREDIENT_COLUMNS)
    conn.commit()
    print(f"  ✅ ingredient {len(df)}행 적재 완료")


# =====================================================
# 2. category 적재(upsert) + category_id 매핑
# =====================================================
def upsert_categories_and_map(conn, category_names: pd.Series) -> dict:
    print("\n[2/5] category 적재(upsert) 중...")
    unique_names = sorted(category_names.dropna().unique())

    with conn.cursor() as cur:
        for name in unique_names:
            cur.execute(
                """
                INSERT INTO category (name) VALUES (%s)
                ON CONFLICT (name) DO NOTHING
                """,
                (name,),
            )
    conn.commit()

    category_map = pd.read_sql("SELECT id, name FROM category", conn)
    name_to_id = dict(zip(category_map["name"], category_map["id"]))
    print(f"  ✅ category {len(unique_names)}종 확인/적재 완료 (전체 {len(category_map)}행)")
    return name_to_id


# =====================================================
# 3. product 적재 (score/summary는 placeholder)
# =====================================================
def load_product(conn) -> None:
    print("\n[3/5] product 적재 중 (score/summary는 5단계에서 계산)...")
    _assert_not_lfs_pointer(PRODUCT_CSV)
    df = pd.read_csv(PRODUCT_CSV, encoding="utf-8-sig", dtype={"external_code": str})

    if "category_name" not in df.columns:
        raise KeyError(
            "product_table_data.csv에 category_name 컬럼이 없습니다. "
            "prepare_product_table_data.py 출력 형식을 확인하세요."
        )

    name_to_id = upsert_categories_and_map(conn, df["category_name"])
    df["category_id"] = df["category_name"].map(name_to_id)

    missing_cat = df["category_id"].isna().sum()
    if missing_cat > 0:
        print(f"  ⚠️ category_id 매핑 실패 {missing_cat}행 (해당 행은 제외하고 적재)")
        df = df.dropna(subset=["category_id"])
    df["category_id"] = df["category_id"].astype(int)

    # NOT NULL 통과용 placeholder. 5단계에서 실제 값으로 UPDATE됨.
    df["score"] = 0
    df["summary"] = ""

    missing = set(PRODUCT_COLUMNS) - set(df.columns)
    if missing:
        raise KeyError(f"product_table_data.csv에 없는 컬럼: {missing}")

    copy_dataframe(conn, df, "product", PRODUCT_COLUMNS)
    conn.commit()
    print(f"  ✅ product {len(df)}행 적재 완료 (score=0, summary='' placeholder)")


# =====================================================
# 4. product_ingredient 적재
# =====================================================
def load_product_ingredient(conn) -> None:
    print("\n[4/5] product_ingredient 적재 중...")
    _assert_not_lfs_pointer(MAPPING_CSV)

    df = pd.read_csv(
        MAPPING_CSV,
        encoding="utf-8-sig",
        dtype={"external_food_code": str, "ingredient_code": str},
    )
    print(f"  원본 매핑 파일: {len(df)}행")

    df["external_food_code"] = df["external_food_code"].str.replace(r"\.0$", "", regex=True).str.strip()
    df["ingredient_code"] = df["ingredient_code"].str.replace(r"\.0$", "", regex=True).str.strip()

    with conn.cursor() as cur:
        cur.execute("SELECT id, external_code FROM product")
        product_map = {str(code).strip(): id_ for id_, code in cur.fetchall()}
        cur.execute("SELECT id, code FROM ingredient")
        ingredient_map = {str(code).strip(): id_ for id_, code in cur.fetchall()}
    print(f"  product 테이블: {len(product_map)}행 조회")
    print(f"  ingredient 테이블: {len(ingredient_map)}행 조회")

    before = len(df)
    df = df[df["external_food_code"].isin(product_map)]
    dropped_product = before - len(df)

    before = len(df)
    df = df[df["ingredient_code"].isin(ingredient_map)]
    dropped_ingredient = before - len(df)

    before = len(df)
    df = df.sort_values("sequence").drop_duplicates(
        subset=["external_food_code", "ingredient_code"], keep="first"
    )
    dropped_dup = before - len(df)

    print(f"  product 미매칭 제외: {dropped_product}행")
    print(f"  ingredient 미매칭 제외: {dropped_ingredient}행")
    print(f"  (product, ingredient) 중복 제외: {dropped_dup}행")

    df["product_id"] = df["external_food_code"].map(product_map)
    df["ingredient_id"] = df["ingredient_code"].map(ingredient_map)
    final_df = df[["product_id", "ingredient_id", "sequence"]]

    if len(final_df) == 0:
        print("  insert할 행이 없습니다. 종료합니다.")
        return

    copy_dataframe(conn, final_df, "product_ingredient", ["product_id", "ingredient_id", "sequence"])
    conn.commit()
    print(f"  ✅ product_ingredient {len(final_df)}행 적재 완료")


# =====================================================
# 5. product.score / product.summary 계산 및 UPDATE
#    (구 product_score.py 로직 그대로. ALLERGEN 제외 필터 반영됨)
# =====================================================
def fetch_product_ingredient_stats(conn) -> pd.DataFrame:
    """
    product당 1행. premium_count/warning_count는 score 계산용,
    premium_names/warning_names는 summary 조립용.

    NOTE: warning_count/warning_names 필터에서 COLOR와 ALLERGEN을 함께
    제외함. ALLERGEN(우유/계란/밀/대두/땅콩/아몬드/호두/복숭아)은 risk_level이
    WARNING이지만 개인 알레르기 정보라 전체 상품 점수에 섞이면 안 됨
    (예: 밀가루가 384건으로 흔하다고 warning_count에 잡히면 빵류 점수가
    알레르기 없는 사용자 기준에서도 부당하게 깎임).
    """
    query = """
        SELECT
            p.id AS product_id,
            p.grade,
            p.warning_additive,
            COUNT(i.id) FILTER (WHERE i.risk_level = 'PREMIUM') AS premium_count,
            COUNT(i.id) FILTER (
                WHERE i.risk_level = 'WARNING' AND i.ingredient_type NOT IN ('COLOR', 'ALLERGEN')
            ) AS warning_count,
            COUNT(i.id) AS total_count,
            COALESCE(
                ARRAY_AGG(i.name) FILTER (WHERE i.risk_level = 'PREMIUM'),
                ARRAY[]::text[]
            ) AS premium_names,
            COALESCE(
                ARRAY_AGG(i.name) FILTER (
                    WHERE i.risk_level = 'WARNING' AND i.ingredient_type NOT IN ('COLOR', 'ALLERGEN')
                ),
                ARRAY[]::text[]
            ) AS warning_names
        FROM product p
        LEFT JOIN product_ingredient pi ON pi.product_id = p.id
        LEFT JOIN ingredient i ON i.id = pi.ingredient_id
        WHERE p.deleted_at IS NULL
        GROUP BY p.id, p.grade, p.warning_additive
    """
    return pd.read_sql(query, conn)


def compute_saturation_counts(df: pd.DataFrame, percentile: float = SATURATION_PERCENTILE) -> dict:
    saturation = {}
    for grade, sub in df.groupby("grade"):
        p_sat = max(1, int(round(sub["premium_count"].quantile(percentile))))
        w_sat = max(1, int(round(sub["warning_count"].quantile(percentile))))
        saturation[grade] = (p_sat, w_sat)
    return saturation


def compute_score(row, saturation: dict) -> int:
    floor, ceiling = GRADE_BANDS[row["grade"]]
    width = ceiling - floor
    mid = floor + width / 2
    half_band = width / 2

    premium_sat, warning_sat = saturation[row["grade"]]
    premium_signal = math.log1p(row["premium_count"]) / math.log1p(premium_sat)
    warning_signal = math.log1p(row["warning_count"]) / math.log1p(warning_sat)

    adjustment = half_band * premium_signal - half_band * warning_signal
    adjustment = max(-half_band, min(half_band, adjustment))

    score = mid + adjustment
    if row["warning_additive"]:
        score -= width * 0.3

    return int(max(floor, min(ceiling, round(score))))


def is_near_saturation(row, saturation: dict) -> bool:
    premium_sat, _ = saturation[row["grade"]]
    return row["premium_count"] >= premium_sat


def build_summary(row, saturation: dict) -> str:
    premium_names = row["premium_names"] or []
    warning_names = row["warning_names"] or []

    if row["grade"] == 1 and warning_names:
        names = ", ".join(warning_names[:2])
        return (
            f"{names} 등 혈당에 영향을 줄 수 있는 성분이 포함되어 있어요. "
            f"등급은 프리미엄이지만 성분표를 한 번 더 확인해보는 걸 추천해요."
        )

    if row["warning_additive"]:
        feature = "카라멜색소 등 우려 첨가물이 포함되어 있어"
    elif warning_names:
        names = ", ".join(warning_names[:2])
        feature = f"{names} 등의 성분이 일부 포함되어 있어"
    elif premium_names and is_near_saturation(row, saturation):
        names = ", ".join(premium_names[:2])
        feature = f"{names} 등 프리미엄 성분 위주로 구성되어 있어"
    else:
        feature = "특별한 감미료 이슈 없이 무난하게 구성되어 있어"

    return f"{feature}, {GRADE_VERDICT[row['grade']]}"


def compute_and_update_score(conn) -> None:
    print("\n[5/5] product.score / summary 계산 및 UPDATE 중...")
    df = fetch_product_ingredient_stats(conn)
    print(f"  대상 product: {len(df)}건")

    saturation = compute_saturation_counts(df)
    print(f"  saturation 기준 (percentile={SATURATION_PERCENTILE}): {saturation}")

    df["score"] = df.apply(lambda row: compute_score(row, saturation), axis=1)
    df["summary"] = df.apply(lambda row: build_summary(row, saturation), axis=1)

    with conn.cursor() as cur:
        cur.execute("""
            CREATE TEMP TABLE tmp_product_score (
                product_id BIGINT,
                score SMALLINT,
                summary TEXT
            ) ON COMMIT DROP
        """)
        buf = io.StringIO()
        df[["product_id", "score", "summary"]].to_csv(buf, index=False, header=False)
        buf.seek(0)
        cur.copy_expert(
            "COPY tmp_product_score (product_id, score, summary) FROM STDIN WITH (FORMAT csv)",
            buf,
        )
        cur.execute("""
            UPDATE product
            SET score = tmp.score,
                summary = tmp.summary
            FROM tmp_product_score tmp
            WHERE product.id = tmp.product_id
        """)
    conn.commit()

    for grade, (floor, ceiling) in GRADE_BANDS.items():
        n_grade = (df["grade"] == grade).sum()
        n_ceiling = ((df["grade"] == grade) & (df["score"] == ceiling)).sum()
        n_floor = ((df["grade"] == grade) & (df["score"] == floor)).sum()
        print(f"  grade {grade}: {n_grade}건 중 ceiling({ceiling}) {n_ceiling}건 / floor({floor}) {n_floor}건")

    print(f"  ✅ product {len(df)}행 score/summary 업데이트 완료")


# =====================================================
# 실행부
# =====================================================
def main() -> None:
    parser = argparse.ArgumentParser(description="Supabase 통합 로더")
    parser.add_argument(
        "--no-truncate",
        action="store_true",
        help="기존 데이터 정리를 건너뛰고 바로 insert (빈 테이블 최초 적재, 또는 5단계 재시도용)",
    )
    args = parser.parse_args()

    conn = psycopg2.connect(get_dsn())
    try:
        if not args.no_truncate:
            truncate_all(conn)
        else:
            print("\n[초기화] --no-truncate 지정됨 -> 기존 데이터 정리 생략")

        load_ingredient(conn)
        load_product(conn)
        load_product_ingredient(conn)
        compute_and_update_score(conn)

        print("\n🎉 전체 적재 완료! (ingredient -> category -> product -> product_ingredient -> score/summary)")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()