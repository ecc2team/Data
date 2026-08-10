import pandas as pd

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
     "제조 과정에서 일부 우려 물질이 생성될 수 있어 과다 섭취를 권장하지 않습니다."]
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
df.to_csv("ingredient.csv", index=False, encoding="utf-8-sig")

print("✅ ingredient.csv 생성 완료!")