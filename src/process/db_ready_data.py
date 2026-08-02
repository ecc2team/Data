import pandas as pd
import numpy as np

# 1. 파일 경로 설정
input_file_path = r"C:\Users\mimit\zeropick\data\processed\integrated_final_validation.csv"
output_file_path = r"C:\Users\mimit\zeropick\data\processed\db_ready_data.csv"

# CSV 파일 읽기
try:
    df = pd.read_csv(input_file_path, encoding='utf-8-sig')
except UnicodeDecodeError:
    df = pd.read_csv(input_file_path, encoding='cp949')

# 컬럼명 띄어쓰기 찌꺼기 제거 (매핑 오류 방지)
df.columns = df.columns.str.strip()

# ==========================================
# [작업 1] 지수 표기법 복구 (2E+13 -> 20000000000000)
# ==========================================
def fix_scientific_notation(val):
    if pd.isna(val):
        return val
    
    val_str = str(val).strip()
    try:
        return str(int(float(val_str)))
    except ValueError:
        return val_str

ext_code_col = '품목제조보고번호' if '품목제조보고번호' in df.columns else '품목제조번호'
if ext_code_col in df.columns:
    df[ext_code_col] = df[ext_code_col].apply(fix_scientific_notation)

# ==========================================
# [작업 2] DB 스키마용 데이터 즉석 생성 (등급 & 첨가물)
# ==========================================
# 2-1. 룰기반_등급 -> 1, 2, 3 숫자로 매핑하여 'grade' 컬럼 생성
grade_mapping = {
    'Good': 1,
    '보통': 2,
    'Bad': 3
}

if '룰기반_등급' in df.columns:
    # 빈칸 등 예외가 있을 경우 기본값 3(Bad)으로 처리
    df['grade'] = df['룰기반_등급'].str.strip().map(grade_mapping).fillna(3).astype(int)
else:
    print("⚠️ '룰기반_등급' 컬럼이 원본에 없습니다! 확인이 필요합니다.")

# 2-2. 원재료명 텍스트를 분석하여 'warning_additive' (첨가물 트랩) 즉석 생성
if 'RAWMTRL_NM' in df.columns:
    # 카라멜색소, 캐러멜색소가 하나라도 포함되어 있으면 True, 아니면 False
    df['warning_additive'] = df['RAWMTRL_NM'].fillna('').str.contains('카라멜색소|캐러멜색소', regex=True)
    # DB 호환을 위해 'TRUE', 'FALSE' 텍스트로 확실히 고정
    df['warning_additive'] = df['warning_additive'].astype(str).str.upper()
else:
    print("⚠️ 'RAWMTRL_NM' (원재료명) 컬럼이 없어 첨가물 판별을 못했습니다. 모두 FALSE로 세팅합니다.")
    df['warning_additive'] = 'FALSE'

# ==========================================
# [작업 3] DB 스키마에 맞춰 필수 컬럼 추출 및 이름 변경
# ==========================================
# 필요한 컬럼만 선택 (방금 만든 grade, warning_additive 포함)
columns_to_keep = [
    ext_code_col,       # 외부 식별 코드
    '식품명',             # 상품명
    '식품대분류',         # 카테고리
    'grade',            # 방금 숫자로 변환한 등급!
    'warning_additive', # 방금 생성한 첨가물 여부!
    '에너지', 
    '당류', 
    '나트륨'
]

# 존재하는 컬럼만 필터링
final_columns = [col for col in columns_to_keep if col in df.columns]
df_final = df[final_columns].copy()

# DB 컬럼명으로 변경
rename_dict = {
    ext_code_col: 'external_code',
    '식품명': 'name',
    '식품대분류': 'category_name', 
    '에너지': 'calories',
    '당류': 'sugar',
    '나트륨': 'sodium'
}
df_final = df_final.rename(columns=rename_dict)

# 4. 전처리 완료된 데이터를 새 CSV로 저장
df_final.to_csv(output_file_path, index=False, encoding='utf-8-sig')

print(f"✅ DB 적재용 데이터 가공이 완료되었습니다!")
print(f"📂 저장된 파일: {output_file_path}")
print(f"📊 최종 포함된 컬럼: {list(df_final.columns)}")