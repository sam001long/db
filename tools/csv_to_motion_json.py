#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 db/measurements.csv 轉成 three.js AnimationClip JSON 檔（docs/animation/motions/*.json）
- 針對 Xbot（Mixamo 命名）設計的骨頭對應
- 找不到骨頭 → 直接略過該 track（避免 three 解析時噴 length 錯）
- 支援兩種角度來源：
  1) 長表：metric ∈ {angle_x, angle_y, angle_z} 或 {ax, ay, az}
  2) 寬表：欄名如 RightArm_x / RightArm_y / RightArm_z
"""

from __future__ import annotations
import os, json, math
from pathlib import Path
from typing import Dict, Any, List, Tuple
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]  # repo 根
CSV_PATH = ROOT / "db" / "measurements.csv"
OUT_DIR = ROOT / "docs" / "animation" / "motions"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ===== Mixamo / Xbot 對應表（完整貼上） =====
JOINT_ALIASES = {
    "hip": "hips", "hips": "hips", "pelvis": "hips", "Hips": "hips",
    "RightUpLeg": "right_up_leg", "RightLeg": "right_leg", "RightFoot": "right_foot",
    "rightupleg": "right_up_leg", "rightleg": "right_leg", "rightfoot": "right_foot",
    "LeftUpLeg": "left_up_leg", "LeftLeg": "left_leg", "LeftFoot": "left_foot",
    "leftupleg": "left_up_leg", "leftleg": "left_leg", "leftfoot": "left_foot",
    "RightShoulder": "right_shoulder", "RightArm": "right_arm",
    "RightForeArm": "right_fore_arm", "RightHand": "right_hand",
    "rightshoulder": "right_shoulder", "rightarm": "right_arm",
    "rightforearm": "right_fore_arm", "righthand": "right_hand",
    "LeftShoulder": "left_shoulder", "LeftArm": "left_arm",
    "LeftForeArm": "left_fore_arm", "LeftHand": "left_hand",
    "leftshoulder": "left_shoulder", "leftarm": "left_arm",
    "leftforearm": "left_fore_arm", "lefthand": "left_hand",
    "Spine": "spine", "Spine1": "spine1", "Spine2": "spine2",
    "Neck": "neck", "Head": "head",
}

BONE_MAP = {
    "hips": "mixamorigHips",
    "spine": "mixamorigSpine",
    "spine1": "mixamorigSpine1",
    "spine2": "mixamorigSpine2",
    "neck": "mixamorigNeck",
    "head": "mixamorigHead",
    "right_up_leg": "mixamorigRightUpLeg",
    "right_leg": "mixamorigRightLeg",
    "right_foot": "mixamorigRightFoot",
    "left_up_leg": "mixamorigLeftUpLeg",
    "left_leg": "mixamorigLeftLeg",
    "left_foot": "mixamorigLeftFoot",
    "right_shoulder": "mixamorigRightShoulder",
    "right_arm": "mixamorigRightArm",
    "right_fore_arm": "mixamorigRightForeArm",
    "right_hand": "mixamorigRightHand",
    "left_shoulder": "mixamorigLeftShoulder",
    "left_arm": "mixamorigLeftArm",
    "left_fore_arm": "mixamorigLeftForeArm",
    "left_hand": "mixamorigLeftHand",
}

def canon_key(name: str) -> str:
    if not name:
        return ""
    k = str(name).strip()
    if k in JOINT_ALIASES: return JOINT_ALIASES[k]
    k2 = k.replace(":", "")
    if k2 in JOINT_ALIASES: return JOINT_ALIASES[k2]
    kl = k.lower()
    return JOINT_ALIASES.get(kl, kl)

# --- 角度單位與四元數 ---
def deg2rad(x: float) -> float: return float(x) * math.pi / 180.0
def euler_xyz_to_quat(rx: float, ry: float, rz: float) -> Tuple[float, float, float, float]:
    """
    將 XYZ 歐拉（弧度）轉四元數，矩陣右手系、順序 X->Y->Z（對 Xbot/three 預設相容）
    """
    cx, sx = math.cos(rx/2), math.sin(rx/2)
    cy, sy = math.cos(ry/2), math.sin(ry/2)
    cz, sz = math.cos(rz/2), math.sin(rz/2)
    qw = cx*cy*cz + sx*sy*sz
    qx = sx*cy*cz - cx*sy*sz
    qy = cx*sy*cz + sx*cy*sz
    qz = cx*cy*sz - sx*sy*cz
    return (qx, qy, qz, qw)

def to_float(x): 
    try: return float(x)
    except: return float("nan")

# --- 讀取 measurements.csv 並組動作 ---
def load_measurements() -> pd.DataFrame:
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"{CSV_PATH} 不存在")
    df = pd.read_csv(CSV_PATH)
    # 正規欄位名
    cols = {c:c for c in df.columns}
    for k in list(cols):
        if k.strip().lower() == "time": cols[k] = "timestamp"
        if k.strip().lower() == "joint_name": cols[k] = "joint"
    df = df.rename(columns=cols)
    if "timestamp" not in df or "joint" not in df:
        raise ValueError("需要欄位 timestamp, joint；請確認清洗流程")
    return df

def assemble_long_format(df: pd.DataFrame) -> Dict[str, Dict[str, List[float]]]:
    """
    輸入長表：每列一個軸的角度。支援 metric: angle_x/angle_y/angle_z 或 ax/ay/az 或 angle + axis欄。
    回傳 per-joint 的 {times, x, y, z}
    """
    df2 = df.copy()
    # 嘗試找出 x/y/z 三種 metric
    metric = df2.get("metric")
    has_axis = "axis" in df2.columns
    if metric is None and has_axis:
        metric = df2["axis"]

    # 標準化 metric 名
    def norm_m(m): 
        m = str(m).lower()
        if m in ("angle_x","ax","x"): return "x"
        if m in ("angle_y","ay","y"): return "y"
        if m in ("angle_z","az","z"): return "z"
        return None
    if metric is None: 
        # 不是長表
        return {}

    df2["mxyz"] = [norm_m(m) for m in metric]
    df2 = df2.dropna(subset=["mxyz", "value"])
    out: Dict[str, Dict[str, List[float]]] = {}
    for (j), g in df2.groupby(["joint"]):
        jkey = canon_key(j)
        if jkey not in BONE_MAP: 
            continue
        rec = out.setdefault(jkey, {"times":[], "x":[], "y":[], "z":[]})
        # 以 timestamp 聚合，確保同時間有 x/y/z
        pivot = g.pivot_table(index="timestamp", columns="mxyz", values="value", aggfunc="last")
        pivot = pivot.sort_index()
        for t, row in pivot.iterrows():
            rec["times"].append(to_float(t))
            rec["x"].append(to_float(row.get("x")))
            rec["y"].append(to_float(row.get("y")))
            rec["z"].append(to_float(row.get("z")))
    return out

def assemble_wide_format(df: pd.DataFrame) -> Dict[str, Dict[str, List[float]]]:
    """
    輸入寬表：欄名像 RightArm_x / RightArm_y / RightArm_z，另有 timestamp
    """
    if "timestamp" not in df.columns: return {}
    xyz_cols = [c for c in df.columns if c.endswith(("_x","_y","_z"))]
    if not xyz_cols: return {}
    # 以欄名前綴辨識關節
    prefix = sorted(set(c[:-2] for c in xyz_cols))
    out: Dict[str, Dict[str, List[float]]] = {}
    df2 = df.sort_values("timestamp")
    times = [to_float(t) for t in df2["timestamp"].tolist()]
    for p in prefix:
        jkey = canon_key(p)
        if jkey not in BONE_MAP: 
            continue
        rec = out.setdefault(jkey, {"times":times.copy(), "x":[], "y":[], "z":[]})
        rec["x"] = [to_float(v) for v in df2.get(f"{p}_x", []).tolist()]
        rec["y"] = [to_float(v) for v in df2.get(f"{p}_y", []).tolist()]
        rec["z"] = [to_float(v) for v in df2.get(f"{p}_z", []).tolist()]
    return out

def build_clip(tracks_xyz: Dict[str, Dict[str, List[float]]], unit_hint: str = "deg") -> Dict[str, Any]:
    """
    將每個關節的 x/y/z 角度（度或弧度）轉成 Quaternion tracks，輸出 Three.js AnimationClip JSON。
    """
    clip = {"name": "clip", "tracks": []}
    for ckey, rec in tracks_xyz.items():
        node = BONE_MAP.get(ckey)
        if not node:  # 安全略過未對應骨頭
            continue
        times = [float(t) for t in rec["times"] if pd.notna(t)]
        if not times: 
            continue
        # 三軸角度
        xs = rec["x"]; ys = rec["y"]; zs = rec["z"]
        # 單位處理
        if unit_hint.lower() in ("deg","degree","degrees"):
            rx = [deg2rad(v) for v in xs]
            ry = [deg2rad(v) for v in ys]
            rz = [deg2rad(v) for v in zs]
        else:
            rx, ry, rz = xs, ys, zs
        # times/values 長度對齊（防呆）
        n = min(len(times), len(rx), len(ry), len(rz))
        if n == 0: 
            continue
        times = times[:n]; rx = rx[:n]; ry = ry[:n]; rz = rz[:n]
        values: List[float] = []
        for i in range(n):
            qx,qy,qz,qw = euler_xyz_to_quat(rx[i], ry[i], rz[i])
            values.extend([qx,qy,qz,qw])
        track = {
            "name": f"{node}.quaternion",
            "type": "quaternion",
            "times": times,
            "values": values
        }
        clip["tracks"].append(track)
    return clip

def main():
    df = load_measurements()

    # 推測單位（若有 unit 欄）
    unit_hint = "deg"
    if "unit" in df.columns:
        u = str(df["unit"].dropna().iloc[0]).lower()
        unit_hint = "rad" if "rad" in u else "deg"

    # 嘗試兩種格式
    tracks = assemble_long_format(df)
    if not tracks:
        tracks = assemble_wide_format(df)
    if not tracks:
        raise RuntimeError("辨識不到角度欄位格式（需要 angle_x/angle_y/angle_z 或 ..._x/_y/_z）")

    clip = build_clip(tracks, unit_hint=unit_hint)

    # 檔名：motion_YYYYmmdd_HHMMSS.json（若 df 有 session/activity 可帶入）
    label = "index"
    if "session_id" in df.columns and pd.notna(df["session_id"]).any():
        label = str(df["session_id"].dropna().iloc[0])
    elif "activity" in df.columns and pd.notna(df["activity"]).any():
        label = str(df["activity"].dropna().iloc[0])

    out_path = OUT_DIR / f"motion_{label}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(clip, f, ensure_ascii=False)

    print(f"[OK] wrote {out_path}")

if __name__ == "__main__":
    main()
