"""
product_ingredient_mapping.csv (external_food_code, ingredient_code, ingredient_name, sequence)
-> product_ingredient 테이블 (product_id, ingredient_id, sequence) 로 변환해서 insert.

product_id / ingredient_id는 둘 다 IDENTITY라 로컬 CSV엔 없음 -> Supabase에서 라이브 조회해서 매핑.

사전 정리 로직 (fk 위반 방지)
---------------------------
1. product 테이블에 없는 external_food_code 행 제외 (fk_product_ingredient_product 위반 방지)
2. ingredient 테이블에 없는 ingredient_code 행 제외 (fk_product_ingredient_ingredient 위반 방지)
3. (external_food_code, ingredient_code) 중복 시 sequence가 가장 작은 것만 유지
   (uk_product_ingredient UNIQUE(product_id, ingredient_id) 위반 방지)

사전 조건
--------
1. product, ingredient 테이블에 데이터가 이미 들어가 있어야 함
2. pip install python-dotenv psycopg2-binary pandas --break-system-packages
3. .env 에 SUPABASE_DB_URL 설정 (import_product_to_supabase.py 와 동일)
"""

import io
import os
import sys
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv()

MAPPING_CSV_PATH = Path("data/processed/product_ingredient_mapping.csv")


def _assert_not_lfs_pointer(path: Path) -> None:
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
            "SUPABASE_DB_URL이 설정되지 않았습니다. .env 파일을 확인하세요."
        )
    return dsn


def fetch_id_map(conn, table: str, key_col: str) -> dict:
    with conn.cursor() as cur:
        cur.execute(f"SELECT id, {key_col} FROM {table}")
        # DB 쪽 키를 문자열로 통일 (CSV 쪽과 타입 맞추기 위함)
        return {str(key).strip(): id_ for id_, key in cur.fetchall()}


def build_copy_buffer(df: pd.DataFrame, columns: list[str]) -> io.StringIO:
    buf = io.StringIO()
    df[columns].to_csv(buf, index=False, header=False, na_rep="\\N")
    buf.seek(0)
    return buf


def main() -> None:
    _assert_not_lfs_pointer(MAPPING_CSV_PATH)

    # external_food_code / ingredient_code는 숫자처럼 보여도 반드시 문자열로 읽어야 함
    # (안 그러면 int64로 읽혀서 DB의 str 키와 매칭이 100% 실패함)
    df = pd.read_csv(
        MAPPING_CSV_PATH,
        encoding="utf-8-sig",
        dtype={"external_food_code": str, "ingredient_code": str},
    )
    print(f"원본 매핑 파일: {len(df)}행")

    # 혹시 엑셀 등에서 "12345.0"처럼 소수점이 붙어 저장된 경우 방어적으로 제거 + 공백 제거
    df["external_food_code"] = (
        df["external_food_code"].str.replace(r"\.0$", "", regex=True).str.strip()
    )
    df["ingredient_code"] = (
        df["ingredient_code"].str.replace(r"\.0$", "", regex=True).str.strip()
    )

    conn = psycopg2.connect(get_dsn())
    try:
        product_map = fetch_id_map(conn, "product", "external_code")
        ingredient_map = fetch_id_map(conn, "ingredient", "code")
        print(f"product 테이블: {len(product_map)}행 조회")
        print(f"ingredient 테이블: {len(ingredient_map)}행 조회")

        # 1. product FK 불일치 제외
        before = len(df)
        df = df[df["external_food_code"].isin(product_map)]
        dropped_product = before - len(df)

        # 2. ingredient FK 불일치 제외
        before = len(df)
        df = df[df["ingredient_code"].isin(ingredient_map)]
        dropped_ingredient = before - len(df)

        # 3. (external_food_code, ingredient_code) 중복 -> sequence 최소값만 유지
        before = len(df)
        df = df.sort_values("sequence").drop_duplicates(
            subset=["external_food_code", "ingredient_code"], keep="first"
        )
        dropped_dup = before - len(df)

        print(f"product 미매칭 제외: {dropped_product}행")
        print(f"ingredient 미매칭 제외: {dropped_ingredient}행")
        print(f"(product, ingredient) 중복 제외: {dropped_dup}행")

        # id 치환
        df["product_id"] = df["external_food_code"].map(product_map)
        df["ingredient_id"] = df["ingredient_code"].map(ingredient_map)
        final_df = df[["product_id", "ingredient_id", "sequence"]]

        print(f"최종 insert 대상: {len(final_df)}행")
        if len(final_df) == 0:
            print("insert할 행이 없습니다. 종료합니다.")
            return

        buf = build_copy_buffer(final_df, ["product_id", "ingredient_id", "sequence"])
        with conn.cursor() as cur:
            cur.copy_expert(
                "COPY product_ingredient (product_id, ingredient_id, sequence) "
                "FROM STDIN WITH (FORMAT csv, NULL '\\N')",
                buf,
            )
        conn.commit()
        print(f"완료: {len(final_df)}행 insert 성공")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()