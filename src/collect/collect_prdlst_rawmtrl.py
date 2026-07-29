"""
식품안전나라 - 식품(첨가물)품목제조보고(원재료) (C002) 전체 벌크 수집.
총 건수가 100만 건이 넘는 규모라, 청크를 받는 즉시 CSV에 이어쓰기(append)한다.
중간에 끊기면 콘솔에 마지막으로 찍힌 "마지막 성공 endIdx" 값을 보고
START_FROM을 그 다음 번호로 바꿔서 다시 실행하면 이어서 받을 수 있다.
(이어받기 모드에서는 기존 파일에 그대로 추가되므로, 처음부터 다시 받을 땐
 기존 CSV 파일을 먼저 지우거나 START_FROM=1로 유지할 것.)
"""

import os
import csv
import time
from pathlib import Path

import requests

from src.config import DATA_DIR, ensure_dir

KEY_ID = os.getenv("FOODSAFETY_API_KEY_ID", "").strip()
SERVICE_ID = os.getenv("FOODSAFETY_SERVICE_ID", "C002").strip()
BASE_URL = "http://openapi.foodsafetykorea.go.kr/api"
OUT_PATH = DATA_DIR / "prdlst_rawmtrl_raw.csv"

CHUNK_SIZE = 1000
SLEEP_SEC = 0.2
START_FROM = 838001                                       


def fetch_chunk(start_idx: int, end_idx: int) -> dict:
    url = f"{BASE_URL}/{KEY_ID}/{SERVICE_ID}/json/{start_idx}/{end_idx}"
    res = requests.get(url, timeout=30)
    res.raise_for_status()
    return res.json()


def main() -> None:
    first = fetch_chunk(1, 1)
    body = first.get(SERVICE_ID, {})
    result = body.get("RESULT", {})
    print("RESULT:", result)

    if result.get("CODE") != "INFO-000":
        print("정상 응답이 아닙니다. raw 응답:", first)
        raise SystemExit("total_count를 확인할 수 없어 중단합니다. 위 RESULT/raw 응답을 확인하세요.")

    total = int(body["total_count"])
    print(f"총 건수: {total:,}")

    ensure_dir(DATA_DIR)
    mode = "a" if START_FROM > 1 else "w"
    write_header = START_FROM == 1

    with open(OUT_PATH, mode, newline="", encoding="utf-8-sig") as f:
        writer = None
        start = START_FROM
        while start <= total:
            end = min(start + CHUNK_SIZE - 1, total)
            try:
                chunk = fetch_chunk(start, end)
            except Exception as e:
                print(f"[{start}-{end}] 요청 실패: {e} -> 5초 후 재시도")
                time.sleep(5)
                continue

            rows = chunk.get(SERVICE_ID, {}).get("row", [])
            if not rows:
                if end >= total:
                    print(f"[{start}-{end}] 빈 응답 (전체 건수 도달) -> 수집 종료")
                    break
                print(f"[{start}-{end}] 빈 응답이지만 아직 전체 건수 미달 -> 일시적 오류로 보고 5초 후 재시도")
                time.sleep(5)
                continue

            if writer is None:
                writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                if write_header:
                    writer.writeheader()

            writer.writerows(rows)
            print(f"  {end:,}/{total:,} 수집 (마지막 성공 endIdx={end})")

            start = end + 1
            time.sleep(SLEEP_SEC)

    print(f"저장 완료 -> {OUT_PATH}")


if __name__ == "__main__":
    main()