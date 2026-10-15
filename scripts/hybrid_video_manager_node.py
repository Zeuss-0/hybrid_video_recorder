#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Expose the existing R3 service API while isolating raw and aimed writers."""

import os
import threading
import time

import rospy
from std_msgs.msg import String
from std_srvs.srv import Trigger, TriggerResponse

from hybrid_video_recorder.recording_state import (
    ERROR,
    IDLE,
    PAUSED,
    RECORDING,
    RecordingState,
)
from hybrid_video_recorder.srv import RecordingControl, RecordingControlRequest


def call_with_timeout(callback, timeout):
    result = {"response": None, "error": None}
    completed = threading.Event()

    def invoke():
        try:
            result["response"] = callback()
        except Exception as exc:
            result["error"] = exc
        finally:
            completed.set()

    worker = threading.Thread(target=invoke, daemon=True)
    worker.start()
    if not completed.wait(timeout):
        return False, None, "服务调用超时"
    if result["error"] is not None:
        return False, None, str(result["error"])
    return True, result["response"], ""


class HybridVideoManager(object):
    def __init__(self):
        self.lock = threading.RLock()
        self.state = RecordingState()
        self.recording_root = os.path.abspath(os.path.expanduser(rospy.get_param(
            "~recording_root", "/home/shansu/catkin_ws/src/mvs/scripts/recordings"
        )))
        self.worker_timeout = float(rospy.get_param("~worker_service_timeout", 30.0))
        self.raw_service_name = rospy.get_param(
            "~raw_control_service", "/hybrid_video_recorder/raw/control"
        )
        self.aimed_service_name = rospy.get_param(
            "~aimed_control_service", "/hybrid_video_recorder/aimed/control"
        )
        self.raw_client = rospy.ServiceProxy(self.raw_service_name, RecordingControl)
        self.aimed_client = rospy.ServiceProxy(self.aimed_service_name, RecordingControl)
        self.raw_started = False
        self.aimed_started = False
        self.session_id = ""
        self.output_dir = ""

        self.state_pub = rospy.Publisher(
            rospy.get_param("~state_topic", "/teleop_joy_ctrl/video/state"),
            String,
            queue_size=1,
            latch=True,
        )
        self.status_pub = rospy.Publisher(
            rospy.get_param("~status_topic", "/teleop_joy_ctrl/video/status"),
            String,
            queue_size=10,
        )
        self.output_pub = rospy.Publisher(
            rospy.get_param("~output_dir_topic", "/teleop_joy_ctrl/video/output_dir"),
            String,
            queue_size=1,
            latch=True,
        )
        self.start_srv = rospy.Service(
            rospy.get_param("~start_service", "/teleop_joy_ctrl/video/start"),
            Trigger,
            self.handle_start,
        )
        self.pause_srv = rospy.Service(
            rospy.get_param("~pause_service", "/teleop_joy_ctrl/video/pause"),
            Trigger,
            self.handle_pause,
        )
        self.resume_srv = rospy.Service(
            rospy.get_param("~resume_service", "/teleop_joy_ctrl/video/resume"),
            Trigger,
            self.handle_resume,
        )
        self.stop_srv = rospy.Service(
            rospy.get_param("~stop_service", "/teleop_joy_ctrl/video/stop"),
            Trigger,
            self.handle_stop,
        )
        self.publish_state("混合解耦录像管理器已启动，YOLO不影响原始数据录制")

    def publish_state(self, message):
        self.state_pub.publish(String(self.state.value))
        self.status_pub.publish(String("状态=%s %s" % (self.state.value, message)))
        rospy.loginfo("混合录像管理器: %s", message)

    def next_session(self):
        base = time.strftime("%Y%m%d_%H%M%S")
        session = base
        suffix = 1
        while os.path.exists(os.path.join(self.recording_root, session)):
            session = "%s_%02d" % (base, suffix)
            suffix += 1
        return session

    def call_worker(self, client, service_name, command):
        try:
            rospy.wait_for_service(service_name, timeout=self.worker_timeout)
        except rospy.ROSException:
            return False, "录像工作节点服务未就绪=%s" % service_name, ""

        request = RecordingControlRequest(
            command=command,
            session_id=self.session_id,
            output_dir=self.output_dir,
        )
        completed, response, error = call_with_timeout(
            lambda: client(request), self.worker_timeout
        )
        if not completed:
            return False, "%s服务%s失败：%s" % (service_name, command, error), ""
        if not response.success:
            return False, response.message, response.output_path
        return True, response.message, response.output_path

    def handle_start(self, _request):
        with self.lock:
            if not self.state.start():
                return TriggerResponse(False, "当前状态=%s，无法开始录像" % self.state.value)
            self.session_id = self.next_session()
            self.output_dir = os.path.join(self.recording_root, self.session_id)
            os.makedirs(self.output_dir, exist_ok=True)
            self.output_pub.publish(String(self.output_dir))
            self.raw_started = False
            self.aimed_started = False

        raw_ok, raw_message, _ = self.call_worker(
            self.raw_client, self.raw_service_name, "start"
        )
        if not raw_ok:
            with self.lock:
                self.state.value = ERROR
                self.publish_state("原始视频启动失败：%s" % raw_message)
            return TriggerResponse(False, raw_message)

        with self.lock:
            self.raw_started = True
        aimed_ok, aimed_message, _ = self.call_worker(
            self.aimed_client, self.aimed_service_name, "start"
        )
        with self.lock:
            self.aimed_started = aimed_ok
            if aimed_ok:
                self.publish_state("原始与aimed录像均已开始，目录=%s" % self.output_dir)
                return TriggerResponse(True, self.output_dir)
            self.publish_state(
                "原始视频已开始；aimed启动失败但不影响数据保底：%s" % aimed_message
            )
            return TriggerResponse(True, "%s；aimed不可用：%s" % (
                self.output_dir, aimed_message))

    def handle_pause(self, _request):
        with self.lock:
            if not self.state.pause():
                return TriggerResponse(False, "当前状态=%s，无法暂停" % self.state.value)
        raw_ok, raw_message, _ = self.call_worker(self.raw_client, self.raw_service_name, "pause")
        aimed_ok = True
        aimed_message = ""
        if self.aimed_started:
            aimed_ok, aimed_message, _ = self.call_worker(
                self.aimed_client, self.aimed_service_name, "pause"
            )
        with self.lock:
            if not raw_ok:
                self.state.value = ERROR
                self.publish_state("原始视频暂停失败：%s" % raw_message)
                return TriggerResponse(False, raw_message)
            if not aimed_ok:
                self.aimed_started = False
                self.publish_state("原始视频持续写入；aimed暂停失败：%s" % aimed_message)
                return TriggerResponse(True, "原始视频持续写入；aimed不可用")
            self.publish_state("已暂停aimed写入，原始视频持续写入")
            return TriggerResponse(True, "已暂停aimed写入，原始视频持续写入")

    def handle_resume(self, _request):
        with self.lock:
            if not self.state.resume():
                return TriggerResponse(False, "当前状态=%s，无法继续" % self.state.value)
        raw_ok, raw_message, _ = self.call_worker(self.raw_client, self.raw_service_name, "resume")
        aimed_ok = True
        aimed_message = ""
        if self.aimed_started:
            aimed_ok, aimed_message, _ = self.call_worker(
                self.aimed_client, self.aimed_service_name, "resume"
            )
        with self.lock:
            if not raw_ok:
                self.state.value = ERROR
                self.publish_state("原始视频继续失败：%s" % raw_message)
                return TriggerResponse(False, raw_message)
            if not aimed_ok:
                self.aimed_started = False
                self.publish_state("原始视频继续写入；aimed继续失败：%s" % aimed_message)
                return TriggerResponse(True, "原始视频已继续；aimed不可用")
            self.publish_state("原始与aimed视频均已继续")
            return TriggerResponse(True, "录像已继续")

    def handle_stop(self, _request):
        with self.lock:
            if not self.state.begin_stop():
                return TriggerResponse(False, "当前状态=%s，无法结束" % self.state.value)
        raw_ok, raw_message, _ = self.call_worker(self.raw_client, self.raw_service_name, "stop")
        aimed_ok = True
        aimed_message = ""
        if self.aimed_started:
            aimed_ok, aimed_message, _ = self.call_worker(
                self.aimed_client, self.aimed_service_name, "stop"
            )
        with self.lock:
            self.raw_started = False
            self.aimed_started = False
            self.state.finish_stop(raw_ok)
            if raw_ok:
                if aimed_ok:
                    self.publish_state("录像已结束，目录=%s" % self.output_dir)
                    return TriggerResponse(True, self.output_dir)
                self.publish_state("原始视频已保存；aimed封装失败：%s" % aimed_message)
                return TriggerResponse(True, "%s；aimed封装失败" % self.output_dir)
            self.publish_state("原始视频封装失败：%s" % raw_message)
            return TriggerResponse(False, raw_message)

    def shutdown(self):
        with self.lock:
            active = self.state.value in (RECORDING, PAUSED, ERROR)
        if active:
            self.handle_stop(None)


def main():
    rospy.init_node("hybrid_video_manager")
    node = HybridVideoManager()
    rospy.on_shutdown(node.shutdown)
    rospy.spin()


if __name__ == "__main__":
    main()
