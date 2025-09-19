# ===== Mixamo / Xbot 對應表（完整貼上這段） =====

# 1) 上游資料裡常見的關節名字（或大小寫/縮寫） → 規格化的 key
JOINT_ALIASES = {
    # 中軸 / 骨盆
    "hip": "hips", "hips": "hips", "pelvis": "hips", "Hips": "hips",

    # 右腿
    "RightUpLeg": "right_up_leg", "RightLeg": "right_leg", "RightFoot": "right_foot",
    "rightupleg": "right_up_leg", "rightleg": "right_leg", "rightfoot": "right_foot",

    # 左腿
    "LeftUpLeg": "left_up_leg", "LeftLeg": "left_leg", "LeftFoot": "left_foot",
    "leftupleg": "left_up_leg", "leftleg": "left_leg", "leftfoot": "left_foot",

    # 右臂
    "RightShoulder": "right_shoulder", "RightArm": "right_arm",
    "RightForeArm": "right_fore_arm", "RightHand": "right_hand",
    "rightshoulder": "right_shoulder", "rightarm": "right_arm",
    "rightforearm": "right_fore_arm", "righthand": "right_hand",

    # 左臂
    "LeftShoulder": "left_shoulder", "LeftArm": "left_arm",
    "LeftForeArm": "left_fore_arm", "LeftHand": "left_hand",
    "leftshoulder": "left_shoulder", "leftarm": "left_arm",
    "leftforearm": "left_fore_arm", "lefthand": "left_hand",

    # 脊柱/頸/頭（若你的資料有）
    "Spine": "spine", "Spine1": "spine1", "Spine2": "spine2",
    "Neck": "neck", "Head": "head",
}

# 2) 規格化 key → Xbot（Mixamo）的真正骨頭名稱
BONE_MAP = {
    # pelvis / spine
    "hips":        "mixamorigHips",
    "spine":       "mixamorigSpine",
    "spine1":      "mixamorigSpine1",
    "spine2":      "mixamorigSpine2",
    "neck":        "mixamorigNeck",
    "head":        "mixamorigHead",

    # right leg
    "right_up_leg":"mixamorigRightUpLeg",
    "right_leg":   "mixamorigRightLeg",
    "right_foot":  "mixamorigRightFoot",

    # left leg
    "left_up_leg": "mixamorigLeftUpLeg",
    "left_leg":    "mixamorigLeftLeg",
    "left_foot":   "mixamorigLeftFoot",

    # right arm
    "right_shoulder":"mixamorigRightShoulder",
    "right_arm":     "mixamorigRightArm",
    "right_fore_arm":"mixamorigRightForeArm",
    "right_hand":    "mixamorigRightHand",

    # left arm
    "left_shoulder":"mixamorigLeftShoulder",
    "left_arm":     "mixamorigLeftArm",
    "left_fore_arm":"mixamorigLeftForeArm",
    "left_hand":    "mixamorigLeftHand",
}

def canon_key(name: str) -> str:
    """
    把上游資料的關節名（大小寫/帶冒號/縮寫）正規化成我們的 key。
    """
    if not name:
        return name
    k = str(name).strip()
    # 常見變體快速對齊
    if k in JOINT_ALIASES:       # 精準命中（大小寫敏感）
        return JOINT_ALIASES[k]
    k2 = k.replace(":", "")      # 有些會寫成 mixamorig:Hips（雖然我們不會直接拿這個）
    if k2 in JOINT_ALIASES:
        return JOINT_ALIASES[k2]
    kl = k.lower()
    if kl in JOINT_ALIASES:
        return JOINT_ALIASES[kl]
    return kl  # fallback：至少不要噴錯
