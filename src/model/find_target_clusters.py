import pandas as pd

from src.config import OUTPUTS_DIR

def find_target_clusters(file_path: str, keywords: list):
    try:
        df = pd.read_csv(file_path)
    except FileNotFoundError:
        print(f"오류: {file_path} 파일을 찾을 수 없습니다.")
        return

    print(f"🔍 다음 키워드가 포함된 클러스터 그룹을 검색합니다:\n{keywords}\n")
    print("-" * 50)

                                  
    target_cluster_ids = set()

                                    
    for keyword in keywords:
        matched = df[df["원재료명"].str.contains(keyword, na=False)]
        target_cluster_ids.update(matched["Cluster_ID"].tolist())

    if not target_cluster_ids:
        print("일치하는 원재료를 찾을 수 없습니다.")
        return

                                      
    print(f"✅ 총 {len(target_cluster_ids)}개의 관련 클러스터 그룹을 찾았습니다.\n")

    for cluster_id in sorted(target_cluster_ids):
                                      
        cluster_items = df[df["Cluster_ID"] == cluster_id]["원재료명"].tolist()
        
                                     
        matched_keywords = [kw for kw in keywords if any(kw in item for item in cluster_items)]
        
        print(f"🎯 [Cluster ID: {cluster_id}] (매칭 키워드: {', '.join(matched_keywords)})")
        print(f" -> 묶인 성분들: {', '.join(cluster_items)}\n")

if __name__ == "__main__":
                         
    INPUT_CSV = OUTPUTS_DIR / "ingredient_clusters_result.csv"
    
                                    
    TARGET_KEYWORDS = [
                                    
        "스테비아", "에리스리톨", "알룰로", "나한과",
        
                                         
        "수크랄로스", "아세설팜", "아스파탐", "자일리톨", "소비톨", "소르비톨", 
        
                                               
        "말티톨", "포도당", "말토덱스트린", "과당", "아가베", "설탕", "물엿",
        
                           
        "프락토올리고당", "이소말토올리고당", "폴리덱스트로스",
        
                         
        "카라멜" 
    ]
    
    find_target_clusters(INPUT_CSV, TARGET_KEYWORDS)