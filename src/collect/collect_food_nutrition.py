"""
식품영양성분DB정보(FoodNtrCpntDbInfo02) 수집 스크립트
- 식약처 공공데이터포털 오픈API에서 타겟 카테고리 데이터를 페이지네이션으로 긁어와 CSV로 저장한다.
- 조인 없이 이 API 단독으로 카테고리/상관관계/제로 키워드 분석에 필요한 컬럼을 뽑는다.

사용 전 체크리스트:
1. 환경변수 FOOD_API_SERVICE_KEY에 본인 data.go.kr 인증키(Decoding/URL Encode 키) 입력
   (터미널에서: export FOOD_API_SERVICE_KEY="발급받은키")
2. CATEGORIES 문자열이 실제 DB의 FOOD_CAT1_NM 값과 정확히 일치하는지 먼저 확인
   -> 확인이 안 됐으면 probe_candidates()로 먼저 후보 문자열들 건수 찔러볼 것
3. FOOD_CAT1_NM 파라미터는 부분/포함 매칭으로 동작하는 것으로 확인됨
   (예: "코코아가공품류"로 쿼리해도 "코코아가공품류 또는 초콜릿류"가 반환됨)
   -> API 필터만 믿지 말고 수집 후 반드시 exact match로 한 번 더 걸러야 함 (filter_exact_category 참고)

변경 이력:
- v2: SERVICE_KEY를 코드에서 제거하고 환경변수로 분리 (키가 대화/커밋 이력에 노출된 적 있어 재발급 권장)
- v2: probe_category에서 ET.ParseError(quota 초과 등으로 XML이 아닌 응답이 올 때)를 못 잡던 문제 수정
- v2: 부분매칭으로 인한 카테고리 오염 방지용 filter_exact_category() 추가
- "과자류,빵류 또는 떡류"는 실제 존재하지 않는 값(0건)이었음 -> "빵 및 과자류"(8772건)로 확인했으나,
  이 카테고리는 품목제조보고번호가 100% 결측인 조리식품(레시피) 데이터로 확인되어 CATEGORIES에서 제외함
- probe_category/probe_candidates 중복 정의돼있던 것 정리
"""

import os
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import requests

from src.config import DATA_DIR, ensure_dir

SERVICE_KEY = os.getenv("FOOD_API_SERVICE_KEY", "").strip()

BASE_URL = "https://apis.data.go.kr/1471000/FoodNtrCpntDbInfo02/getFoodNtrCpntDbInq02"

                                          
                                        
FIELDS = {
    "FOOD_CD": "식품코드",
    "FOOD_NM_KR": "식품명",
    "FOOD_CAT1_NM": "식품대분류",
    "FOOD_CAT2_NM": "식품중분류",
    "ITEM_REPORT_NO": "품목제조보고번호",                                 
    "SERVING_SIZE": "기준량",
    "AMT_NUM1": "에너지",
    "AMT_NUM3": "단백질",
    "AMT_NUM4": "지방",
    "AMT_NUM6": "탄수화물",
    "AMT_NUM7": "당류",
    "AMT_NUM13": "나트륨",
    "AMT_NUM23": "콜레스테롤",
    "AMT_NUM24": "포화지방산",
    "AMT_NUM53": "당알콜",
    "AMT_NUM55": "알룰로오스",
    "AMT_NUM56": "에리스리톨",
    "AMT_NUM60": "포도당",
}

NUMERIC_COLS = ["에너지", "단백질", "지방", "탄수화물", "당류", "나트륨",
                "콜레스테롤", "포화지방산", "당알콜", "알룰로오스", "에리스리톨", "포도당"]

                                                      
                                                      
CATEGORIES = [
    "음료류",
    "과자류·빵류 또는 떡류",                                                 
    "코코아가공품류 또는 초콜릿류",                             
]

NUM_OF_ROWS = 100
SLEEP_SEC = 0.3


def fetch_page(category: str, page_no: int, num_of_rows: int = NUM_OF_ROWS, max_retries: int = 5) -> ET.Element:
    params = {
        "serviceKey": SERVICE_KEY,
        "pageNo": page_no,
        "numOfRows": num_of_rows,
        "type": "xml",
        "FOOD_CAT1_NM": category,
    }
    for attempt in range(1, max_retries + 1):
        try:
            res = requests.get(BASE_URL, params=params, timeout=15)
            res.raise_for_status()
            return ET.fromstring(res.content)
        except requests.exceptions.RequestException as e:
            if attempt == max_retries:
                raise
            wait = 3 * attempt
            print(f"  [{category} p{page_no}] 요청 실패({e.__class__.__name__}) -> {wait}초 후 재시도 ({attempt}/{max_retries})")
            time.sleep(wait)
        except ET.ParseError:
                                                      
            print(f"  [{category} p{page_no}] XML 파싱 실패. 응답 원문 일부: {res.text[:300]!r}")
            if attempt == max_retries:
                raise
            wait = 3 * attempt
            print(f"  -> {wait}초 후 재시도 ({attempt}/{max_retries})")
            time.sleep(wait)


