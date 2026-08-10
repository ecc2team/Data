import os
import sys

import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from src.config import PROCESSED_DATA_DIR

# =====================================================
# 파일 경로
# =====================================================
INPUT_FILE = PROCESSED_DATA_DIR / "integrated_final_validation.csv"
OUTPUT_FILE = PROCESSED_DATA_DIR / "product_table_data.csv"

# =====================================================
# CSV 읽기
# =====================================================
try:
    df = pd.read_csv(INPUT_FILE, encoding="utf-8-sig")
except UnicodeDecodeError:
    df = pd.read_csv(INPUT_FILE, encoding="cp949")

df.columns = df.columns.str.strip()

# =====================================================
# 품목제조보고번호(=external_code) 지수표기 복구
# =====================================================
def fix_scientific_notation(val):
    if pd.isna(val):
        return None

    val = str(val).strip()

    try:
        return str(int(float(val)))
    except ValueError:
        return val


ext_code_col = (
    "품목제조보고번호"
    if "품목제조보고번호" in df.columns
    else "품목제조번호"
)

df[ext_code_col] = df[ext_code_col].apply(fix_scientific_notation)

print(
    f"⚠️ external_code 결측치 : "
    f"{df[ext_code_col].isna().sum()}건 / {len(df)}건"
)

# =====================================================
# grade 생성
# =====================================================
grade_mapping = {
    "Good": 1,
    "보통": 2,
    "Bad": 3,
}

df["grade"] = (
    df["룰기반_등급"]
    .astype(str)
    .str.strip()
    .map(grade_mapping)
    .fillna(3)
    .astype(int)
)

# =====================================================
# warning_additive 생성
# =====================================================
df["warning_additive"] = (
    df["RAWMTRL_NM"]
    .fillna("")
    .str.contains("카라멜색소|캐러멜색소", regex=True)
)

# =====================================================
# 숫자 컬럼 정리
# =====================================================
for col in ["에너지", "당류", "나트륨"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

before = len(df)

df = df.dropna(subset=["에너지"])

if before != len(df):
    print(f"⚠️ 에너지 NULL {before-len(df)}건 제거")

df["에너지"] = df["에너지"].round().astype(int)

# =====================================================
# DB 컬럼만 추출
# =====================================================
df_final = df[
    [
        ext_code_col,
        "식품명",
        "식품대분류",
        "표준원재료명",
        "grade",
        "warning_additive",
        "에너지",
        "당류",
        "나트륨",
    ]
].copy()

df_final.rename(
    columns={
        ext_code_col: "external_code",
        "식품명": "name",
        "식품대분류": "category_name",
        "표준원재료명": "raw_materials",
        "에너지": "calories",
        "당류": "sugar",
        "나트륨": "sodium",
    },
    inplace=True,
)

# =====================================================
# external_code 중복 제거
# (NULL은 모두 유지)
# =====================================================
has_code = df_final[df_final["external_code"].notna()].copy()
no_code = df_final[df_final["external_code"].isna()].copy()

print(
    f"external_code 있음 : {len(has_code)}건 / "
    f"없음 : {len(no_code)}건"
)

has_code = has_code.sort_values(
    "name",
    key=lambda x: x.str.len(),
    ascending=False,
)

has_code = has_code.drop_duplicates(
    subset="external_code",
    keep="first",
)

df_final = pd.concat(
    [has_code, no_code],
    ignore_index=True,
)

assert (
    df_final[df_final["external_code"].notna()]["external_code"]
    .duplicated()
    .sum()
    == 0
)

print("✅ external_code 중복 제거 완료")

# =====================================================
# 저장
# =====================================================
df_final.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8-sig",
)

print()
print("===================================")
print("DB 적재용 CSV 생성 완료")
print("===================================")
print(f"저장 위치 : {OUTPUT_FILE}")
print(f"최종 건수 : {len(df_final)}")
print(f"컬럼 : {list(df_final.columns)}")