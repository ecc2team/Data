# Zeropick

Zeropick은 제로/무설탕 제품의 실제 안전성과 마케팅 표기 간 차이를 분석하기 위한 데이터 파이프라인 프로젝트입니다. 원본 데이터 수집부터 전처리, 등급 분류, DB 적재(스코어/요약 계산 포함), 시각화까지 하나의 흐름으로 처리할 수 있도록 구성되어 있습니다.

## 1. 프로젝트 개요

이 프로젝트는 다음 순서로 동작합니다.

1. 원본 데이터 수집
2. ingredient 마스터 데이터 구축 (감미료/전분/색소/알레르기 워치리스트)
3. 제로 제품 기준 데이터 구축 (원재료 클러스터링 포함)
4. 룰 기반 등급 분류
5. DB 적재용 정제 데이터 생성
6. Supabase 적재 및 score/summary 계산
7. 시각화 결과물 생성

---

## 2. 폴더 구조

- data/
  - raw/: 원본 데이터 CSV
    - food_nutrition_raw.csv
    - prdlst_rawmtrl_raw.csv
  - processed/: 전처리, 등급 분류, DB 적재용 중간 산출물
  - final/: DB 적재용 최종 마스터 데이터
    - ingredient.csv
- outputs/
  - charts/: 시각화 결과 이미지(PNG)
- src/
  - collect/: 원본 데이터 수집 스크립트
  - process/: ingredient 마스터 구축, 전처리, 등급 분류, DB 적재 스크립트
  - visualization/: 시각화용 스크립트
  - config.py: 프로젝트 공통 경로 설정

---

## 3. 실행 전 준비

### 3.1 Python 환경 구성

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3.2 환경 변수 설정

프로젝트 루트에 `.env` 파일을 두고 아래 값을 채웁니다.

```env
# data.go.kr 공공데이터포털 - 식품영양성분DB (collect_food_nutrition.py)
FOOD_API_SERVICE_KEY=발급받은_인증키

# 식품안전나라 openapi - 품목제조보고 원재료 C002 (collect_prdlst_rawmtrl.py)
FOODSAFETY_API_KEY_ID=발급받은_인증키
# FOODSAFETY_SERVICE_ID=C002   # 기본값 C002, 보통 안 건드려도 됨

# Supabase Postgres 접속 (load_all_to_supabase.py)
# Supabase 대시보드 > Project Settings > Database > Connection string
SUPABASE_DB_URL=postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres
```

`src/config.py`에서 데이터/출력 경로를 공통 관리하므로, 스크립트 실행 위치와 무관하게 경로를 재사용할 수 있습니다. DB 접속은 위 `SUPABASE_DB_URL` 하나로 통일되어 있습니다(로컬 Postgres 접속 방식은 더 이상 쓰지 않음).

---

## 4. 전체 파이프라인 실행 순서

### 4.1 원본 데이터 수집

```bash
python src/collect/collect_prdlst_rawmtrl.py
python src/collect/collect_food_nutrition.py
```

수집 결과는 각각 `data/raw/`에 저장됩니다. `collect_prdlst_rawmtrl.py`는 100만 건 이상을 청크 단위로 이어받으므로, 중간에 끊기면 콘솔에 찍힌 마지막 `endIdx`를 보고 스크립트 상단 `START_FROM` 값을 조정해 재실행합니다.

### 4.2 ingredient 마스터 데이터 생성

```bash
python src/process/build_ingredient_master.py
```

`data/final/ingredient.csv`가 생성됩니다. 감미료·당알코올·전분·착색료·알레르기 유발물질을 PREMIUM/GENERAL/WARNING 등급으로 정리한 워치리스트로, 이후 등급 판정(4.3)과 Supabase `ingredient` 테이블 적재(4.6) 양쪽에서 기준 데이터로 쓰입니다. 원본 수집 다음, 등급 판정 이전에 실행해야 합니다.

### 4.3 제로 제품 기준 데이터 생성

```bash
python src/process/build_zero_product_base_data.py
```

이 단계에서 다음 파일이 생성됩니다.

- `data/processed/zeropick_base_data_v4.csv`
- `data/processed/ingredient_clusters_result.csv`
- `data/processed/zeropick_blacklist_candidates.csv` (최종등급 3 상품이 있을 때만)

원재료명 클러스터링에 문장 임베딩 모델(`jhgan/ko-sroberta-multitask`)을 사용하므로 최초 실행 시 모델 다운로드로 시간이 걸릴 수 있습니다.

