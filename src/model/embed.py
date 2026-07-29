import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_similarity

from path_config import OUTPUTS_DIR, ensure_dir

def run_embedding_clustering(unclassified_ingredients: list):
    """
    판정불가/미검출 원재료 리스트를 입력받아 임베딩 기반으로 자동 클러스터링합니다.
    """
    print("1. Hugging Face SRoBERTa 모델 로드 중...")
                                                              
    model = SentenceTransformer('jhgan/ko-sroberta-multitask')
    
    print(f"2. {len(unclassified_ingredients)}개 원재료 텍스트 벡터화(임베딩) 진행 중...")
    embeddings = model.encode(unclassified_ingredients)
    
    print("3. 유사도 기반 자동 클러스터링 진행 중...")
                                                               
                                                               
    cluster_model = AgglomerativeClustering(
        n_clusters=None, 
        distance_threshold=0.25, 
        metric='cosine', 
        linkage='average'
    )
    
    cluster_labels = cluster_model.fit_predict(embeddings)
    
                           
    result_df = pd.DataFrame({
        "원재료명": unclassified_ingredients,
        "Cluster_ID": cluster_labels
    })
    
                                  
    result_df = result_df.sort_values(by=["Cluster_ID", "원재료명"]).reset_index(drop=True)
    
    return result_df, embeddings

                                            
             
                                            
if __name__ == "__main__":
                                   
    sample_unknowns = [
        "알룰로스", "알룰로오스", "액상알룰로스", 
        "효소처리스테비아", "스테비올배당체", "스테비아추출물",
        "수크랄로스", "수크랄로오스", "액상수크랄로스",
        "에리스리톨", "에리스리톨분말", 
        "천연향료", "구연산", "정제수", "정제염", "L-글루탐산나트륨"
    ]
    
    clustered_df, vectors = run_embedding_clustering(sample_unknowns)
    
    print("\n[임베딩 클러스터링 결과 - 같은 Cluster ID끼리 묶임]")
    print(clustered_df)
    
                                               
    ensure_dir(OUTPUTS_DIR)
    clustered_df.to_csv(OUTPUTS_DIR / "clustering_after_result.csv", index=False, encoding="utf-8-sig")
    print(f"\n{OUTPUTS_DIR / 'clustering_after_result.csv'}로 저장 완료!")