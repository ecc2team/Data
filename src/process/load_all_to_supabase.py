"""
Supabase 통합 로더.

ingredient.csv, product_table_data.csv, product_ingredient_mapping.csv
3개 파일을 FK 순서(ingredient/category -> product -> product_ingredient)에
맞춰 한 번에 적재한다.

기존에는 load_product_table_data_to_db.py / load_product_ingredient_mapping_to_db.py
2개로 나뉘어 있었고, ingredient 자체를 Supabase에 넣는 스크립트는 따로
없었음(로컬 Docker용 load_to_local_db.py만 있었는데 그건 삭제됨). 이 스크립트가
그 3개 파일을 모두 커버한다.

재실행 안전성
------------
COPY는 순수 INSERT라 이미 데이터가 있는 상태로 재실행하면 uk_ingredient_name,
uk_ingredient_code, uk_product_external_code, uk_product_ingredient 유니크
제약 위반으로 실패한다. 그래서 이 스크립트는 매 실행마다 기존 데이터를
자식->부모 순으로 먼저 비우고(product_ingredient -> product -> ingredient),
그다음 부모->자식 순으로 다시 채운다. --no-truncate 옵션을 주면 이 초기화를
건너뛰고 이어서 INSERT만 시도한다(빈 테이블에 처음 적재할 때만 사용 권장).

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
python src/loader/load_all_to_supabase.py            # 기존 데이터 정리 후 전체 재적재
python src/loader/load_all_to_supabase.py --no-truncate   # 정리 없이 바로 insert (빈 테이블 최초 적재용)
"""

import argparse
import io
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
PRODUCT_COLUMNS = [
    "category_id", "external_code", "name", "raw_materials",
    "grade", "warning_additive", "calories", "sugar", "sodium",
]


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
    print("\n[1/4] ingredient 적재 중...")
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
    print("\n[2/4] category 적재(upsert) 중...")
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
# 3. product 적재
# =====================================================
def load_product(conn) -> None:
    print("\n[3/4] product 적재 중...")
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

    missing = set(PRODUCT_COLUMNS) - set(df.columns)
    if missing:
        raise KeyError(f"product_table_data.csv에 없는 컬럼: {missing}")

    copy_dataframe(conn, df, "product", PRODUCT_COLUMNS)
    conn.commit()
    print(f"  ✅ product {len(df)}행 적재 완료")


# =====================================================
# 4. product_ingredient 적재
# =====================================================
def load_product_ingredient(conn) -> None:
    print("\n[4/4] product_ingredient 적재 중...")
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
# 실행부
# =====================================================
def main() -> None:
    parser = argparse.ArgumentParser(description="Supabase 통합 로더")
    parser.add_argument(
        "--no-truncate",
        action="store_true",
        help="기존 데이터 정리를 건너뛰고 바로 insert (빈 테이블 최초 적재 시에만 사용)",
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

        print("\n🎉 전체 적재 완료! (ingredient -> category -> product -> product_ingredient)")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()