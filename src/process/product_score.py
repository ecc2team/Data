"""
product.score / product.summary 컬럼 채우기 스크립트.

score 계산 방식
--------------
1. product.grade(1~3)로 점수 밴드(구간)를 정함
   grade 1 (프리미엄 클린 제로) -> 90~100
   grade 2 (일반 제로)          -> 70~89
   grade 3 (가짜 제로 주의)      -> 40~69
2. 해당 밴드 안에서, ingredient.risk_level 분포(PREMIUM/WARNING 개수)로 세부 점수 조정
   - 개수를 그대로 곱하지 않고 log1p로 점감시켜서, 성분 몇 개만 있어도
     바로 밴드 최고점/최저점에 꽂히는 걸 방지 (원래 버그: width 비례 계수라
     등급 상관없이 premium_count>=3~4면 무조건 ceiling)
3. warning_additive(카라멜색소 등)면 밴드 안에서 추가 감점
   -> 어떤 경우에도 밴드를 벗어나지 않음 (등급-점수 모순 방지)

summary 계산 방식
-----------------
"특징(왜)" + "결론(등급)" 두 조각을 조립해서 만듦. 결론은 grade로 고정된 3종 문구,
특징은 아래 우선순위로 실제 매칭된 성분 이름을 넣어 상품마다 자연스럽게 달라지게 함.

분기 우선순위 (특징 파트):
1. warning_additive=True            -> 우려 첨가물 언급
2. warning_count > 0                -> 매칭된 WARNING 성분 이름 언급
3. premium_count가 saturation 근처   -> 매칭된 PREMIUM 성분 이름 언급
4. 나머지                            -> 무난하다는 중립 문구

score와 summary는 같은 입력값(grade, warning_additive, premium/warning 성분 분포)에서
나오므로 한 번의 쿼리·순회로 같이 계산한다. 프론트/API에서 매 요청마다 재조립하지
않도록 배치 스크립트가 계산 -> DB 저장 -> API는 select만 하는 구조를 따른다.

주의 (이번에 확인된 것들)
------------------------
- ingredient 테이블은 "전체 원재료 목록"이 아니라 당류/감미료/전분/색소
  워치리스트(16종)라서 product당 매칭 개수가 대부분 1~3개로 작음.
  -> premium_count / total_count 같은 비율 계산은 total_count=1인 상품
     (전체의 32%)에서 바로 100%가 나와버리므로 절대 쓰지 말 것.
     raw count 기반 + log1p 점감으로 계산.
- COLOR 타입(카라멜색소)은 warning_count 집계에서 애초에 제외되어 있음
  (`AND i.ingredient_type <> 'COLOR'`). warning_additive 플래그와
  중복 감점/중복 언급되지 않게 이 필터는 절대 빼면 안 됨. summary의
  warning_names도 동일 필터를 통과한 값이라 warning_additive 케이스와 겹치지 않음.

사전 조건
--------
1. ALTER TABLE product ADD COLUMN score SMALLINT; 마이그레이션 적용 완료
2. ALTER TABLE product ADD COLUMN summary TEXT; 마이그레이션 적용 완료
   (스키마에 이미 있는 ai_verdict 컬럼이 이 용도와 겹치면 그걸 재사용해도 됨 —
   그 경우 아래 COPY/UPDATE의 컬럼명만 summary -> ai_verdict로 바꾸면 됨)
3. product, ingredient, product_ingredient 데이터 이미 채워져 있어야 함 (이미 완료된 상태)
4. .env에 SUPABASE_DB_URL 설정
"""

import io
import math
import os

import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv()

GRADE_BANDS = {
    1: (90, 100),
    2: (70, 89),
    3: (40, 69),
}

GRADE_VERDICT = {
    1: "믿고 선택할 수 있는 프리미엄 제로 상품입니다.",
    2: "일반적인 수준의 제로 상품입니다.",
    3: "가짜 제로일 가능성이 있으니 성분표를 꼭 확인하세요.",
}

# 성분 개수가 saturation 기준에 도달하면 밴드 끝(ceiling/floor)에 도달.
# 고정값 대신 등급별 실제 분포(percentile)에서 자동으로 뽑음 -> 상품 데이터가
# 늘어나도 매번 손으로 재조정할 필요 없음. 이 percentile이 사실상 유일한 튜닝 값:
# 낮추면(예: 0.90) ceiling에 닿는 상품이 늘고, 높이면(예: 0.98) 줄어듦.
# summary의 "프리미엄 성분 위주" 분기 판단에도 동일 기준을 재사용한다.
SATURATION_PERCENTILE = 0.95


