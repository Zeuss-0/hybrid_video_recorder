#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""One fault-isolated FFmpeg recorder for either raw or pause-aware video."""

import os
import subprocess
import threading
from queue import Empty, Full, Queue

from cv_bridge import CvBridge, CvBridgeError
import rospy
from sensor_msgs.msg import Image
from std_msgs.msg import String

from hybrid_video_recorder.recording_state import (
    ERROR,
    IDLE,
    PAUSED,
    RECORDING,
    RecordingState,
)
from hybrid_video_recorder.srv import RecordingControl, RecordingControlResponse


class HybridVideoWorker(object):
    def __init__(self):
        self.lock = threading.RLock()
        self.bridge = CvBridge()
        self.state = RecordingState()
        self.role = rospy.get_param("~role", "").strip().lower()
        if self.role not in ("raw", "aimed"):
            raise rospy.ROSInitException("~role must be raw or aimed")

        self.image_topic = rospy.get_param("~image_topic", "/camera/image_raw")
        self.fps = float(rospy.get_param("~fps", 30.0))
        self.first_frame_timeout = float(rospy.get_param("~first_frame_timeout", 10.0))
        self.finalize_timeout = float(rospy.get_param("~writer_finalize_timeout", 20.0))
        self.ffmpeg_preset = rospy.get_param("~ffmpeg_preset", "veryfast")
        self.frame_queue = Queue(maxsize=max(1, int(rospy.get_param("~writer_queue_size", 120))))
        self.first_frame = threading.Event()
        self.writer_stop = threading.Event()
        self.writer_failed = threading.Event()
        self.writer_thread = None
        self.writer = None
        self.session_id = ""
        self.output_dir = ""
        self.output_path = ""
        self.video_size = None
        self.dropped_frames = 0

        self.state_pub = rospy.Publisher("~state", String, queue_size=1, latch=True)
        self.status_pub = rospy.Publisher("~status", String, queue_size=10)
        self.output_pub = rospy.Publisher("~output_path", String, queue_size=1, latch=True)
        self.control_srv = rospy.Service("~control", RecordingControl, self.handle_control)
        self.image_sub = rospy.Subscriber(
            self.image_topic,
            Image,
            self.image_callback,
            queue_size=1,
            buff_size=2 ** 24,
        )
        self.publish_state("节点已启动，持续订阅图像话题=%s" % self.image_topic)

    def publish_state(self, message):
        self.state_pub.publish(String(self.state.value))
        self.status_pub.publish(String("角色=%s 状态=%s %s" % (
            self.role, self.state.value, message)))
        rospy.loginfo("混合录像%s节点: %s", self.role, message)

    def response(self, success, message):
        return RecordingControlResponse(success, message, self.output_path)

    def handle_control(self, request):
        command = request.command.strip().lower()
        if command == "start":
            return self.handle_start(request)
        if command == "pause":
            return self.handle_pause()
        if command == "resume":
            return self.handle_resume()
        if command == "stop":
            return self.handle_stop()
        return self.response(False, "未知录像命令=%s" % request.command)

    def handle_start(self, request):
        session_id = request.session_id.strip()
        output_dir = os.path.abspath(os.path.expanduser(request.output_dir.strip()))
        if not session_id or not output_dir:
            return self.response(False, "开始录像缺少session_id或output_dir")

        with self.lock:
            if not self.state.start():
                return self.response(False, "当前状态=%s，无法开始录像" % self.state.value)
            self.release_writer_locked(force=True)
            self.clear_frame_queue_locked()
            self.session_id = session_id
            self.output_dir = output_dir
            filename = (
                "%s.mp4" % session_id
                if self.role == "raw"
                else "aimed_%s.mp4" % session_id
            )
            self.output_path = os.path.join(output_dir, filename)
            os.makedirs(output_dir, exist_ok=True)
            self.first_frame.clear()
            self.writer_stop.clear()
            self.writer_failed.clear()
            self.video_size = None
            self.dropped_frames = 0
            self.output_pub.publish(String(self.output_path))
            self.publish_state("等待首帧，文件=%s" % self.output_path)

        if not self.first_frame.wait(self.first_frame_timeout):
            with self.lock:
                self.state.value = ERROR
                self.release_writer_locked(force=True)
                self.publish_state("等待首帧超时，话题=%s" % self.image_topic)
            return self.response(False, "等待图像首帧超时")
        return self.response(True, "录像已开始")

    def handle_pause(self):
        with self.lock:
            if not self.state.pause():
                return self.response(False, "当前状态=%s，无法暂停" % self.state.value)
            behavior = "继续写入原始视频" if self.role == "raw" else "停止写入aimed视频"
            self.publish_state("已暂停，%s，图像订阅保持不断开" % behavior)
            return self.response(True, "录像已暂停")

    def handle_resume(self):
        with self.lock:
            if not self.state.resume():
                return self.response(False, "当前状态=%s，无法继续" % self.state.value)
            self.publish_state("已继续写入")
            return self.response(True, "录像已继续")

    def handle_stop(self):
        with self.lock:
            if not self.state.begin_stop():
                return self.response(False, "当前状态=%s，无法结束" % self.state.value)
            self.publish_state("正在封装视频")
            success = self.release_writer_locked(force=False)
            self.state.finish_stop(success)
            suffix = "" if self.dropped_frames == 0 else "，丢帧=%d" % self.dropped_frames
            self.publish_state("录像已结束%s" % suffix)
            return self.response(success, "录像已结束%s" % suffix)

    def should_write(self):
        return self.state.value == RECORDING or (
            self.role == "raw" and self.state.value == PAUSED
        )

    def image_callback(self, message):
        with self.lock:
            if not self.should_write():
                return
        try:
            frame = self.bridge.imgmsg_to_cv2(message, desired_encoding="bgr8")
        except CvBridgeError as exc:
            rospy.logwarn_throttle(2.0, "混合录像%s节点: 图像转换失败=%s", self.role, exc)
            return

        with self.lock:
            if not self.should_write():
                return
            height, width = frame.shape[:2]
            if self.writer is None:
                if not self.start_writer_locked(width, height):
                    return
            elif self.video_size != (width, height):
                self.state.value = ERROR
                self.writer_failed.set()
                self.publish_state("录制中分辨率改变，已停止写入")
                return
            try:
                self.frame_queue.put_nowait(frame.copy())
                self.first_frame.set()
            except Full:
                self.dropped_frames += 1
                rospy.logwarn_throttle(
                    2.0,
                    "混合录像%s节点: 写入队列已满，累计丢帧=%d",
                    self.role,
                    self.dropped_frames,
                )

    def start_writer_locked(self, width, height):
        self.video_size = (width, height)
        command = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", "%dx%d" % self.video_size,
            "-framerate", "%.6f" % self.fps,
            "-i", "pipe:0", "-an", "-c:v", "libx264",
            "-preset", self.ffmpeg_preset,
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            self.output_path,
        ]
        try:
            self.writer = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
            )
        except OSError as exc:
            self.writer = None
            self.state.value = ERROR
            self.publish_state("FFmpeg启动失败=%s" % exc)
            return False
        self.writer_thread = threading.Thread(target=self.writer_loop, daemon=True)
        self.writer_thread.start()
        self.publish_state("开始写入视频=%s" % self.output_path)
        return True

    def writer_loop(self):
        while not self.writer_stop.is_set() or not self.frame_queue.empty():
            try:
                frame = self.frame_queue.get(timeout=0.1)
            except Empty:
                continue
            try:
                if self.writer is None or self.writer.stdin is None:
                    raise OSError("FFmpeg输入不可用")
                self.writer.stdin.write(frame.tobytes())
            except (BrokenPipeError, OSError) as exc:
                self.writer_failed.set()
                self.writer_stop.set()
                rospy.logerr("混合录像%s节点: FFmpeg写入失败=%s", self.role, exc)
            finally:
                self.frame_queue.task_done()

    def release_writer_locked(self, force):
        self.writer_stop.set()
        thread_ok = True
        if self.writer_thread is not None and self.writer_thread.is_alive():
            self.writer_thread.join(timeout=self.finalize_timeout)
            thread_ok = not self.writer_thread.is_alive()
        if not thread_ok and self.writer is not None:
            self.writer.terminate()
            self.writer_thread.join(timeout=1.0)

        writer_ok = True
        if self.writer is not None:
            if self.writer.stdin is not None:
                try:
                    self.writer.stdin.close()
                except (BrokenPipeError, OSError):
                    pass
            try:
                writer_ok = self.writer.wait(timeout=1.0 if force else self.finalize_timeout) == 0
            except subprocess.TimeoutExpired:
                self.writer.terminate()
                try:
                    self.writer.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    self.writer.kill()
                    self.writer.wait(timeout=1.0)
                writer_ok = False
        self.writer = None
        self.writer_thread = None
        self.video_size = None
        self.clear_frame_queue_locked()
        return thread_ok and writer_ok and not self.writer_failed.is_set()

    def clear_frame_queue_locked(self):
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
                self.frame_queue.task_done()
            except Empty:
                break

    def shutdown(self):
        with self.lock:
            self.release_writer_locked(force=True)


def main():
    rospy.init_node("hybrid_video_worker")
    node = HybridVideoWorker()
    rospy.on_shutdown(node.shutdown)
    rospy.spin()


if __name__ == "__main__":
    main()
