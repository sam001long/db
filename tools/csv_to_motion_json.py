#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
import json, math
from pathlib import Path
from typing import Dict, Any, List, Tuple
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "db" / "measurements.csv"
OUT_DIR = ROOT / "docs" / "animation" / "motions"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 你目前資料只用到這些關節名：hip、knee
BONE_MAP = {
    "hip":  "mixamorigHips",
    "hips": "mixamorigHips",
    "pelvis":"mixamorigHips",
    "knee": "mixamorigRightLeg",   # 先對右腿；之後你有 LeftKnee/RightKnee 再細分
    "rightknee": "mixamorigRightLeg",
    "leftknee":  "mixamorigLeftLeg",
}

def deg2rad(x: float) -> float: return float(x) * math.pi / 180.0

def euler_xyz_to_quat(rx: float, ry: float, rz: float) -> Tuple[float,float,float,float]:
    cx, sx = math.cos(rx/2), math.sin(rx/2)
    cy, sy = math.cos(ry/2), math.sin(ry/2)
    cz, sz = math.cos(rz/2), math.sin(rz/2)
    qw = cx*cy*cz + sx*sy*sz
    qx = sx*cy*cz - cx*sy*sz
    qy = cx*sy*cz + sx*cy*sz
    qz = cx*cy*sz - sx*sy*cz
    return (qx,qy,qz,qw)

def nz(v) -> float:
    try:
        f = float(v)
        return f if math.isfinite(f) else 0.0
    except:
        return 0.0

def main():
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"{CSV_PATH} 不存在")

    df = pd.read_csv(CSV_PATH)

    # 最小欄位檢查
    required = {"joint","timestamp","value"}
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise RuntimeError(f"缺少必要欄位：{missing}（至少要 joint,timestamp,value；你的檔有 {list(df.columns)}）")

    # 單位：預設 deg；若有 unit 欄含 rad 就用 rad
    unit_hint = "deg"
    if "unit" in df.columns and df["unit"].astype(str).str.contains("rad", case=False, na=False).any():
        unit_hint = "rad"

    # 只挑我們要的欄位，並排序
    df2 = df[["joint","timestamp","value"]].copy()
    df2["joint"] = df2["joint"].astype(str).str.strip().str.lower()
    df2 = df2.sort_values(["joint","timestamp"])

    # 依關節分組，組成三軸角度（你的 metric=angle → 對 y 軸；x,z=0）
    per_joint: Dict[str, Dict[str, List[float]]] = {}
    for j, g in df2.groupby("joint"):
        bone = BONE_MAP.get(j)
        if not bone:
            # 不在對應表就跳過（避免 three 噴錯）
            continue
        times = [nz(t) for t in g["timestamp"].tolist()]
        angs  = [nz(v) for v in g["value"].tolist()]
        if unit_hint == "deg":
            angs = [deg2rad(v) for v in angs]
        # x,z 全 0；y 用角度
        rx = [0.0]*len(angs)
        ry = angs
        rz = [0.0]*len(angs)
        # 組 quaternion values
        values: List[float] = []
        for i in range(len(times)):
            qx,qy,qz,qw = euler_xyz_to_quat(rx[i], ry[i], rz[i])
            values.extend([qx,qy,qz,qw])
        per_joint[j] = {
            "bone": bone,
            "times": [float(t) for t in times],
            "values": values
        }

    # 組 Three.js clip JSON
    clip = {"name":"clip","tracks":[]}
    for j, rec in per_joint.items():
        clip["tracks"].append({
            "name": f"{rec['bone']}.quaternion",
            "type": "quaternion",
            "times": rec["times"],
            "values": rec["values"]
        })

    out_path = OUT_DIR / "motion_index.json"   # 沒有 session_id 就固定叫 index
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(clip, f, ensure_ascii=False)
    print(f"[OK] wrote {out_path} with {len(clip['tracks'])} tracks")

if __name__ == "__main__":
    main()
