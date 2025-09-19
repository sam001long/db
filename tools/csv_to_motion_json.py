#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 db/measurements.csv 轉成 three.js AnimationClip JSON（docs/animation/motions/*.json）

支援輸入格式：
 A) 長表：timestamp, joint, metric(=angle_x/angle_y/angle_z 或 x/y/z/ax/ay/az/angle), value[, unit]
 B) 寬表：timestamp, RightArm_x/RightArm_y/RightArm_z ...
 C) 單一角度欄：timestamp, joint, angle_deg/angle_rad/theta/angle（也可附 axis）

針對 Xbot/Mixamo 命名；對不到骨頭或資料不完整會略過該 track。
"""

from __future__ import annotations
import json, math
from pathlib import Path
from typing import Dict, Any, List, Tuple
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "db" / "measurements.csv"
OUT_DIR = ROOT / "docs" / "animation" / "motions"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------- 別名對應（擴充 hip/knee 等通用名） ----------
JOINT_ALIASES: Dict[str, str] = {}
def _add(canon: str, *names: str):
    for n in names:
        JOINT_ALIASES[n] = canon
        JOINT_ALIASES[n.lower()] = canon
        JOINT_ALIASES[n.replace(":", "")] = canon

# 軀幹
_add("hips",   "Hips","Hip","Pelvis","pelvis","Root","hip")
_add("spine",  "Spine","Spine0")
_add("spine1", "Spine1","LowerSpine","Spine_Lower")
_add("spine2", "Spine2","UpperSpine","Spine_Upper","Chest")
_add("neck",   "Neck")
_add("head",   "Head")

# 腿（預設 Knee 對右腿；之後你有左右就寫 RightKnee / LeftKnee）
_add("right_up_leg","RightUpLeg","RightThigh","R_Thigh","R_UpperLeg")
_add("right_leg",   "RightLeg","RightShin","R_Shin","RightKnee","R_LowerLeg","knee")  # knee → 先對右腿
_add("right_foot",  "RightFoot","R_Foot","RightAnkle","Ankle_R")
_add("right_toe",   "RightToeBase","RightToe","R_Toe","Toe_R")
_add("left_up_leg", "LeftUpLeg","LeftThigh","L_Thigh","L_UpperLeg","LeftKnee_Parent")
_add("left_leg",    "LeftLeg","LeftShin","L_Shin","LeftKnee","L_LowerLeg")
_add("left_foot",   "LeftFoot","L_Foot","LeftAnkle","Ankle_L")
_add("left_toe",    "LeftToeBase","LeftToe","L_Toe","Toe_L")

# 手臂
_add("right_shoulder","RightShoulder","R_Shoulder")
_add("right_arm",     "RightArm","RightUpperArm","R_Arm","R_UpperArm")
_add("right_fore_arm","RightForeArm","RightLowerArm","R_ForeArm","R_LowerArm","RightElbow")
_add("right_hand",    "RightHand","R_Hand","RightWrist","Wrist_R")
_add("left_shoulder", "LeftShoulder","L_Shoulder")
_add("left_arm",      "LeftArm","LeftUpperArm","L_Arm","L_UpperArm")
_add("left_fore_arm", "LeftForeArm","LeftLowerArm","L_ForeArm","L_LowerArm","LeftElbow")
_add("left_hand",     "LeftHand","L_Hand","LeftWrist","Wrist_L")

# Mixamo / Xbot 實際骨頭名
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

# ---------- 角度→四元數 ----------
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

def nz(v: float) -> float:
    """非數或無窮時回 0，避免 NaN 進到四元數。"""
    return v if (isinstance(v,(int,float)) and math.isfinite(v)) else 0.0

# ---------- 讀 CSV ----------
def load_measurements() -> pd.DataFrame:
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"{CSV_PATH} 不存在")
    df = pd.read_csv(CSV_PATH)

    # 標準欄名
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

# ---------- A) 長表（含 metric=angle 的單軸情境） ----------
def assemble_long_format(df: pd.DataFrame) -> Dict[str, Dict[str, List[float]]]:
    # metric 欄（或 axis）
    if "metric" in df.columns:
        metric_series = df["metric"].astype(str)
    elif "axis" in df.columns:
        metric_series = df["axis"].astype(str)
    else:
        return {}

    # 值欄
    value_col = None
    for cand in ("value","angle","val"):
        if cand in df.columns:
            value_col = cand
            break
    if value_col is None:
        return {}

    def norm(m: str):
        m = m.strip().lower()
        if m in ("x","ax","angle_x","rot_x"): return "x"
        if m in ("y","ay","angle_y","rot_y"): return "y"
        if m in ("z","az","angle_z","rot_z"): return "z"
        if m in ("angle",): return "y"  # 你的資料：只有一個 angle → 預設 y 軸
        return None

    df2 = df.copy()
    df2["mxyz"] = metric_series.map(norm)
    df2 = df2.dropna(subset=["mxyz", value_col, "timestamp", "joint"])

    out: Dict[str, Dict[str, List[float]]] = {}
    # 先看這個 joint 是否只有單一軸（例如全都是 'angle' → y）
    for j, g in df2.groupby("joint"):
        ck = canon_key(j)
        if ck not in BONE_MAP:
            continue
        g = g.sort_values("timestamp")
        # 以 timestamp -> mxyz 做一個小 pivot
        piv = g.pivot_table(index="timestamp", columns="mxyz", values=value_col, aggfunc="last").sort_index()

        rec = out.setdefault(ck, {"times": [], "x": [], "y": [], "z": []})
        for t, row in piv.iterrows():
            rec["times"].append(to_float(t))
            x = to_float(row.get("x")) if "x" in row.index else float("nan")
            y = to_float(row.get("y")) if "y" in row.index else float("nan")
            z = to_float(row.get("z")) if "z" in row.index else float("nan")

            # 若只有單軸出現，其它兩軸自動補 0（避免 NaN）
            if math.isfinite(y) and not math.isfinite(x) and not math.isfinite(z):
                x = 0.0; z = 0.0
            elif math.isfinite(x) and not math.isfinite(y) and not math.isfinite(z):
                y = 0.0; z = 0.0
            elif math.isfinite(z) and not math.isfinite(x) and not math.isfinite(y):
                x = 0.0; y = 0.0

            rec["x"].append(nz(x))
            rec["y"].append(nz(y))
            rec["z"].append(nz(z))
    return out

# ---------- B) 寬表 ----------
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
        if ck not in BONE_MAP: continue
        rec = out.setdefault(ck, {"times": times.copy(), "x": [], "y": [], "z": []})
        rec["x"] = [nz(to_float(v)) for v in g.get(f"{p}_x", []).tolist()]
        rec["y"] = [nz(to_float(v)) for v in g.get(f"{p}_y", []).tolist()]
        rec["z"] = [nz(to_float(v)) for v in g.get(f"{p}_z", []).tolist()]
    return out

# ---------- C) 單一角度欄 ----------
def assemble_single_angle(df: pd.DataFrame) -> Dict[str, Dict[str, List[float]]]:
    angle_col = None
    unit_hint = None
    for cand in ("angle_deg","angle_rad","theta","angle"):
        if cand in df.columns:
            angle_col = cand; break
    if angle_col is None:
        return {}

    unit_hint = ("rad" if angle_col in ("angle_rad","theta") else
                 ("rad" if ("unit" in df.columns and df["unit"].astype(str).str.contains("rad", case=False, na=False).any()) else "deg"))

    axis_series = (df["axis"].astype(str).str.lower() if "axis" in df.columns else pd.Series(["y"]*len(df)))

    df2 = df[["timestamp","joint",angle_col]].copy()
    df2["axis"] = axis_series
   df2 = df2.dropna(subset=["timestamp","joint", angle_col, "axis"])


    out: Dict[str, Dict[str, List[float]]] = {}
    for (j, ax), g in df2.groupby(["joint","axis"]):
        ck = canon_key(j)
        if ck not in BONE_MAP: continue
        g = g.sort_values("timestamp")
        times = [to_float(t) for t in g["timestamp"].tolist()]
        vals  = [to_float(v) for v in g[angle_col].tolist()]
        rec = out.setdefault(ck, {"times": [], "x": [], "y": [], "z": []})
        if not rec["times"]:
            rec["times"] = times
            rec["x"] = [0.0]*len(times); rec["y"] = [0.0]*len(times); rec["z"] = [0.0]*len(times)
        if ax.startswith("x"): rec["x"] = vals
        elif ax.startswith("z"): rec["z"] = vals
        else: rec["y"] = vals
        for k in ("times","x","y","z"):
            rec[k] = rec[k][:len(rec["times"])]
        rec["_unit_hint"] = unit_hint
    return out

# ---------- 組動畫 ----------
def build_clip(tracks_xyz: Dict[str, Dict[str, List[float]]], unit_hint: str = "deg") -> Dict[str, Any]:
    clip = {"name": "clip", "tracks": []}
    for ck, rec in tracks_xyz.items():
        node = BONE_MAP.get(ck)
        if not node: continue
        times = [float(t) for t in rec["times"] if pd.notna(t)]
        xs, ys, zs = rec["x"], rec["y"], rec["z"]
        hint = (rec.get("_unit_hint") or unit_hint or "deg").lower()
        if hint.startswith("deg"):
            rx = [deg2rad(v) for v in xs]; ry = [deg2rad(v) for v in ys]; rz = [deg2rad(v) for v in zs]
        else:
            rx, ry, rz = xs, ys, zs
        n = min(len(times), len(rx), len(ry), len(rz))
        if n <= 0: continue
        times = times[:n]; rx=rx[:n]; ry=ry[:n]; rz=rz[:n]
        values: List[float] = []
        for i in range(n):
            qx,qy,qz,qw = euler_xyz_to_quat(rx[i], ry[i], rz[i])
            # 保底：不是有限數就用 0,0,0,1
            if not all(map(math.isfinite, (qx,qy,qz,qw))):
                qx=qy=qz=0.0; qw=1.0
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

    # 預設單位
    unit_hint = "deg"
    if "unit" in df.columns and not df["unit"].dropna().empty:
        u0 = str(df["unit"].dropna().iloc[0]).lower()
        if "rad" in u0: unit_hint = "rad"

    # 依序嘗試三種格式
    tracks = assemble_long_format(df) or assemble_wide_format(df) or assemble_single_angle(df)
    if not tracks:
        raise RuntimeError("辨識不到角度欄位：請提供 metric+value（或 *_x/_y/_z，或 angle/angle_deg/theta）")

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
