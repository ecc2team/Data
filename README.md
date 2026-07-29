# Zeropick Project

## 🗂️ 프로젝트 구조 (Project Structure)
프로젝트는 데이터, 소스 코드, 최종 결과물을 명확히 분리하여 관리합니다.

- `data/`: 모든 데이터 파일이 저장되는 공간 (Git 업로드 제외)
  - `raw/`: 식약처/공공데이터 등 최초 수집 원본 CSV (`food_nutrition_raw.csv` 등)
  - `interim/`: 1차 가공 및 병합된 중간 데이터 (`zeropick_base_data_v4.csv` 등)
  - `processed/`: DB 적재 직전의 최종 정제 데이터 (`final_grade_data.csv`, `product_ingredient_mapping.csv` 등)
- `src/`: 파이썬 소스 코드 전용 폴더
  - `collect/`: 공공 API 및 원본 데이터 수집 스크립트
  - `process/`: 데이터 전처리, 병합, 매핑 추출 스크립트
  - `model/`: AI(Zero-shot) 검증 및 클러스터링 스크립트
  - `visualization/`: 시각화 데이터 및 차트 생성 스크립트
  - `config.py`: 전체 프로젝트의 경로(Path)를 관리하는 단일 설정 파일
- `outputs/`: 생성된 최종 결과물 보관
  - `charts/`: 시각화 차트 이미지(.png) 및 차트용 추출 데이터(.csv)

---

## 🚀 실행 순서 (Execution Flow)
작업 파이프라인은 `src/` 내의 모듈을 다음 순서대로 실행하여 진행합니다.

**1. 데이터 수집**
   - `src/collect/collect_prdlst_rawmtrl.py` (식품안전나라 원재료 수집)
   - `src/collect/collect_food_nutrition.py` (영양성분 수집)

**2. 전처리 및 병합 (기초 데이터 구축)**
   - `src/process/merge_whitelist_v4.py` (제로슈거/칼로리 화이트리스트 병합)
   - `src/process/zeropick_final_graded.py` (룰 기반 최종 등급 분류)
   - `src/process/final_ingredient.py` (RDB 적재용 대체당 매핑 데이터 추출)

**3. 모델링 및 AI 검증**
   - `src/model/zero_shot.py` (Zero-shot 기반 유해성 판정)
   - `src/model/clustering_ingredients.py` (원재료명 텍스트 클러스터링)

**4. 시각화 (데이터 추출 및 차트 생성)**
   - `src/visualization/export_chart_data.py` (차트용 데이터 세팅)
   - `src/visualization/chart1_chart2_visualization.py` (최종 차트 렌더링 및 저장)

---

## 📌 참고 사항 (Notes)
- **경로 설정:** 모든 파일 읽기/쓰기 경로는 `src/config.py`에 정의된 상대 경로를 따르므로, 스크립트 위치가 변경되어도 에러가 발생하지 않습니다.
- **가상 환경:** `.venv` 폴더와 대용량 `.csv` 파일들은 `.gitignore`에 의해 형상관리(Git)에서 제외됩니다.
- **환경 복원:** 코드를 클론(Clone)한 후, `pip install -r requirements.txt`를 실행하여 패키지 환경을 복원할 수 있습니다.
- 모든 스크립트의 산출물은 프로젝트 루트가 아닌 `data/` 또는 `outputs/` 디렉터리에 안전하게 분리되어 저장됩니다.