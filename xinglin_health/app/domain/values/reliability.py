"""回答可靠性分级（FR-023）：按来源类型分别判定后汇总。"""

from enum import Enum


class Reliability(str, Enum):
    HIGH = "high"        # 回答有直接依据
    PARTIAL = "partial"  # 部分内容缺乏直接依据
    LOW = "low"          # 缺乏依据（触发信息不足提示）
