#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 db/measurements.csv 轉成 three.js AnimationClip JSON 檔（docs/animation/motions/*.json）
- 針對 Xbot（Mixamo 命名）設計的骨頭對應
- 找不到骨頭 → 略過該 track（避免 three 解析時噴 length 錯）
- 支援兩種格式：
  1) 長表：metric ∈ {angle_x, angle_y, angle_z} 或 {ax, ay, az} 或 axis 欄位 x/y/z
  2) 寬表：RightArm_x / RightArm_y / RightArm_z + timestamp
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

# ===== Mixamo / Xbot 對應 =====

# 上游各種寫法 → 規格化 key
JOINT_ALIASES: Dict[str, str] = {}

def add_alias(canon: str, *names: str):
    for n in names:
        JOINT_ALIASES[n] = canon
        JOINT_ALIASES[n.lower()] = canon
        JOINT_ALIASES[n.replace(":", "")] = canon

# 中軸
add_alias("hips", "Hips","Hip","Pelvis","Pelvic","Root","hip","pelvis")
add_alias("spine", "Spine","Spine0")
add_alias("spine1","Spine1","LowerSpine","Spine_Lower")
add_alias("spine2","Spine2","UpperSpine","Spine_Upper","Chest")
add_alias("neck",  "Neck","neck")
add_alias("head",  "Head","head")

# 右腿（大腿/小腿/腳/趾）
add_alias("right_up_leg", "RightUpLeg","RightThigh","R_Thigh","RightLegUpper","R_UpperLeg")
add_alias("right_leg",    "RightLeg","RightShin","R_Shin","RightKnee","R_LowerLeg")
add_alias("right_foot",   "RightFoot","R_Foot","Ankle_R","RightAnkle")
add_alias("right_toe",    "RightToeBase","R_Toe","RightToe","Toe_R")

# 左腿
add_alias("left_up_leg",  "LeftUpLeg","LeftThigh","L_Thigh","LeftLegUpper","L_UpperLeg")
add_alias("left_leg",     "LeftLeg","LeftShin","L_Shin","LeftKnee","L_LowerLeg")
add_alias("left_foot",    "LeftFoot","L_Foot","Ankle_L","LeftAnkle")
add_alias("left_toe",     "LeftToeBase","L_Toe","LeftToe","Toe_L")

# 右臂（肩/上臂/前臂/手腕/手）
add_alias("right_shoulder","RightShoulder","R_Shoulder")
add_alias("right_arm",     "RightArm","RightUpperArm","R_Arm","R_UpperArm")
add_alias("right_fore_arm","RightForeArm","RightLowerArm","R_ForeArm","R_LowerArm","RightElbow")
add_alias("right_hand",    "RightHand","R_Hand","RightWrist","Wrist_R")

# 左臂
add_alias("left_shoulder", "LeftShoulder","L_Shoulder")
add_alias("left_arm",      "LeftArm","LeftUpperArm","L_Arm","L_UpperArm")
add_alias("left_fore_arm", "LeftForeArm","LeftLowerArm","L_ForeArm","L_LowerArm","LeftElbow")
add_alias("left_hand",     "LeftHand","L_Hand","LeftWrist","Wrist_L")

# 規格化 key → Mixamo 真實骨頭名
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
    "right_toe": "mixamorigRightToeBase",
    "left_up_leg": "mixamorigLeftUpLeg",
    "left_leg": "mixamorigLeftLeg",
    "left_foot": "mixamorigLeftFoot",
    "left_toe": "mixamorigLeftToeBase",
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
    if not name: return ""
    k = str(name).strip()
    return JOINT_ALIASES.get(k) or JOINT_ALIASES.get(k.replace(":", "")) or JOINT_ALIASES.get(k.lower()) or k.lower()

# -------- 角度 → 四元數 --------
def deg2rad(x: float) -> float: return float(x) * math.pi / 180.0
def euler_xyz_to_quat(rx: float, ry: float, rz: float) -> Tuple[float, float, float, float]:
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

# -------- 讀取/組裝 --------
def load_measurements() -> pd.DataFrame:
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"{CSV_PATH} 不存在")
    df = pd.read_csv(CSV_PATH)
    # 正規欄位名
    rename = {}
    for c in df.columns:
        lc = c.strip().lower()
        if lc == "time": rename[c] = "timestamp"
        if lc == "joint_name": rename[c] = "joint"
    df = df.rename(columns=rename)
    if "timestamp" not in df.columns or "joint" not in df.columns:
        # 也允許 frame（假設 30fps）
        if "frame" in df.columns:
            df["timestamp"] = df["frame"].astype(float) / 30.0
        else:
            raise ValueError("需要欄位 timestamp/joint（或 frame/joint）")
    return df

