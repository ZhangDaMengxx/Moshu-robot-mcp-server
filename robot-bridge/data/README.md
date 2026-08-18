# LeRobot 录制技能包

本目录保存从相邻 `lerobotTest/data` 导入的原始录制包：

- `gestures/`：`hand_gesture_pack/2`，仅灵巧手。
- `combos/`：`combo_pack/1`，机械臂与灵巧手联合关键帧。

这些 JSON 保留录制时的数据，不在导入时重排、夹取或改写关节值。`combo_pack/1`
联合包可通过 MCP 的 `skill_list`、`skill_execute` 执行；所有帧会在运动前完成关节
限位和手部可行域预检。执行前应对 `recorded_from: mock` 的联合包在
真机上重新录制或人工复核。

`sim/out/robot_traj_nero_inspire_rgb.npz` 是与当前 7 轴机械臂和 6 驱动灵巧手兼容的
示教轨迹。RGB-D 版本的手部数据是 12 关节模型，未导入，不能直接下发给 6 驱动硬件。
