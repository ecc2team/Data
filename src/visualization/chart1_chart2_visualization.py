import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import platform

from path_config import CHARTS_DIR, ensure_dir

if platform.system() == 'Darwin':
    plt.rc('font', family='AppleGothic')
elif platform.system() == 'Windows':
    plt.rc('font', family='Malgun Gothic')
else:
    plt.rc('font', family='NanumGothic')

plt.rcParams['axes.unicode_minus'] = False

def draw_chart1_scatter():
    df = pd.read_csv(CHARTS_DIR / "chart1_scatter_data.csv")
    
    plt.figure(figsize=(14, 7))
    
    sns.stripplot(
        data=df, 
        x="식품대분류", 
        y="에너지", 
        hue="칼로리이상치",
        palette={False: '#B0BEC5', True: '#E53935'},
        jitter=True, 
        alpha=0.7,
        size=5
    )
    
    plt.title("무늬만 제로? 당류 0.5g 미만 제품의 카테고리별 칼로리 분포", fontsize=16, pad=15)
    plt.xlabel("식품대분류", fontsize=12)
    plt.ylabel("에너지 (kcal)", fontsize=12)
    plt.xticks(rotation=45, ha='right')
    
    plt.legend(title='칼로리 상위 10% (이상치)', loc='upper right')
    
    plt.tight_layout()
    ensure_dir(CHARTS_DIR)
    plt.savefig(CHARTS_DIR / 'chart1_scatter.png', dpi=300, bbox_inches='tight')

def draw_chart2_heatmap():
    df = pd.read_csv(CHARTS_DIR / "chart2_sweetener_trend.csv")
    
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
    
    plt.title("카테고리별 대체당 사용 빈도", fontsize=16, pad=15)
    plt.xlabel("대체당", fontsize=12)
    plt.ylabel("식품대분류", fontsize=12)
    plt.xticks(rotation=45, ha='right')
    
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / 'chart2_sweetener_heatmap.png', dpi=300, bbox_inches='tight')

if __name__ == "__main__":
    draw_chart1_scatter()
    draw_chart2_heatmap()