def assemble_long_format(df: pd.DataFrame) -> Dict[str, Dict[str, List[float]]]:
    metric = df.get("metric") or df.get("axis")
    if metric is None: return {}
    def norm(m):
        m = str(m).lower()
        if m in ("x","ax","angle_x"): return "x"
        if m in ("y","ay","angle_y"): return "y"
        if m in ("z","az","angle_z"): return "z"
        return None
    df2 = df.copy()
    df2["mxyz"] = [norm(m) for m in metric]
    df2 = df2.dropna(subset=["mxyz","value"])
    out: Dict[str, Dict[str, List[float]]] = {}
    for j,g in df2.groupby("joint"):
        ck = canon_key(j)
        if ck not in BONE_MAP: continue
        piv = g.pivot_table(index="timestamp", columns="mxyz", values="value", aggfunc="last").sort_index()
        rec = out.setdefault(ck, {"times":[], "x":[], "y":[], "z":[]})
        for t,row in piv.iterrows():
            rec["times"].append(to_float(t))
            rec["x"].append(to_float(row.get("x")))
            rec["y"].append(to_float(row.get("y")))
            rec["z"].append(to_float(row.get("z")))
    return out

def assemble_wide_format(df: pd.DataFrame) -> Dict[str, Dict[str, List[float]]]:
    if "timestamp" not in df.columns: return {}
    xyz = [c for c in df.columns if c.endswith(("_x","_y","_z"))]
    if not xyz: return {}
    prefixes = sorted(set(c[:-2] for c in xyz))
    out: Dict[str, Dict[str, List[float]]] = {}
    times = [to_float(t) for t in df.sort_values("timestamp")["timestamp"].tolist()]
    for p in prefixes:
        ck = canon_key(p)
        if ck not in BONE_MAP: continue
        g = df.sort_values("timestamp")
        rec = out.setdefault(ck, {"times":times.copy(), "x":[], "y":[], "z":[]})
        rec["x"] = [to_float(v) for v in g.get(f"{p}_x", []).tolist()]
        rec["y"] = [to_float(v) for v in g.get(f"{p}_y", []).tolist()]
        rec["z"] = [to_float(v) for v in g.get(f"{p}_z", []).tolist()]
    return out

def build_clip(tracks_xyz: Dict[str, Dict[str, List[float]]], unit_hint: str = "deg") -> Dict[str, Any]:
    clip = {"name":"clip", "tracks":[]}
    for ck, rec in tracks_xyz.items():
        node = BONE_MAP.get(ck)
        if not node: continue
        times = [float(t) for t in rec["times"] if pd.notna(t)]
        xs,ys,zs = rec["x"], rec["y"], rec["z"]
        if unit_hint.lower().startswith("deg"):
            rx = [deg2rad(v) for v in xs]; ry=[deg2rad(v) for v in ys]; rz=[deg2rad(v) for v in zs]
        else:
            rx,ry,rz = xs,ys,zs
        n = min(len(times), len(rx), len(ry), len(rz))
        if n<=0: continue
        times = times[:n]; rx=rx[:n]; ry=ry[:n]; rz=rz[:n]
        values: List[float] = []
        for i in range(n):
            qx,qy,qz,qw = euler_xyz_to_quat(rx[i],ry[i],rz[i])
            values.extend([qx,qy,qz,qw])
        clip["tracks"].append({
            "name": f"{node}.quaternion",
            "type": "quaternion",
            "times": times,
            "values": values
        })
    return clip

def main():
    df = load_measurements()
    unit_hint = "deg"
    if "unit" in df.columns and not df["unit"].dropna().empty:
        u = str(df["unit"].dropna().iloc[0]).lower()
        unit_hint = "rad" if "rad" in u else "deg"

    tracks = assemble_long_format(df) or assemble_wide_format(df)
    if not tracks:
        raise RuntimeError("辨識不到角度欄位（需 angle_x/y/z 或 *_x/_y/_z）")

    clip = build_clip(tracks, unit_hint=unit_hint)

    label = "index"
    if "session_id" in df.columns and not df["session_id"].dropna().empty:
        label = str(df["session_id"].dropna().iloc[0])
    elif "activity" in df.columns and not df["activity"].dropna().empty:
        label = str(df["activity"].dropna().iloc[0])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"motion_{label}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(clip, f, ensure_ascii=False)
    print(f"[OK] wrote {out_path} with {len(clip['tracks'])} tracks")

if __name__ == "__main__":
    main()
