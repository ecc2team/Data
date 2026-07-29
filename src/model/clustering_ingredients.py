import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering

from path_config import OUTPUTS_DIR, ensure_dir

def run_clustering(input_file: str, output_file: str):
    print("1. 기초 데이터 로드 및 원재료 분리 중...")
    try:
        df = pd.read_csv(input_file)
    except FileNotFoundError:
        print(f"오류: {input_file} 파일을 찾을 수 없습니다.")
        return

                                            
    raw_materials_set = set()
    
                 
    for items in df["RAWMTRL_NM"].dropna():
                           
        ingredients = [x.strip() for x in items.split(",")]
        raw_materials_set.update(ingredients)
        
                       
    unique_ingredients = [x for x in list(raw_materials_set) if x]
    print(f" -> 추출된 고유 원재료 개수: {len(unique_ingredients)}개\n")

    print("2. 한국어 특화 임베딩 모델 로드 중 (CPU 환경, 1~2분 소요 가능)...")
                                  
    model = SentenceTransformer('jhgan/ko-sroberta-multitask')

    print("3. 원재료 텍스트 임베딩 추출 중...")
    embeddings = model.encode(unique_ingredients)

    print("\n4. 응집형 클러스터링(Agglomerative Clustering) 수행 중...")
                                     
    clustering_model = AgglomerativeClustering(
        n_clusters=None, 
        distance_threshold=0.25, 
        metric='cosine', 
        linkage='average'
    )
    cluster_labels = clustering_model.fit_predict(embeddings)

                             
    result_df = pd.DataFrame({
        "원재료명": unique_ingredients,
        "Cluster_ID": cluster_labels
    })

                                
    result_df = result_df.sort_values(by=["Cluster_ID", "원재료명"])
    
    ensure_dir(OUTPUTS_DIR)
    output_path = OUTPUTS_DIR / output_file
    result_df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n✅ 클러스터링 완료! 결과가 '{output_file}'에 저장되었습니다.")
    
                      
    print("\n[클러스터링 결과 미리보기 - 같은 ID끼리 묶임]")
    print(result_df.head(15).to_string(index=False))

if __name__ == "__main__":
                            
    INPUT_CSV = OUTPUTS_DIR / "zeropick_base_data_v4.csv" 
    OUTPUT_CSV = "ingredient_clusters_result.csv"
    
    run_clustering(INPUT_CSV, OUTPUT_CSV)