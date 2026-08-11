"""技能层(运行时子集):清单(registry.yaml + gestures.yaml)加载 + 可行域校验。

这里是从开发仓库 VLA-HandArm 拆出来的**运行时最小集**,只保留 bridge 真正
要用的两个模块:

  schema.py     清单加载/校验/参数归一。registry.yaml 和 gestures.yaml 的真源。
  hand_pose.py  五指语义 → 六关节弧度 + 拇指-食指可行域校验。

开发仓库里还有 backend / intent / runner / console_exec 等(动作展开、文本意图、
ROS 侧执行),bridge 不走那些路,所以没拆过来。要那些请看开发仓库。

⚠ 标定数据(hand_pose.py 里的 RAW_MAP / LIMIT_HI / FEASIBLE)是在真手上量出来
   的,和开发仓库同源。换硬件必须重新标定,不能照抄。
"""
from .schema import (  # noqa: F401
    ParamSpec,
    RegistryError,
    SafetySpec,
    SkillRegistry,
    SkillSpec,
    get_registry,
    load_registry,
)

__all__ = [
    "ParamSpec", "RegistryError", "SafetySpec", "SkillRegistry", "SkillSpec",
    "get_registry", "load_registry",
]
