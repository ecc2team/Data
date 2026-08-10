from io import StringIO

import pandas as pd
import psycopg2

from src.config import DATA_DIR, DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, PROCESSED_DATA_DIR

INGREDIENT_CSV = DATA_DIR / "final" / "ingredient.csv"
PRODUCT_CSV = PROCESSED_DATA_DIR / "product_table_data.csv"

# ── 로컬 Docker DB 접속 ───────────────────────────
conn = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
)
cur = conn.cursor()


def bulk_copy(df, table, columns):
    buf = StringIO()
    df[columns].to_csv(
        buf,
        index=False,
        header=False,
        sep="\t",
        na_rep="\\N",
    )
    buf.seek(0)

    cur.copy_expert(
        f"COPY {table} ({', '.join(columns)}) "
        f"FROM STDIN WITH (FORMAT text, NULL '\\N')",
        buf,
    )


# ── 1. product 읽기 ───────────────────────────────
product_df = pd.read_csv(
    PRODUCT_CSV,
    dtype={"external_code": str},
)

# 숫자 컬럼 숫자로 변환 (문자열/빈칸 처리)
numeric_cols = ["calories", "sugar", "sodium"]

for col in numeric_cols:
    product_df[col] = pd.to_numeric(product_df[col], errors="coerce")

# NULL → 0
product_df["calories"] = product_df["calories"].fillna(0).astype(int)
product_df["sugar"] = product_df["sugar"].fillna(0)
product_df["sodium"] = product_df["sodium"].fillna(0)

# warning_additive NULL이면 False
product_df["warning_additive"] = (
    product_df["warning_additive"].fillna(False).astype(bool)
)

print("결측치 개수")
print(product_df[["calories", "sugar", "sodium"]].isna().sum())

# ── 2. category 적재 ──────────────────────────────
categories = pd.DataFrame({"name": product_df["category_name"].dropna().unique()})

bulk_copy(categories, "category", ["name"])
conn.commit()
print(f"✅ category {len(categories)}건 적재 완료")

# ── 3. ingredient 적재 ────────────────────────────
ingredient_df = pd.read_csv(INGREDIENT_CSV)

bulk_copy(
    ingredient_df,
    "ingredient",
    [
        "code",
        "name",
        "ingredient_type",
        "risk_level",
        "summary",
        "description",
    ],
)

conn.commit()
print(f"✅ ingredient {len(ingredient_df)}건 적재 완료")

# ── 4. category_id 매핑 ───────────────────────────
category_map = pd.read_sql(
    "SELECT id, name FROM category",
    conn,
)

name_to_cid = dict(zip(category_map["name"], category_map["id"]))

product_df["category_id"] = product_df["category_name"].map(name_to_cid).astype("Int64")

missing_cat = product_df["category_id"].isna().sum()

if missing_cat > 0:
    print(f"⚠️ category_id 매핑 실패 {missing_cat}건")

# ── 5. product 적재 ───────────────────────────────
bulk_copy(
    product_df,
    "product",
    [
        "external_code",
        "name",
        "category_id",
        "raw_materials", 
        "grade",
        "warning_additive",
        "calories",
        "sugar",
        "sodium",
    ],
)

conn.commit()
print(f"✅ product {len(product_df)}건 적재 완료")

cur.close()
conn.close()

print("🎉 전체 적재 완료!")
