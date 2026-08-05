"""
Supabase Table Editor의 CSV import GUI는 빈 셀을 NULL로 제대로 못 넘기는 알려진 버그가 있음
(https://github.com/supabase/supabase/issues/17835, #43258 등).
이 스크립트는 GUI를 거치지 않고 psycopg2 COPY로 직접 insert하며,
결측값을 "\\N" 이라는 명시적 NULL 센티널로 표시해서 이 문제를 완전히 우회함.

사전 조건
--------
1. V2__alter_product_sodium_nullable.sql 마이그레이션이 먼저 적용되어 있어야 함
   (sodium이 NOT NULL이면 NULL insert 시 not-null constraint violation 발생)
2. data/processed/db_ready_data.csv 는 category_id 매핑이 이미 완료된 상태여야 함
   (map_category_to_id.py 실행 후)
3. .env 또는 환경변수에 Supabase 연결 정보(SUPABASE_DB_URL)가 설정되어 있어야 함
   예: postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres
   (Supabase 대시보드 > Project Settings > Database > Connection string)
"""

import io
import os
from pathlib import Path

import pandas as pd
import psycopg2

CSV_PATH = Path("data/processed/db_ready_data.csv")

# product 테이블 DDL 컬럼 순서와 동일하게 맞춤 (id, image_url, deleted_at은 제외 - 자동/nullable)
COLUMNS = [
    "category_id",
    "external_code",
    "name",
    "raw_materials",
    "grade",
    "warning_additive",
    "calories",
    "sugar",
    "sodium",
]


def _assert_not_lfs_pointer(path: Path) -> None:
    with open(path, "rb") as f:
        head = f.read(200)
    if head.startswith(b"version https://git-lfs.github.com"):
        raise RuntimeError(
            f"{path} 가 Git LFS 포인터 파일입니다. 터미널에서 `git lfs pull` 먼저 실행하세요."
        )


def build_copy_buffer(df: pd.DataFrame) -> io.StringIO:
    """DataFrame -> COPY용 CSV 버퍼. 결측치는 명시적으로 \\N 문자열로 표시."""
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep="\\N")
    buf.seek(0)
    return buf


def main() -> None:
    _assert_not_lfs_pointer(CSV_PATH)

    df = pd.read_csv(CSV_PATH, encoding="utf-8-sig")
    missing_cols = set(COLUMNS) - set(df.columns)
    if missing_cols:
        raise KeyError(f"CSV에 없는 컬럼: {missing_cols}")
    df = df[COLUMNS]

    dsn = os.environ.get("SUPABASE_DB_URL")
    if not dsn:
        raise EnvironmentError(
            "SUPABASE_DB_URL 환경변수가 없습니다. "
            "Supabase 대시보드 > Project Settings > Database > Connection string 값을 설정하세요."
        )

    buf = build_copy_buffer(df)
    col_list = ", ".join(COLUMNS)

    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.copy_expert(
                f"COPY product ({col_list}) FROM STDIN WITH (FORMAT csv, NULL '\\N')",
                buf,
            )
        conn.commit()
        print(f"완료: {len(df)}행 insert 성공")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()