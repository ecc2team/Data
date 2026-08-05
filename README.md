# Zeropick

Zeropick은 제로/무설탕 제품의 실제 안전성과 마케팅 표기 간 차이를 분석하기 위한 데이터 파이프라인 프로젝트입니다. 원본 데이터 수집부터 전처리, 등급 분류, AI 검증, DB 적재, 시각화까지 하나의 흐름으로 처리할 수 있도록 구성되어 있습니다.

## 1. 프로젝트 개요

이 프로젝트는 다음 순서로 동작합니다.

1. 원본 데이터 수집
2. 제로 제품 기준 데이터 구축
3. 룰 기반 등급 분류
4. Zero-shot 기반 AI 검증
5. DB 적재용 정제 데이터 생성
6. 시각화 결과물 생성

---

## 2. 폴더 구조

- data/
  - raw/: 원본 데이터 CSV
    - food_nutrition_raw.csv
    - prdlst_rawmtrl_raw.csv
  - interim/: 중간 가공 데이터
  - processed/: 전처리 및 정제 결과 데이터
- outputs/
  - charts/: 생성된 차트 이미지 및 차트용 데이터
- src/
  - collect/: 데이터 수집 스크립트
  - process/: 전처리, 등급 분류, 매핑 생성 스크립트
  - model/: 클러스터링 및 Zero-shot 모델 스크립트
  - visualization/: 시각화용 스크립트
  - loader/: 로컬 DB 적재용 스크립트
  - config.py: 프로젝트 공통 경로 및 DB 설정

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

프로젝트 루트에 .env 파일을 두면 DB 접속 정보를 덮어쓸 수 있습니다.

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=zeropick
DB_USER=zeropick
DB_PASSWORD=zeropick
```

`src/config.py`에서 경로와 DB 기본값을 공통 관리하므로, 스크립트 실행 위치와 무관하게 경로를 재사용할 수 있습니다.

---

## 4. 전체 파이프라인 실행 순서

### 4.1 원본 데이터 수집

```bash
python src/collect/collect_prdlst_rawmtrl.py
python src/collect/collect_food_nutrition.py
```

수집 결과는 각각 `data/raw/` 아래에 저장됩니다.

### 4.2 제로 제품 기준 데이터 생성

```bash
python src/process/merge_whitelist_v4.py
```

이 단계에서 다음 파일이 생성됩니다.

- `data/processed/zeropick_base_data_v4.csv`
- `data/processed/ingredient_clusters_result.csv`
- `data/processed/zeropick_blacklist_candidates.csv`

### 4.3 룰 기반 등급 분류 및 AI 검증

```bash
python src/process/zeropick_final_graded.py
```

이 단계에서 `data/processed/integrated_final_validation.csv`가 생성됩니다.

### 4.4 DB 적재용 데이터 생성

```bash
python src/process/db_ready_data.py
python src/process/final_ingredient.py
```

생성되는 주요 파일:

- `data/processed/db_ready_data.csv`
- `data/processed/product_ingredient_mapping.csv`

### 4.5 로컬 DB 적재

로컬 PostgreSQL이 준비되어 있다면 다음으로 적재합니다.

```bash
python src/loader/load_all.py
```

이 스크립트는 다음 두 파일을 순차적으로 적재합니다.

- `data/processed/db_ready_data.csv`
- `data/processed/integrated_final_validation.csv`

### 4.6 시각화 결과물 생성

```bash
python src/visualization/export_chart_data.py
python src/visualization/chart1_chart2_visualization.py
```

생성되는 결과물:

- `data/processed/chart1_scatter_data.csv`
- `data/processed/chart2_sweetener_trend.csv`
- `outputs/charts/`

---

## 5. 주요 산출물

| 단계 | 주요 산출물 |
| --- | --- |
| 데이터 수집 | `data/raw/*.csv` |
| 기본 데이터 구축 | `data/processed/zeropick_base_data_v4.csv` |
| 등급/AI 검증 | `outputs/integrated_final_validation.csv` |
| DB 적재용 데이터 | `data/processed/db_ready_data.csv` |
| 시각화 | `outputs/charts/*.png` |

---

## 6. 참고 사항

- 경로 및 DB 설정은 `src/config.py`에서 관리합니다.
- 대용량 데이터 파일은 보통 Git 추적 대상에서 제외되므로, 로컬 환경에서 생성된 결과물을 사용합니다.
- 일부 모델 스크립트는 문장 임베딩 모델을 사용하므로 초기 실행 시 시간이 조금 걸릴 수 있습니다.
- 시각화 또는 DB 적재는 실행 전 데이터가 정상적으로 생성되었는지 확인하는 것이 좋습니다.
