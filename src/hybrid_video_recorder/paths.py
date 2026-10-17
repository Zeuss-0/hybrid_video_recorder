"""Resolve the recording directory without a machine-specific default."""

import os

ENV_RECORDING_ROOT = "HYBRID_VIDEO_RECORDING_ROOT"
DEFAULT_RECORDINGS_DIRNAME = "recordings"


def resolve_recording_root(param_value, env_value, package_path):
    """Return an absolute recording directory.

    Precedence is the non-empty ROS parameter, then the environment value,
    then ``<package_path>/recordings``. ``~`` is expanded. Relative paths
    are joined to ``package_path`` so the result does not depend on the
    process working directory.
    """
    configured = _clean(param_value)
    if not configured:
        configured = _clean(env_value)
    if not configured:
        configured = DEFAULT_RECORDINGS_DIRNAME

    expanded = os.path.expanduser(configured)
    if not os.path.isabs(expanded):
        if not package_path:
            raise ValueError("package_path is required for a relative recording_root")
        expanded = os.path.join(package_path, expanded)
    return os.path.abspath(expanded)


def package_directory():
    """Return the hybrid_video_recorder directory from the ROS package index."""
    try:
        import rospkg
        return rospkg.RosPack().get_path("hybrid_video_recorder")
    except Exception:
        return os.path.abspath(os.path.join(
            os.path.dirname(__file__), os.pardir, os.pardir
        ))


def _clean(value):
    if value is None:
        return ""
    return str(value).strip()
