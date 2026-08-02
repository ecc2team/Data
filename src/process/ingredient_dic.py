import pandas as pd

# 최종 기획안이 모두 반영된 완전판 마스터 데이터
data = [
    # 🟢 1등급 (PREMIUM) : 혈당 0, 칼로리 0, 천연 유래 안전 성분 (프리미엄 뱃지)
    ["STEVIA", "스테비아", "SWEETENER", "PREMIUM", "자연 유래 감미료", "안전성이 가장 우수하고 당도가 높으나 가격이 비쌉니다. 칼로리와 혈당에 영향을 주지 않습니다."],
    ["ERYTHRITOL", "에리스리톨", "SWEETENER", "PREMIUM", "0kcal 천연 당알코올", "당알코올 중 예외적으로 0kcal이며, 혈당을 올리지 않아 당뇨 환자에게 유용합니다."],
    ["ALLULOSE", "알룰로스", "SWEETENER", "PREMIUM", "흡수가 매우 느린 0칼로리 대체당", "설탕의 1/10 칼로리입니다. 단, 하루 허용량이 다소 낮아 과다 섭취 시 설사를 유발할 수 있습니다."],
    ["MONK_FRUIT", "나한과", "SWEETENER", "PREMIUM", "과일 추출 천연 감미료", "나한과 열매에서 추출한 천연 감미료로 비싸지만 안전하고 좋습니다."],

    # ⚪ 2등급 (GENERAL) : 혈당은 없으나 합성 감미료이거나 소량 섭취 권장 (일반 노출)
    ["SUCRALOSE", "수크랄로스", "SWEETENER", "GENERAL", "안심하고 섭취 가능한 인공감미료", "가격이 저렴하고 당도가 매우 높으며 안심하고 섭취할 수 있습니다."],
    ["ACESULFAME_K", "아세설팜칼륨", "SWEETENER", "GENERAL", "안전한 합성 감미료", "수크랄로스와 흔하게 조합되며 안심하고 섭취 가능합니다."],
    ["ASPARTAME", "아스파탐", "SWEETENER", "GENERAL", "논란이 있는 인공 감미료", "1일 허용량 내에서는 안전하나, 체내에서 소량의 메탄올을 생성하여 잠재적 위험성 논란이 있습니다."],
    ["XYLITOL", "자일리톨", "SWEETENER", "GENERAL", "주의가 필요한 당알코올", "혈당 흡수를 늦췄으나 칼로리가 설탕의 절반 이상 존재하므로 과다 섭취는 금물입니다."],
    ["SORBITOL", "소르비톨", "SWEETENER", "GENERAL", "주의가 필요한 당알코올", "칼로리가 존재하며, 다량 섭취 시 배탈이나 설사를 유발할 수 있습니다."],

    # 🔴 3등급 (WARNING) : 혈당을 올리거나 배탈 위험이 큰 '가짜 제로' (주의 딱지 및 후순위)
    ["MALTITOL", "말티톨", "SWEETENER", "WARNING", "혈당을 올리는 가짜 제로", "당알코올 중 혈당 지수(GI)가 35~52로 높아 설탕과 유사하게 살이 찌고 혈당을 올립니다."],
    ["GLUCOSE", "포도당", "SWEETENER", "WARNING", "인슐린 분비 유발 최악의 성분", "혈당 지수(GI) 100으로 설탕보다 인슐린 분비를 강하게 유발하여 혈당 관리에 최악입니다."],
    ["MALTODEXTRIN", "말토덱스트린", "ADDITIVE", "WARNING", "혈당을 급격히 올리는 전분", "혈당 지수(GI)가 85~110으로 매우 높아 제품의 식감을 살리지만 혈당을 빠르게 올립니다."],
    ["TAPIOCA_STARCH", "타피오카전분", "ADDITIVE", "WARNING", "혈당 지수(GI)가 높은 전분", "혈당 지수(GI)가 85로 매우 높은 편이라 혈당을 빠르게 올립니다."],
    ["FRUCTOSE", "과당", "SWEETENER", "WARNING", "내장 지방 증가 주원인", "간에서 대사되기 때문에 과다 섭취 시 내장 지방 증가의 주원인이 됩니다."],
    ["AGAVE_SYRUP", "아가베시럽", "SWEETENER", "WARNING", "과당이 주성분인 시럽", "몸에 좋은 천연 시럽처럼 보이지만 실제로는 과당이 주성분이라 내장 지방을 늘립니다."],
    ["CARAMEL_COLOR", "카라멜색소", "ADDITIVE", "WARNING", "당독소를 생성하는 최악의 색소", "제조 과정에서 당독소가 많이 생성되어 세포를 파괴하고 노화를 촉진하므로 피해야 합니다."]
]

columns = ["code", "name", "ingredient_type", "risk_level", "summary", "description"]

df = pd.DataFrame(data, columns=columns)
df.to_csv("ingredient.csv", index=False, encoding="utf-8-sig")

print("✅ 최종 기획안이 모두 반영된 ingredient.csv 파일 생성 완료!")