def compute_saturation_counts(df: pd.DataFrame, percentile: float = SATURATION_PERCENTILE) -> dict:
    """등급별 premium_count/warning_count percentile을 saturation 기준으로 계산."""
    saturation = {}
    for grade, sub in df.groupby("grade"):
        p_sat = max(1, int(round(sub["premium_count"].quantile(percentile))))
        w_sat = max(1, int(round(sub["warning_count"].quantile(percentile))))
        saturation[grade] = (p_sat, w_sat)
    return saturation


def get_dsn() -> str:
    dsn = os.environ.get("SUPABASE_DB_URL")
    if not dsn:
        raise EnvironmentError("SUPABASE_DB_URL이 설정되지 않았습니다.")
    return dsn


def fetch_product_ingredient_stats(conn) -> pd.DataFrame:
    """
    product당 1행. premium_count/warning_count/total_count는 score 계산용,
    premium_names/warning_names는 summary 조립용 — 두 번 조회하지 않도록
    ARRAY_AGG로 한 쿼리에서 같이 끌고 온다.

    FILTER 안에서 ARRAY_AGG(i.name) FILTER (...)로 조건별 이름만 모으고,
    LEFT JOIN이라 매칭이 없는 경우 NULL이 나오므로 COALESCE로 빈 배열 처리.
    """
    # NOTE: ingredient_type <> 'COLOR' 필터에 'ALLERGEN'을 추가로 제외함.
    # 알레르기 유발물질(우유/계란/밀/대두/땅콩/아몬드/호두/복숭아)은 사용자 개인화
    # 필터(user_allergy) 전용이라 product 전체 등급/점수 계산에 섞이면 안 됨
    # (예: 밀가루가 384건으로 흔하다고 warning_count에 잡히면 빵류 점수가
    # 알레르기 없는 사용자 기준에서도 부당하게 깎임). COLOR와 동일하게
    # premium/warning 집계와 summary용 이름 배열 양쪽에서 제외해야 함.
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


def compute_score(row, saturation: dict) -> int:
    floor, ceiling = GRADE_BANDS[row["grade"]]
    width = ceiling - floor
    mid = floor + width / 2
    half_band = width / 2

    # log1p로 점감: 성분 1개->2개 갈 때는 크게 오르고, 개수가 늘수록
    # 한 개당 영향력이 줄어듦. 등급별 premium_sat/warning_sat 개수에 도달하면
    # 그때 half_band(밴드 절반)에 도달 -> 그 이상은 clamp.
    premium_sat, warning_sat = saturation[row["grade"]]
    premium_signal = math.log1p(row["premium_count"]) / math.log1p(premium_sat)
    warning_signal = math.log1p(row["warning_count"]) / math.log1p(warning_sat)

    adjustment = half_band * premium_signal - half_band * warning_signal
    adjustment = max(-half_band, min(half_band, adjustment))  # 밴드 절반 넘게 흔들리지 않게 clamp

    score = mid + adjustment

    if row["warning_additive"]:
        score -= width * 0.3

    return int(max(floor, min(ceiling, round(score))))


def is_near_saturation(row, saturation: dict) -> bool:
    """premium_count가 saturation 기준 근처(=거의 만점권)인지 판단."""
    premium_sat, _ = saturation[row["grade"]]
    return row["premium_count"] >= premium_sat


def build_summary(row, saturation: dict) -> str:
    premium_names = row["premium_names"] or []
    warning_names = row["warning_names"] or []

    # grade=1(프리미엄)인데 WARNING 성분이 매칭된 모순 케이스는
    # "믿고 선택하세요" 문구를 그대로 못 씀 -> 신중 문구로 별도 처리
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


