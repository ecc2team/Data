import os
import sys

import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from src.config import DATA_DIR, ensure_dir

# 최종 기획안 반영 ingredient 마스터 데이터
data = [
    # 🟢 PREMIUM
    ["STEVIA", "스테비아", "SWEETENER", "PREMIUM",
     "자연 유래 감미료",
     "안전성이 가장 우수하고 당도가 높으나 가격이 비쌉니다. 칼로리와 혈당에 영향을 주지 않습니다."],

    ["ERYTHRITOL", "에리스리톨", "SUGAR_ALCOHOL", "PREMIUM",
     "0kcal 천연 당알코올",
     "당알코올 중 예외적으로 0kcal이며, 혈당을 올리지 않아 당뇨 환자에게 유용합니다."],

    ["ALLULOSE", "알룰로스", "SWEETENER", "PREMIUM",
     "흡수가 매우 느린 0칼로리 대체당",
     "설탕의 약 1/10 수준의 칼로리를 가지며 혈당에 거의 영향을 주지 않습니다. 과다 섭취 시 설사를 유발할 수 있습니다."],

    ["MONK_FRUIT", "나한과", "SWEETENER", "PREMIUM",
     "과일 추출 천연 감미료",
     "나한과 열매에서 추출한 천연 감미료로 혈당에 영향을 거의 주지 않습니다."],

    # ⚪ GENERAL
    ["SUCRALOSE", "수크랄로스", "SWEETENER", "GENERAL",
     "안심하고 섭취 가능한 인공감미료",
     "당도가 매우 높으며 여러 식품에 널리 사용됩니다."],

    ["ACESULFAME_K", "아세설팜칼륨", "SWEETENER", "GENERAL",
     "안전한 합성 감미료",
     "수크랄로스와 함께 자주 사용되는 감미료입니다."],

    ["ASPARTAME", "아스파탐", "SWEETENER", "GENERAL",
     "논란이 있는 인공 감미료",
     "허용 섭취량 내에서는 안전하다고 평가되지만 일부 논란이 있는 감미료입니다."],

    ["XYLITOL", "자일리톨", "SUGAR_ALCOHOL", "GENERAL",
     "주의가 필요한 당알코올",
     "설탕보다 혈당 영향은 적지만 과다 섭취 시 복통이나 설사를 유발할 수 있습니다."],

    ["SORBITOL", "소르비톨", "SUGAR_ALCOHOL", "GENERAL",
     "주의가 필요한 당알코올",
     "당알코올의 일종으로 과다 섭취 시 복통이나 설사를 유발할 수 있습니다."],

    # 🔴 WARNING
    ["MALTITOL", "말티톨", "SUGAR_ALCOHOL", "WARNING",
     "혈당을 올리는 당알코올",
     "당알코올이지만 혈당지수(GI)가 상대적으로 높아 혈당 관리 시 주의가 필요합니다."],

    ["GLUCOSE", "포도당", "SUGAR", "WARNING",
     "혈당을 빠르게 올리는 당류",
     "혈당지수(GI)가 100으로 매우 높아 혈당을 빠르게 상승시킵니다."],

    ["FRUCTOSE", "과당", "SUGAR", "WARNING",
     "과다 섭취 시 주의가 필요한 당류",
     "과다 섭취 시 내장지방 증가 및 대사 건강에 영향을 줄 수 있습니다."],

    ["AGAVE_SYRUP", "아가베시럽", "SUGAR", "WARNING",
     "과당 비율이 높은 시럽",
     "천연 시럽이지만 과당 함량이 높아 과다 섭취는 권장되지 않습니다."],

    ["MALTODEXTRIN", "말토덱스트린", "STARCH", "WARNING",
     "혈당을 빠르게 올리는 전분",
     "혈당지수가 매우 높은 전분으로 혈당을 빠르게 상승시킬 수 있습니다."],

    ["TAPIOCA_STARCH", "타피오카전분", "STARCH", "WARNING",
     "혈당지수가 높은 전분",
     "혈당지수가 높은 전분 원료입니다."],

    ["CARAMEL_COLOR", "카라멜색소", "COLOR", "WARNING",
     "주의가 필요한 착색료",
     "제조 과정에서 일부 우려 물질이 생성될 수 있어 과다 섭취를 권장하지 않습니다."],

    # 🟡 ALLERGEN (알레르기 유발물질 - product.grade/score 계산에는 포함되지 않음.
    # 사용자별 개인화 필터(user_allergy)용으로만 사용. 목록은 zeropick_base_data_v4.csv
    # 원재료(RAWMTRL_NM) 실측 매칭 건수 기준 상위 8종만 선정 (음료/과자·빵·떡/초콜릿
    # 카테고리 데이터셋이라 법정 21종 중 새우/게/고등어/육류/메밀/잣 등은 매칭이
    # 거의 없어 제외함).
    ["MILK", "우유", "ALLERGEN", "WARNING",
     "우유 알레르기 유발 성분",
     "우유 및 우유 단백질(버터, 치즈, 유크림, 탈지분유, 유청단백 등)을 원료로 사용했습니다. 우유 알레르기가 있다면 섭취에 주의하세요."],

    ["EGG", "계란", "ALLERGEN", "WARNING",
     "계란 알레르기 유발 성분",
     "계란 또는 난백/난황을 원료로 사용했습니다. 계란 알레르기가 있다면 섭취에 주의하세요."],

    ["WHEAT", "밀", "ALLERGEN", "WARNING",
     "밀 알레르기 유발 성분",
     "밀가루 및 밀 글루텐을 원료로 사용했습니다. 밀 알레르기가 있다면 섭취에 주의하세요."],

    ["SOYBEAN", "대두", "ALLERGEN", "WARNING",
     "대두 알레르기 유발 성분",
     "대두, 대두유, 대두단백, 대두레시틴 등을 원료로 사용했습니다. 대두 알레르기가 있다면 섭취에 주의하세요."],

    ["PEANUT", "땅콩", "ALLERGEN", "WARNING",
     "땅콩 알레르기 유발 성분",
     "땅콩 또는 땅콩가공품을 원료로 사용했습니다. 땅콩 알레르기가 있다면 섭취에 주의하세요."],

    ["ALMOND", "아몬드", "ALLERGEN", "WARNING",
     "아몬드 알레르기 유발 성분",
     "아몬드 또는 아몬드가공품을 원료로 사용했습니다. 견과류 알레르기가 있다면 섭취에 주의하세요."],

    ["WALNUT", "호두", "ALLERGEN", "WARNING",
     "호두 알레르기 유발 성분",
     "호두 또는 호두가공품을 원료로 사용했습니다. 견과류 알레르기가 있다면 섭취에 주의하세요."],

    ["PEACH", "복숭아", "ALLERGEN", "WARNING",
     "복숭아 알레르기 유발 성분",
     "복숭아 또는 복숭아향을 원료로 사용했습니다. 복숭아 알레르기가 있다면 섭취에 주의하세요."],
]

columns = [
    "code",
    "name",
    "ingredient_type",
    "risk_level",
    "summary",
    "description"
]

df = pd.DataFrame(data, columns=columns)

# data/final/ingredient.csv로 저장 (build_zero_product_base_data.py의
# INGREDIENT_PATH = FINAL_DATA_DIR / "ingredient.csv" 와 동일 경로).
# 예전엔 cwd에 그냥 "ingredient.csv"로 저장해서 어디서 실행하느냐에 따라
# 실제 참조 경로와 어긋날 수 있었음.
FINAL_DATA_DIR = DATA_DIR / "final"
ensure_dir(FINAL_DATA_DIR)
output_path = FINAL_DATA_DIR / "ingredient.csv"
df.to_csv(output_path, index=False, encoding="utf-8-sig")

print(f"✅ ingredient.csv 생성 완료! ({output_path}, {len(df)}행)")