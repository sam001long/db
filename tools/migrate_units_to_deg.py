# tools/migrate_units_to_deg.py
import math
from pathlib import Path
import pandas as pd

DB_DIR = Path("db")
CSV = DB_DIR / "measurements.csv"
PARQ = DB_DIR / "measurements.parquet"

def main():
    if not CSV.exists():
        print(f"找不到 {CSV}，先跑 ingest 產生資料吧。")
        return

    df = pd.read_csv(CSV)
    if df.empty:
        print("CSV 是空的，略過。")
        return

    # 只針對角度（metric == angle）且 unit==rad 的列做轉換
    has_metric = "metric" in df.columns
    has_unit = "unit" in df.columns
    has_value = "value" in df.columns
    if not (has_metric and has_unit and has_value):
        print("CSV 欄位缺少 metric/unit/value，無法轉換。")
        return

    mask = df["metric"].astype(str).str.lower().eq("angle") & df["unit"].astype(str).str.lower().eq("rad")
    if mask.any():
        df.loc[mask, "value"] = df.loc[mask, "value"].astype(float) * 180.0 / math.pi
        df.loc[mask, "unit"] = "deg"
        changed = mask.sum()
        print(f"已把 {changed} 列從 rad 轉為 deg")
    else:
        print("沒有需要轉換的列（看起來已經都是 deg）。")

    # 寫回 CSV 與 Parquet（需要 pyarrow）
    df.to_csv(CSV, index=False)
    try:
        df.to_parquet(PARQ, index=False)
        print(f"已輸出：{CSV} 與 {PARQ}")
    except Exception as e:
        print(f"寫 Parquet 失敗（可能缺 pyarrow）：{e}")

if __name__ == "__main__":
    main()
