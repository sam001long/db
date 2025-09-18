# tools/csv_to_motion_json.py
import sys, json, math, os, pandas as pd, pathlib, datetime as dt

# 將 canonical 的 joint 名稱 → 你的 glTF 骨頭名稱（先放示例；請改成你的實際骨頭名）
BONE_MAP = {
  "hip": "Hips",
  "knee": "RightUpLeg",     # ← 改成你的
  "ankle": "RightLeg",      # ← 改成你的
  "shoulder": "RightShoulder",
  "elbow": "RightArm",
  "wrist": "RightForeArm",
}

def eulerZdeg_to_quat(zdeg):
  z = math.radians(float(zdeg))
  return [0.0, 0.0, math.sin(z/2.0), math.cos(z/2.0)]  # Z 軸旋轉四元數

def main():
  if len(sys.argv) < 3:
    print("usage: python tools/csv_to_motion_json.py db/measurements.csv animation/motions")
    sys.exit(1)

  src = pathlib.Path(sys.argv[1])
  out_dir = pathlib.Path(sys.argv[2])
  out_dir.mkdir(parents=True, exist_ok=True)

  if not src.exists():
    print(f"not found: {src}")
    sys.exit(1)

  df = pd.read_csv(src)

  # 只處理角度（metric == angle）
  df = df[df["metric"] == "angle"].copy()
  if df.empty:
    # 輸出空的 demo 以免前端報錯
    empty = {"name":"Empty","duration":0,"tracks":[]}
    (out_dir / "motion_demo.json").write_text(json.dumps(empty, ensure_ascii=False), encoding="utf-8")
    print("no angle metric; wrote empty motion")
    return

  # 統一單位：如果還是 rad 就轉成 deg
  if "unit" in df.columns:
    mask = df["unit"].astype(str).str.lower().eq("rad")
    if mask.any():
      df.loc[mask, "value"] = df.loc[mask, "value"].astype(float) * 180.0 / math.pi
      df.loc[mask, "unit"] = "deg"

  # 依 joint 分組，為每個骨頭做 quaternion track（簡化：以 Z 軸旋轉示例）
  tracks = []
  for joint, g in df.groupby("joint"):
    bone = BONE_MAP.get(str(joint))
    if not bone:
      continue
    g = g.sort_values("timestamp")
    times = g["timestamp"].astype(float).tolist()
    quats = []
    for zdeg in g["value"].astype(float).tolist():
      quats.extend(eulerZdeg_to_quat(zdeg))
    tracks.append({
      "name": f"{bone}.quaternion",
      "type": "quaternion",
      "times": times,
      "values": quats
    })

  clip = {
    "name": "MotionClip",
    "duration": float(df["timestamp"].max()) if len(df) else 0.0,
    "tracks": tracks
  }

  # 檔名：motion_YYYYmmdd_HHMMSS.json
  ts = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
  out_path = out_dir / f"motion_{ts}.json"
  out_path.write_text(json.dumps(clip, ensure_ascii=False), encoding="utf-8")
  print(f"Wrote {out_path}")

if __name__ == "__main__":
  main()