def flag_grade_ingredient_conflicts(df: pd.DataFrame) -> pd.DataFrame:
    """
    grade와 ingredient.risk_level 매칭이 서로 모순되는 케이스를 찾아낸다.

    배경: grade는 product_table_data.csv 생성 스크립트에서 `룰기반_등급`을
    그대로 매핑한 값이라, product_score.py가 여기서 join하는
    ingredient.risk_level(PREMIUM/WARNING) 워치리스트와는 완전히 독립적인
    파이프라인에서 나온다. 그래서 "grade 1(프리미엄)인데 WARNING 성분이
    매칭됨" 같은 조합이 로직 버그 없이도 나올 수 있다.

    이 함수는 그 값을 고치지 않는다 (grade 산정 로직은 이 스크립트 밖,
    product_table_data.csv를 만드는 단계에 있어서 여기서 손댈 수 없음).
    대신 모순 건수를 눈에 보이게 로그로 남겨서, `룰기반_등급` 쪽을 나중에
    재검토할 때 근거 자료로 쓸 수 있게 한다. score/summary 값 자체는
    건드리지 않는다.

    모순 정의:
    - grade 1(프리미엄) + warning_count > 0
    - grade 3(가짜 제로 주의) + premium_count > 0 이고 warning_count == 0
      (경고 성분 없이 프리미엄 성분만 있는데 최하 등급인 경우)
    """
    grade1_with_warning = df[(df["grade"] == 1) & (df["warning_count"] > 0)].copy()
    grade1_with_warning["conflict_type"] = "grade1_but_has_warning"

    grade3_without_warning = df[
        (df["grade"] == 3) & (df["premium_count"] > 0) & (df["warning_count"] == 0)
    ].copy()
    grade3_without_warning["conflict_type"] = "grade3_but_only_premium"

    conflicts = pd.concat([grade1_with_warning, grade3_without_warning], ignore_index=True)

    if len(conflicts) == 0:
        print("\ngrade-ingredient 모순 케이스: 없음")
        return conflicts

    print(f"\n⚠️  grade-ingredient 모순 케이스: {len(conflicts)}건")
    for conflict_type, sub in conflicts.groupby("conflict_type"):
        print(f"  - {conflict_type}: {len(sub)}건")
    print("  (grade는 product_table_data.csv의 룰기반_등급에서 오고,")
    print("   ingredient.risk_level 매칭과는 독립적이라 발생 가능. score/summary는 미수정.")
    print("   룰기반_등급 산정 로직 재검토용으로 아래 CSV 확인)")

    return conflicts


def build_copy_buffer(df: pd.DataFrame) -> io.StringIO:
    buf = io.StringIO()
    df[["product_id", "score", "summary"]].to_csv(buf, index=False, header=False)
    buf.seek(0)
    return buf


def main() -> None:
    conn = psycopg2.connect(get_dsn())
    try:
        df = fetch_product_ingredient_stats(conn)
        print(f"대상 product: {len(df)}건")

        saturation = compute_saturation_counts(df)
        print(f"saturation 기준 (percentile={SATURATION_PERCENTILE}): {saturation}")

        df["score"] = df.apply(lambda row: compute_score(row, saturation), axis=1)
        df["summary"] = df.apply(lambda row: build_summary(row, saturation), axis=1)

        conflicts = flag_grade_ingredient_conflicts(df)
        if len(conflicts) > 0:
            conflicts_path = "grade_ingredient_conflicts.csv"
            conflicts.to_csv(conflicts_path, index=False, encoding="utf-8-sig")
            print(f"  -> 상세 내역 저장: {conflicts_path} (팀/멘토님 공유용)")
            
        # ceiling/floor 클러스터링이 적절한 수준인지 바로 확인
        for grade, (floor, ceiling) in GRADE_BANDS.items():
            n_grade = (df["grade"] == grade).sum()
            n_ceiling = ((df["grade"] == grade) & (df["score"] == ceiling)).sum()
            n_floor = ((df["grade"] == grade) & (df["score"] == floor)).sum()
            print(f"  grade {grade}: {n_grade}건 중 ceiling({ceiling}) {n_ceiling}건 / floor({floor}) {n_floor}건")

        # summary 분기 분포도 같이 확인 (거의 다 같은 문구로 쏠리는지 체크용)
        print("\nsummary 예시 3건:")
        for _, row in df.sample(min(3, len(df))).iterrows():
            print(f"  [product_id={row['product_id']}] {row['summary']}")

        with conn.cursor() as cur:
            cur.execute("""
                CREATE TEMP TABLE tmp_product_score (
                    product_id BIGINT,
                    score SMALLINT,
                    summary TEXT
                ) ON COMMIT DROP
            """)
            buf = build_copy_buffer(df)
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
        print(f"\n완료: {len(df)}건 score/summary 업데이트 성공")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()