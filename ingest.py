import os, io, json, hashlib, yaml
from pathlib import Path
from typing import List, Dict, Any
import pandas as pd

# 路徑設定
UP = Path("uploads")
DB_DIR = Path("db")
DB_DIR.mkdir(exist_ok=True)
OUT_CSV = DB_DIR / "measurements.csv"
OUT_PARQUET = DB_DIR / "measurements.parquet"
HASH_LOG = DB_DIR / "_ingested_hashes.txt"  # 已處理過的檔案內容 hash 記錄

# 規則
CFG = yaml.safe_load(open("ingest_config.yaml", "r", encoding="utf-8"))

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def read_any_bytes(filename: str, data: bytes) -> List[pd.DataFrame]:
    ext = Path(filename).suffix.lower()
    bio = io.BytesIO(data)
    if ext in [".csv", ".tsv"]:
        sep = "," if ext == ".csv" else "\t"
        return [pd.read_csv(bio, sep=sep)]
    if ext in [".xlsx", ".xls"]:
        xls = pd.ExcelFile(bio)
        return [xls.parse(sheet) for sheet in xls.sheet_names]
    if ext == ".json":
        obj = json.loads(data.decode("utf-8"))
        if isinstance(obj, list):
            return [pd.DataFrame(obj)]
        if isinstance(obj, dict) and "data" in obj:
            return [pd.DataFrame(obj["data"])]
        return [pd.json_normalize(obj)]
    raise ValueError(f"不支援的格式: {ext}")

def detect_provider(df: pd.DataFrame, cfg) -> str | None:
    headers = set(map(str, df.columns))
    for name, rule in cfg.get("providers", {}).items():
        keys = set(map(str, rule.get("detect_any_header", [])))
        if headers & keys:
            return name
    return None

def wide_to_long(df: pd.DataFrame, rule: Dict[str, Any]) -> pd.DataFrame:
    id_vars = rule["wide_to_long"]["id_vars"]
    var_name = rule["wide_to_long"]["var_name"]
    value_name = rule["wide_to_long"]["value_name"]
    long_df = pd.melt(df, id_vars=id_vars, var_name=var_name, value_name=value_name)
    if "parse_feature" in rule:
        pat = rule["parse_feature"]["pattern"]
        extracted = long_df[var_name].str.extract(pat, expand=True)
        long_df = pd.concat([long_df, extracted], axis=1)
        for k, v in (rule["parse_feature"].get("set") or {}).items():
            long_df[k] = v
    return long_df

def normalize_df(df: pd.DataFrame, provider: str, cfg) -> pd.DataFrame:
    rule = cfg["providers"][provider]
    if "wide_to_long" in rule:
        df = wide_to_long(df, rule)
    df = df.rename(columns=rule.get("rename", {}))
    for k, v in (rule.get("set") or {}).items():
        df[k] = v
    if "derived" in rule:
        for new_col, expr in rule["derived"].items():
            safe_locals = {c: df[c] for c in df.columns if c in expr}
            df[new_col] = eval(expr, {"__builtins__": {}}, safe_locals)

    # 補上 canonical 預設值
    for k, v in (CFG["canonical"].get("defaults") or {}).items():
        if k not in df.columns:
            df[k] = v

    # 檢查必填
    need = CFG["canonical"]["required"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"缺少必要欄位: {missing}")

    keep = list(set(
        need + list((CFG["canonical"].get("defaults") or {}).keys())
        + ["session_id", "subject_id", "activity", "unit", "metric"]
    ))
    keep = [c for c in keep if c in df.columns]
    return df[keep].copy()

def load_hashes() -> set[str]:
    if not HASH_LOG.exists():
        return set()
    return set(x.strip() for x in HASH_LOG.read_text().splitlines() if x.strip())

def save_hash(h: str):
    # 確保檔案存在
    if not HASH_LOG.exists():
        HASH_LOG.touch()
    with open(HASH_LOG, "a", encoding="utf-8") as f:
        f.write(h + "\n")

def main():
    seen = load_hashes()
    outputs = []

    for p in sorted(UP.glob("*")):
        if p.is_dir():
            continue
        data = p.read_bytes()
        h = sha256_bytes(data)
        if h in seen:
            print(f"[skip] {p.name} duplicate")
            continue
        try:
            dfs = read_any_bytes(p.name, data)
            provider_used = None
            for df in dfs:
                provider = detect_provider(df, CFG)
                if provider is None:
                    raise ValueError("無法偵測提供者；請在 ingest_config.yaml 增加規則")
                provider_used = provider
                norm = normalize_df(df, provider, CFG)

                # ---- 單位統一：只針對角度（metric == 'angle'）的 rad → deg ----
                if "metric" in norm.columns and "unit" in norm.columns:
                    is_angle = norm["metric"].astype(str).str.lower().eq("angle")
                    is_rad = norm["unit"].astype(str).str.lower().eq("rad")
                    mask = is_angle & is_rad
                    if mask.any():
                        norm.loc[mask, "value"] = norm.loc[mask, "value"].astype(float) * 180.0 / 3.141592653589793
                        norm.loc[mask, "unit"] = "deg"

                # 記錄來源（更穩的去重與追蹤）
                norm["source_hash"] = h
                norm["source_file"] = p.name

                outputs.append(norm)

            save_hash(h)
            print(f"[ok] {p.name} ({provider_used})")
        except Exception as e:
            print(f"[fail] {p.name}: {e}")

    # 若沒有新資料：若有舊 CSV 仍補一份 Parquet
    if not outputs:
        if OUT_CSV.exists():
            existing = pd.read_csv(OUT_CSV)
            try:
                existing.to_parquet(OUT_PARQUET, index=False)
                print(f"沒有新資料；已由現有 CSV 生成 Parquet：{OUT_PARQUET}")
            except Exception as e:
                print(f"寫 Parquet 失敗（可能缺套件）：{e}")
        else:
            print("沒有新的資料可處理。")
        return

    # 整併、與舊資料合併
    out = pd.concat(outputs, ignore_index=True)
    if OUT_CSV.exists():
        existing = pd.read_csv(OUT_CSV)
        out = pd.concat([existing, out], ignore_index=True)

    # 更穩的去重鍵（含來源雜湊；若未來加 session_id 也可一併放）
    dedup_keys = [c for c in ["timestamp", "joint", "metric", "value", "source_hash"] if c in out.columns]
    out = out.drop_duplicates(subset=dedup_keys, keep="last")

    # 同時輸出 CSV 與 Parquet
    out.to_csv(OUT_CSV, index=False)
    try:
        out.to_parquet(OUT_PARQUET, index=False)
    except Exception as e:
        print(f"寫 Parquet 失敗（可能缺套件）：{e}")

    print(f"✅ 累積輸出：{OUT_CSV}（{len(out)} 列）")
    if OUT_PARQUET.exists():
        print(f"✅ Parquet：{OUT_PARQUET}")

if __name__ == "__main__":
    main()
