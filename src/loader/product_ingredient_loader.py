import re
from io import StringIO

import pandas as pd
import psycopg2

from src.config import DATA_DIR, DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

CSV_PATH = DATA_DIR / "processed" / "integrated_final_validation.csv"

# ==========================
# DB 연결
# ==========================
conn = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
)

cur = conn.cursor()

# ==========================
# product 조회
# ==========================
product_df = pd.read_sql(
    """
    SELECT id, external_code
    FROM product
    """,
    conn,
)

product_df["external_code"] = product_df["external_code"].astype(str)

product_map = dict(
    zip(
        product_df["external_code"],
        product_df["id"],
    )
)

# ==========================
# ingredient 조회
# ==========================
ingredient_df = pd.read_sql(
    """
    SELECT id, name
    FROM ingredient
    """,
    conn,
)

ingredient_map = dict(
    zip(
        ingredient_df["name"],
        ingredient_df["id"],
    )
)

# ==========================
# CSV 읽기
# ==========================
df = pd.read_csv(
    CSV_PATH,
    dtype={
        "품목제조보고번호": str,
    },
)

records = []


# ==========================
# 원재료 토큰 추출
# ==========================
def extract_tokens(raw_text):
    """
    예시

    설탕, 혼합제제(수크랄로스, 아세설팜칼륨), 구연산(무수)

    ↓

    [
        "설탕",
        "혼합제제",
        "수크랄로스",
        "아세설팜칼륨",
        "구연산",
        "무수"
    ]
    """

    text = str(raw_text)

    tokens = []

    # 최상위 쉼표 기준 분리 (괄호 내부 쉼표 제외)
    depth = 0
    current = ""

    for ch in text:
        if ch == "(":
            depth += 1
            current += ch
        elif ch == ")":
            depth -= 1
            current += ch
        elif ch == "," and depth == 0:
            if current.strip():
                tokens.append(current.strip())
            current = ""
        else:
            current += ch

    if current.strip():
        tokens.append(current.strip())

    results = []

    for token in tokens:
        token = token.strip()

        if not token:
            continue

        # 원본 토큰
        results.append(token)

        # 괄호 밖 이름
        outside = re.sub(r"\(.*?\)", "", token).strip()
        if outside and outside != token:
            results.append(outside)

        # 괄호 안 내용
        inside = re.findall(r"\((.*?)\)", token)

        for item in inside:
            for sub in item.split(","):
                sub = sub.strip()
                if sub:
                    results.append(sub)

    # 순서 유지하며 중복 제거
    return list(dict.fromkeys(results))


# ==========================
# 매핑
# ==========================
for _, row in df.iterrows():

    external_code = str(row["품목제조보고번호"])

    if external_code not in product_map:
        continue

    raw = row.get("RAWMTRL_NM")

    if pd.isna(raw):
        continue

    product_id = product_map[external_code]

    tokens = extract_tokens(raw)

    sequence = 1

    for token in tokens:

        if token in ingredient_map:

            records.append(
                (
                    product_id,
                    ingredient_map[token],
                    sequence,
                )
            )

            sequence += 1

# ==========================
# 중복 제거
# ==========================
records = list(dict.fromkeys(records))

print(f"총 {len(records)}건 매핑")

# ==========================
# COPY
# ==========================
buffer = StringIO()

pd.DataFrame(
    records,
    columns=[
        "product_id",
        "ingredient_id",
        "sequence",
    ],
).to_csv(
    buffer,
    sep="\t",
    index=False,
    header=False,
)

buffer.seek(0)

cur.copy_expert(
    """
    COPY product_ingredient
    (product_id, ingredient_id, sequence)
    FROM STDIN
    WITH (FORMAT text)
    """,
    buffer,
)

conn.commit()

print("✅ product_ingredient 적재 완료!")

cur.close()
conn.close()