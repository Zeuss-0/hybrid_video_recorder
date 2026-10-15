# hybrid_video_recorder

ROS1 hybrid video recorder designed to protect raw data from detector failures.

## Design

- `raw` and `aimed` are separate ROS processes with separate FFmpeg writers.
- Both workers subscribe continuously to `/camera/image_raw`; pause does not
  reconnect the ROS subscriber.
- The raw worker writes during `RECORDING` and `PAUSED`.
- The aimed worker writes only during `RECORDING`.
- The manager exposes the existing `/teleop_joy_ctrl/video/*` Trigger API, so
  the R3 gesture code does not need to change.
- YOLO is intentionally outside this data-guarantee chain. Its failure cannot
  cancel raw or aimed recording.

The package never starts or stops `camera_stream`. Start the camera as an
independent process before beginning a session:

```bash
source ~/catkin_ws/devel/setup.bash
rosrun mvs camera_stream
```

## Launch

```bash
source ~/test_ws/devel/setup.bash
source ~/catkin_ws/devel/setup.bash
source ~/moma_ws/devel/setup.bash
roslaunch teleop_joy_ctrl teleop_joy_ctrl.launch
```

The hybrid manager is the default backend. To temporarily use the previous
YOLO-coupled manager instead:

```bash
roslaunch teleop_joy_ctrl teleop_joy_ctrl.launch \
  start_hybrid_video_manager:=false \
  start_legacy_video_manager:=true
```

Each recording session writes into one timestamp directory:

```text
<recording_root>/<timestamp>/<timestamp>.mp4
<recording_root>/<timestamp>/aimed_<timestamp>.mp4
```