def parse_items(root: ET.Element) -> list[dict]:
    rows = []
    for item in root.findall(".//item"):
        row = {}
        for field in FIELDS:
            el = item.find(field)
            row[field] = el.text if el is not None else None
        rows.append(row)
    return rows


def get_total_count(root: ET.Element) -> int:
    el = root.find(".//totalCount")
    return int(el.text) if el is not None else 0


def collect_category(category: str) -> list[dict]:
    all_rows: list[dict] = []
    page_no = 1

    root = fetch_page(category, page_no)
    total = get_total_count(root)
    print(f"[{category}] 총 {total}건")
    all_rows.extend(parse_items(root))

    while len(all_rows) < total:
        page_no += 1
        time.sleep(SLEEP_SEC)
        root = fetch_page(category, page_no)
        all_rows.extend(parse_items(root))
        print(f"  {len(all_rows)}/{total} 수집")

    return all_rows


def filter_exact_category(df: pd.DataFrame, target: str) -> pd.DataFrame:
    """API의 FOOD_CAT1_NM 필터가 부분매칭으로 동작하는 것으로 확인되어,
    수집 후 정확히 일치하는 값만 다시 걸러내는 안전장치.
    걸러진 값들이 뭐였는지도 같이 출력해서 예상 못한 카테고리가 섞였는지 바로 보이게 함."""
    exact = df[df["식품대분류"] == target]
    dropped = df[df["식품대분류"] != target]
    if len(dropped) > 0:
        print(f"  [부분매칭 정리] '{target}' 쿼리로 받았지만 다른 값이었던 행: {len(dropped)}개")
        print(dropped["식품대분류"].value_counts().to_string())
    return exact


def discover_categories(sample_rows: int = 500) -> None:
    """CATEGORIES 문자열이 실제 값과 맞는지 모를 때, 필터 없이 일부 데이터를 훑어서
    등장하는 FOOD_CAT1_NM 값들을 확인해보는 용도. 참고: 이 API는 앞부분에 조리식품 카테고리가
    몰려있어서 sample_rows가 작으면 가공식품(음료/과자 등) 카테고리가 안 보일 수 있음.
    -> 특정 값이 실제 존재하는지 확실히 알고 싶으면 probe_category()를 쓸 것."""
    params = {
        "serviceKey": SERVICE_KEY,
        "pageNo": 1,
        "numOfRows": sample_rows,
        "type": "xml",
    }
    res = requests.get(BASE_URL, params=params, timeout=10)
    res.raise_for_status()
    root = ET.fromstring(res.content)
    cats = sorted({
        el.text for el in root.findall(".//FOOD_CAT1_NM") if el.text
    })
    print("발견된 FOOD_CAT1_NM 값들:")
    for c in cats:
        print(" -", c)


def probe_category(candidate: str) -> int:
    """실제 존재하는 카테고리 값인지 1건만 요청해서 가볍게 확인.
    반환된 행의 실제 식품대분류 값도 같이 보여줘서 부분매칭 여부를 바로 확인할 수 있게 함."""
    params = {
        "serviceKey": SERVICE_KEY,
        "pageNo": 1,
        "numOfRows": 1,
        "type": "xml",
        "FOOD_CAT1_NM": candidate,
    }
    res = requests.get(BASE_URL, params=params, timeout=10)
    res.raise_for_status()
    try:
        root = ET.fromstring(res.content)
    except ET.ParseError:
        print(f"  '{candidate}' -> XML 파싱 실패. 응답 원문 일부: {res.text[:300]!r}")
        return 0
    total = get_total_count(root)
    items = parse_items(root)
    actual_cat = items[0]["FOOD_CAT1_NM"] if items else None
    match_note = "" if actual_cat == candidate else f"  <- 실제 반환값 다름: {actual_cat!r} (부분매칭 의심)"
    print(f"  '{candidate}' -> {total}건{match_note}")
    return total


def probe_candidates(candidates: list[str]) -> None:
    print("카테고리 후보별 건수:")
    for c in candidates:
        print(f"  '{c}' 확인 중...", flush=True)
        try:
            probe_category(c)
        except requests.exceptions.RequestException as e:
            print(f"  '{c}' -> 요청 실패({e.__class__.__name__}), 건너뜀")
        time.sleep(0.3)


def main() -> None:
    all_data: list[dict] = []
    ensure_dir(DATA_DIR)
    output_path = DATA_DIR / "food_nutrition_raw.csv"

    for cat in CATEGORIES:
        raw_rows = collect_category(cat)
        df_cat = pd.DataFrame(raw_rows)
        df_cat.rename(columns=FIELDS, inplace=True)
        df_cat = filter_exact_category(df_cat, cat)
        all_data.extend(df_cat.to_dict("records"))

        df = pd.DataFrame(all_data)
        for col in NUMERIC_COLS:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"  [중간 저장] 현재까지 {len(df)}행 -> {output_path}")

    dup = df["품목제조보고번호"].duplicated().sum()
    if dup:
        print(f"  [경고] 품목제조보고번호 중복 {dup}건 발견 (카테고리 간 겹침 가능성)")

    print(f"저장 완료: {len(all_data)}행 -> {output_path}")


if __name__ == "__main__":
                                           
                           
                                                                                 
    
                                                                 
    main()