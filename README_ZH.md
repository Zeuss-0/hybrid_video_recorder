# hybrid_video_recorder

ROS1 录像功能包，保存一份全程原视频和一份可暂停写入的原视频。

[English](README.md)

## 录像行为

| 文件 | 内容 | 暂停时 |
| --- | --- | --- |
| `<时间戳>.mp4` | 完整原始相机画面 | 持续录制 |
| `aimed_<时间戳>.mp4` | 仅录制期间的原始画面 | 停止写入 |

两个录像节点始终订阅 `/camera/image_raw`，各自使用独立的 FFmpeg 进程。暂停不会断开订阅。YOLO 独立运行，检测失败不会停止这两路录像。

## 启动

需要已编译的 ROS1 工作空间和 FFmpeg。终端 1：启动相机。

```bash
source ~/catkin_ws/devel/setup.bash
rosrun mvs camera_stream
```

终端 2：启动手柄总控，默认启用 Hybrid 录像。

```bash
source ~/test_ws/devel/setup.bash
source ~/catkin_ws/devel/setup.bash
source ~/moma_ws/devel/setup.bash
roslaunch teleop_joy_ctrl teleop_joy_ctrl.launch
```

如果 Dobot 驱动已运行，在启动命令后加上 `start_arm_bringup:=false`。

只需录像服务时，可在加载 `moma_ws` 环境后执行 `roslaunch hybrid_video_recorder hybrid_video_recorder.launch`。两种启动方式选一种，避免重复启动录像节点。

## R3 操作

| 手势 | 功能 |
| --- | --- |
| 空闲时双击 | 开始录像 |
| 录像或暂停时短按 | 暂停/继续 aimed 视频 |
| 长按至少 1.5 秒 | 保存并结束本次录像 |

录像包不负责启动或关闭相机，结束录像后，单独启动的相机继续运行。

## 配置与状态

在 [config/default.yaml](config/default.yaml) 中修改 `image_topic`、`recording_root`、`fps` 及写入参数。每次录像目录为 `<recording_root>/<时间戳>/`。

`recording_root` 按以下顺序确定：

1. 非空的启动参数 `recording_root`。
2. 配置文件中的 ROS 参数 `~recording_root`。
3. 参数为空时，使用环境变量 `HYBRID_VIDEO_RECORDING_ROOT`。
4. `<功能包>/recordings`。`<功能包>` 为 `rospack find hybrid_video_recorder` 的结果。

`~` 会展开。相对路径相对于功能包目录解析。

```bash
export HYBRID_VIDEO_RECORDING_ROOT=~/recordings

roslaunch hybrid_video_recorder hybrid_video_recorder.launch \
  recording_root:=~/recordings
```

```bash
rostopic echo /teleop_joy_ctrl/video/status
rostopic echo /teleop_joy_ctrl/video/output_dir
rostopic hz /camera/image_raw
```

管理节点在 `/teleop_joy_ctrl/video/` 下提供 `start`、`pause`、`resume`、`stop` 四个 Trigger 服务。

切换到旧版 YOLO 耦合录像：

```bash
roslaunch teleop_joy_ctrl teleop_joy_ctrl.launch \
  start_hybrid_video_manager:=false start_legacy_video_manager:=true
```
