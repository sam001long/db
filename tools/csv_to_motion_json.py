#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 db/measurements.csv 轉成 three.js AnimationClip JSON（docs/animation/motions/*.json）
- 針對 Xbot/Mixamo 骨頭命名
- 找不到骨頭或資料不完整 → 略過該 track（避免 three 解析時噴錯）
- 支援兩種格式：
  1) 長表：timestamp, joint, metric(=angle_x/angle_y/angle_z 或 x/y/z/ax/ay/az), value[, unit, session_id...]
  2) 寬表：timestamp, RightArm_x/RightArm_y/RightArm_z ...
"""

from __future__ import annotations
import os, json, math
from pathlib import Path
from typing import Dict, Any, List, Tuple
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "db" / "measurements.csv"
OUT_DIR = ROOT / "docs" / "animation" / "motions"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------- 別名對應 ----------
JOINT_ALIASES: Dict[str, str] = {}
def _add(canon: str, *names: str):
    for n in names:
        JOINT_ALIASES[n] = canon
        JOINT_ALIASES[n.lower()] = canon
        JOINT_ALIASES[n.replace(":", "")] = canon

# 中軸
_add("hips", "Hips","Hip","Pelvis","pelvis","Root")
_add("spine","Spine","Spine0")
_add("spine1","Spine1","LowerSpine","Spine_Lower")
_add("spine2","Spine2","UpperSpine","Spine_Upper","Chest")
_add("neck","Neck")
_add("head","Head")
# 腿
_add("right_up_leg","RightUpLeg","RightThigh","R_Thigh","R_UpperLeg")
_add("right_leg","RightLeg","RightShin","R_Shin","RightKnee","R_LowerLeg")
_add("right_foot","RightFoot","R_Foot","RightAnkle","Ankle_R")
_add("right_toe","RightToeBase","RightToe","R_Toe","Toe_R")
_add("left_up_leg","LeftUpLeg","LeftThigh","L_Thigh","L_UpperLeg")
_add("left_leg","LeftLeg","LeftShin","L_Shin","LeftKnee","L_LowerLeg")
_add("left_foot","LeftFoot","L_Foot","LeftAnkle","Ankle_L")
_add("left_toe","LeftToeBase","LeftToe","L_Toe","Toe_L")
# 手臂
_add("right_shoulder","RightShoulder","R_Shoulder")
_add("right_arm","RightArm","RightUpperArm","R_Arm","R_UpperArm")
_add("right_fore_arm","RightForeArm","RightLowerArm","R_ForeArm","R_LowerArm","RightElbow")
_add("right_hand","RightHand","R_Hand","RightWrist","Wrist_R")
_add("left_shoulder","LeftShoulder","L_Shoulder")
_add("left_arm","LeftArm","LeftUpperArm","L_Arm","L_UpperArm")
_add("left_fore_arm","LeftForeArm","LeftLowerArm","L_ForeArm","L_LowerArm","LeftElbow")
_add("left_hand","LeftHand","L_Hand","LeftWrist","Wrist_L")

BONE_MAP = {
    "hips":"mixamorigHips","spine":"mixamorigSpine","spine1":"mixamorigSpine1","spine2":"mixamorigSpine2",
    "neck":"mixamorigNeck","head":"mixamorigHead",
    "right_up_leg":"mixamorigRightUpLeg","right_leg":"mixamorigRightLeg","right_foot":"mixamorigRightFoot","right_toe":"mixamorigRightToeBase",
    "left_up_leg":"mixamorigLeftUpLeg","left_leg":"mixamorigLeftLeg","left_foot":"mixamorigLeftFoot","left_toe":"mixamorigLeftToeBase",
    "right_shoulder":"mixamorigRightShoulder","right_arm":"mixamorigRightArm","right_fore_arm":"mixamorigRightForeArm","right_hand":"mixamorigRightHand",
    "left_shoulder":"mixamorigLeftShoulder","left_arm":"mixamorigLeftArm","left_fore_arm":"mixamorigLeftForeArm","left_hand":"mixamorigLeftHand",
}

def canon_key(name: str) -> str:
    if not name: return ""
    k = str(name).strip()
    return JOINT_ALIASES.get(k) or JOINT_ALIASES.get(k.replace(":", "")) or JOINT_ALIASES.get(k.lower()) or k.lower()

# ---------- 角度轉四元數 ----------
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

def to_float(x):
    try: return float(x)
    except: return float("nan")

# ---------- 讀取 CSV ----------
def load_measurements() -> pd.DataFrame:
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"{CSV_PATH} 不存在")
    df = pd.read_csv(CSV_PATH)

    # 標準化欄位名
    rename = {}
    for c in df.columns:
        lc = c.strip().lower()
        if lc == "time": rename[c] = "timestamp"
        if lc == "joint_name": rename[c] = "joint"
    df = df.rename(columns=rename)

    if "timestamp" not in df.columns:
        if "frame" in df.columns:
            df["timestamp"] = df["frame"].astype(float) / 30.0
        else:
            raise ValueError("需要欄位 timestamp（或 frame）")

    if "joint" not in df.columns:
        raise ValueError("需要欄位 joint")

    return df

# ---------- 長表 ----------
def assemble_long_format(df: pd.DataFrame) -> Dict[str, Dict[str, List[float]]]:
    # 不要用 Series 的 or；改成明確檢查欄位是否存在
    if "metric" in df.columns:
        metric_series = df["metric"]
    elif "axis" in df.columns:
        metric_series = df["axis"]
    else:
        return {}  # 不是長表

    # 值欄
    value_col = None
    for cand in ("value","angle","val"):
        if cand in df.columns:
            value_col = cand
            break
    if value_col is None:
        return {}

    def norm(m):
        m = str(m).lower()
        if m in ("x","ax","angle_x"): return "x"
        if m in ("y","ay","angle_y"): return "y"
        if m in ("z","az","angle_z"): return "z"
        return None

    df2 = df.copy()
    df2["mxyz"] = metric_series.map(norm)
    df2 = df2.dropna(subset=["mxyz", value_col, "timestamp", "joint"])

    out: Dict[str, Dict[str, List[float]]] = {}
    for j, g in df2.groupby("joint"):
        ck = canon_key(j)
        if ck not in BONE_MAP:  # 不認得的骨頭直接略過
            continue
        piv = g.pivot_table(index="timestamp", columns="mxyz", values=value_col, aggfunc="last").sort_index()
        rec = out.setdefault(ck, {"times": [], "x": [], "y": [], "z": []})
        for t, row in piv.iterrows():
            rec["times"].append(to_float(t))
            rec["x"].append(to_float(row.get("x")))
            rec["y"].append(to_float(row.get("y")))
            rec["z"].append(to_float(row.get("z")))
    return out

# ---------- 寬表 ----------
def assemble_wide_format(df: pd.DataFrame) -> Dict[str, Dict[str, List[float]]]:
    if "timestamp" not in df.columns:
        return {}
    xyz_cols = [c for c in df.columns if c.endswith(("_x","_y","_z"))]
    if not xyz_cols:
        return {}

    prefixes = sorted(set(c[:-2] for c in xyz_cols))
    out: Dict[str, Dict[str, List[float]]] = {}
    g = df.sort_values("timestamp")
    times = [to_float(t) for t in g["timestamp"].tolist()]

    for p in prefixes:
        ck = canon_key(p)
        if ck not in BONE_MAP:
            continue
        rec = out.setdefault(ck, {"times": times.copy(), "x": [], "y": [], "z": []})
        rec["x"] = [to_float(v) for v in g.get(f"{p}_x", []).tolist()]
        rec["y"] = [to_float(v) for v in g.get(f"{p}_y", []).tolist()]
        rec["z"] = [to_float(v) for v in g.get(f"{p}_z", []).tolist()]
    return out

# ---------- 組動畫 ----------
def build_clip(tracks_xyz: Dict[str, Dict[str, List[float]]], unit_hint: str = "deg") -> Dict[str, Any]:
    clip = {"name": "clip", "tracks": []}
    for ck, rec in tracks_xyz.items():
        node = BONE_MAP.get(ck)
        if not node: 
            continue
        times = [float(t) for t in rec["times"] if pd.notna(t)]
        xs, ys, zs = rec["x"], rec["y"], rec["z"]
        if unit_hint.lower().startswith("deg"):
            rx = [deg2rad(v) for v in xs]; ry = [deg2rad(v) for v in ys]; rz = [deg2rad(v) for v in zs]
        else:
            rx, ry, rz = xs, ys, zs
        n = min(len(times), len(rx), len(ry), len(rz))
        if n <= 0:
            continue
        times = times[:n]; rx = rx[:n]; ry = ry[:n]; rz = rz[:n]
        values: List[float] = []
        for i in range(n):
            qx, qy, qz, qw = euler_xyz_to_quat(rx[i], ry[i], rz[i])
            values.extend([qx, qy, qz, qw])
        clip["tracks"].append({
            "name": f"{node}.quaternion",
            "type": "quaternion",
            "times": times,
            "values": values
        })
    return clip

def main():
    df = load_measurements()

    # 單位偵測
    unit_hint = "deg"
    if "unit" in df.columns and not df["unit"].dropna().empty:
        u0 = str(df["unit"].dropna().iloc[0]).lower()
        if "rad" in u0: unit_hint = "rad"

    # 長表或寬表
    tracks = assemble_long_format(df)
    if not tracks:
        tracks = assemble_wide_format(df)
    if not tracks:
        raise RuntimeError("辨識不到角度欄位：需要 metric(angle_x/y/z) + value，或 *_x/_y/_z 寬表")

    clip = build_clip(tracks, unit_hint=unit_hint)

    # 檔名標籤
    label = "index"
    for c in ("session_id","activity"):
        if c in df.columns and not df[c].dropna().empty:
            label = str(df[c].dropna().iloc[0]); break

    out_path = OUT_DIR / f"motion_{label}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(clip, f, ensure_ascii=False)
    print(f"[OK] wrote {out_path} with {len(clip['tracks'])} tracks")

if __name__ == "__main__":
    main()
