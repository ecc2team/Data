import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

scripts = [
    "load_to_local_db.py",
    "product_ingredient_loader.py",
]

for script in scripts:
    print(f"\n===== {script} =====")

    subprocess.run(
        [sys.executable, str(BASE_DIR / script)],
        check=True,
    )

print("\n🎉 모든 데이터 적재 완료!")