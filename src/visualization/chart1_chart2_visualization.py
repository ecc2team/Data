import os
import platform
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

if platform.system() == 'Darwin':
    plt.rc('font', family='AppleGothic')
elif platform.system() == 'Windows':
    plt.rc('font', family='Malgun Gothic')
else:
    plt.rc('font', family='NanumGothic')

plt.rcParams['axes.unicode_minus'] = False

current_path = Path(__file__).resolve() if '__file__' in locals() else Path.cwd().resolve()
BASE_DIR = current_path
while BASE_DIR != BASE_DIR.parent:
    if (BASE_DIR / "data").exists():
        break
    BASE_DIR = BASE_DIR.parent
else:
    BASE_DIR = Path.cwd().resolve().parent if (Path.cwd().name == 'src') else Path.cwd().resolve()

DATA_DIR = BASE_DIR / "data"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUTS_DIR = BASE_DIR / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

def draw_chart1_scatter():
    file_path = PROCESSED_DIR / "chart1_scatter_data.csv"
    if not file_path.exists():
        print(f"[경고] 파일이 없습니다: {file_path}. export_chart_data를 먼저 실행하세요.")
        return

    df = pd.read_csv(file_path)
    if df.empty:
        print("[경고] Chart 1 데이터가 비어 있습니다.")
        return
    
    plt.figure(figsize=(14, 7))
    
    sns.stripplot(
        data=df, 
        x="식품대분류", 
        y="에너지", 
        hue="고위험_이상치",
        palette={False: '#B0BEC5', True: '#E53935'},
        jitter=True, 
        alpha=0.7,
        size=6,
        hue_order=[True, False]
    )
    
    plt.title("위험/가짜 제로(3등급) 제품들의 카테고리별 칼로리 분포", fontsize=16, pad=15)
    plt.xlabel("식품대분류", fontsize=12)
    plt.ylabel("에너지 (kcal)", fontsize=12)
    plt.xticks(rotation=45, ha='right')
    
    plt.legend(title='고위험 이상치 여부', loc='upper right')
    plt.tight_layout()
    
    chart_path = OUTPUTS_DIR / 'chart1_scatter.png'
    plt.savefig(chart_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"차트 1 저장 완료: {chart_path}")

def draw_chart2_heatmap():
    file_path = PROCESSED_DIR / "chart2_sweetener_trend.csv"
    if not file_path.exists():
        print(f"[경고] 파일이 없습니다: {file_path}")
        return

    df = pd.read_csv(file_path)
    if df.empty:
        print("[경고] Chart 2 데이터가 비어 있습니다.")
        return
    
    pivot_df = df.pivot(index="식품대분류", columns="대체당", values="건수").fillna(0)
    
    pivot_df['총건수'] = pivot_df.sum(axis=1)
    pivot_df = pivot_df.sort_values('총건수', ascending=False).drop(columns=['총건수'])
    
    plt.figure(figsize=(12, 8))
    
    sns.heatmap(
        pivot_df, 
        annot=True, 
        fmt=".0f", 
        cmap="Blues", 
        linewidths=.5, 
        cbar_kws={'label': '사용 건수'}
    )
    
    plt.title("카테고리별 주요 대체당 사용 빈도 (히트맵)", fontsize=16, pad=15)
    plt.xlabel("대체당 종류", fontsize=12)
    plt.ylabel("식품대분류", fontsize=12)
    plt.xticks(rotation=45, ha='right')
    
    plt.tight_layout()
    chart_path = OUTPUTS_DIR / 'chart2_sweetener_heatmap.png'
    plt.savefig(chart_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"차트 2 저장 완료: {chart_path}")

if __name__ == "__main__":
    draw_chart1_scatter()
    draw_chart2_heatmap()
    print("=== 심화 시각화 차트 생성 완료 (outputs 폴더 확인) ===")