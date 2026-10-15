IDLE = "IDLE"
RECORDING = "RECORDING"
PAUSED = "PAUSED"
STOPPING = "STOPPING"
ERROR = "ERROR"


class RecordingState(object):
    def __init__(self):
        self.value = IDLE

    def start(self):
        if self.value not in (IDLE, ERROR):
            return False
        self.value = RECORDING
        return True

    def pause(self):
        if self.value != RECORDING:
            return False
        self.value = PAUSED
        return True

    def resume(self):
        if self.value != PAUSED:
            return False
        self.value = RECORDING
        return True

    def begin_stop(self):
        if self.value not in (RECORDING, PAUSED, ERROR):
            return False
        self.value = STOPPING
        return True

    def finish_stop(self, success):
        self.value = IDLE if success else ERROR
