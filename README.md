# hybrid_video_recorder

ROS1 recorder for a complete raw video and a pause-aware raw video.

[中文版](README_ZH.md)

## Recording Behavior

| File | Content | During pause |
| --- | --- | --- |
| `<timestamp>.mp4` | Complete original camera video | Keeps recording |
| `aimed_<timestamp>.mp4` | Original frames from active recording intervals | Stops writing |

Both workers subscribe to `/camera/image_raw` continuously and use separate FFmpeg processes. Pause does not reconnect subscribers. YOLO runs independently; its failure does not stop these recordings.

## Start

Requires a built ROS1 workspace and FFmpeg. Start the camera in terminal 1:

```bash
source ~/catkin_ws/devel/setup.bash
rosrun mvs camera_stream
```

Start the gamepad controller in terminal 2; Hybrid recording is enabled by default:

```bash
source ~/test_ws/devel/setup.bash
source ~/catkin_ws/devel/setup.bash
source ~/moma_ws/devel/setup.bash
roslaunch teleop_joy_ctrl teleop_joy_ctrl.launch
```

If Dobot bringup is already running, append `start_arm_bringup:=false`.

For recording services without the gamepad controller, use `roslaunch hybrid_video_recorder hybrid_video_recorder.launch` after sourcing `moma_ws`. Choose one launch method to avoid duplicate recording nodes.

## R3 Controls

| Gesture | Action |
| --- | --- |
| Double-click while idle | Start recording |
| Short-click while recording/paused | Pause/resume aimed video |
| Hold for at least 1.5 seconds | Save and end the session |

The recorder does not start or stop the camera. Ending a session leaves the separately started camera running.

## Configuration and Status

Edit [config/default.yaml](config/default.yaml) for `image_topic`, `recording_root`, `fps`, and writer settings. Default output directory: `/home/shansu/catkin_ws/src/mvs/scripts/recordings/<timestamp>/`.

```bash
rostopic echo /teleop_joy_ctrl/video/status
rostopic echo /teleop_joy_ctrl/video/output_dir
rostopic hz /camera/image_raw
```

The manager provides `start`, `pause`, `resume`, and `stop` Trigger services under `/teleop_joy_ctrl/video/`.

To switch to the previous YOLO-coupled backend:

```bash
roslaunch teleop_joy_ctrl teleop_joy_ctrl.launch \
  start_hybrid_video_manager:=false start_legacy_video_manager:=true
```