### 4.4 룰 기반 등급 분류

```bash
python src/process/apply_rule_grading.py
```

`data/processed/integrated_final_validation.csv`가 생성됩니다. 예전에는 mDeBERTa 기반 zero-shot 교차검증까지 포함한 버전이었으나, product.grade로 실제 DB에 들어가는 값은 항상 룰기반 등급이었고 로컬 CPU에서 zero-shot 추론 비용 대비 검증 가치가 낮아 zero-shot 단계는 제거했습니다. (원재료 클러스터링에 쓰는 `sentence-transformers`와는 별개로, `torch`/`transformers` 직접 의존은 이 단계에서 더 이상 필요 없습니다.)

### 4.5 DB 적재용 데이터 생성

```bash
python src/process/prepare_product_table_data.py
python src/process/build_product_ingredient_mapping.py
```

생성되는 주요 파일:

- `data/processed/product_table_data.csv`
- `data/processed/product_ingredient_mapping.csv`

### 4.6 Supabase 적재 (score/summary 계산 포함)

```bash
python src/process/load_all_to_supabase.py                # 기존 데이터 정리 후 전체 재적재
python src/process/load_all_to_supabase.py --no-truncate   # 정리 없이 이어서 (최초 적재 또는 재시도용)
```

`data/final/ingredient.csv`, `data/processed/product_table_data.csv`, `data/processed/product_ingredient_mapping.csv` 세 파일을 FK 순서(ingredient → category → product → product_ingredient)에 맞춰 적재한 뒤, 마지막 단계에서 `product.score`/`product.summary`를 계산해 UPDATE합니다.

grade(룰기반 등급)와 ingredient 워치리스트 매칭 결과는 서로 독립적인 파이프라인에서 나오는 값이라, 둘이 서로 모순되는 상품(예: 프리미엄 등급인데 WARNING 성분이 매칭됨)이 나올 수 있습니다. 이런 케이스는 실행 중 `grade_ingredient_conflicts.csv`로 로그를 남기니, 등급 산정 로직을 재검토할 때 참고 자료로 씁니다.

### 4.7 시각화 결과물 생성

```bash
python src/visualization/export_chart_data.py
python src/visualization/chart1_chart2_visualization.py
```

생성되는 결과물:

- `data/processed/chart1_scatter_data.csv`
- `data/processed/chart2_sweetener_trend.csv`
- `outputs/charts/chart1_scatter.png`, `outputs/charts/chart2_sweetener_heatmap.png`

PNG는 `.gitignore`에 포함되어 있어 Git에는 올라가지 않고 로컬에만 생성됩니다.

---

## 5. 주요 산출물

| 단계 | 주요 산출물 |
| --- | --- |
| 원본 데이터 수집 | `data/raw/*.csv` |
| ingredient 마스터 | `data/final/ingredient.csv` |
| 기본 데이터 구축 | `data/processed/zeropick_base_data_v4.csv` |
| 등급 분류 | `data/processed/integrated_final_validation.csv` |
| DB 적재용 데이터 | `data/processed/product_table_data.csv`, `product_ingredient_mapping.csv` |
| Supabase 적재 | `product`/`ingredient`/`product_ingredient` 테이블 (score·summary 포함) |
| 시각화 | `outputs/charts/*.png` |

---

## 6. 참고 사항

- 경로 설정은 `src/config.py`에서 관리하고, DB 접속은 `SUPABASE_DB_URL` 하나로 통일되어 있습니다.
- 대용량 데이터 파일은 Git LFS로 추적됩니다. 클론 후 `git lfs pull`을 먼저 실행해야 실제 데이터를 받을 수 있습니다.
- `build_zero_product_base_data.py`의 원재료 클러스터링 단계는 문장 임베딩 모델을 사용하므로 최초 실행 시 시간이 조금 걸릴 수 있습니다.
- Supabase 적재 또는 시각화 실행 전에는 앞 단계 산출물이 최신 상태로 존재하는지 확인하는 것이 좋습니다.
- `product.score`/`product.summary`는 grade와 ingredient 매칭 결과라는 서로 다른 두 기준으로 계산되어, 얼핏 모순돼 보이는 조합이 나올 수 있습니다. `load_all_to_supabase.py` 5단계가 이를 감지해 `grade_ingredient_conflicts.csv`로 남깁니다.
READMEEOF
echo "README.md 작성 완료"
wc -l /home/claude/Data/README.md