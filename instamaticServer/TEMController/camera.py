from instamaticServer.utils.config import config


_conf = config()
_cam_interfaces = ('simulate', 'tecnai')

__all__ = ['get_camera', 'get_camera_class']


def get_camera_class(interface: str):
    """Grab the cam class with the given 'interface'."""

    if interface == 'simulate':
        from .simu_camera import SimuCamera as CamCls
    elif interface == 'tecnai':
        from .tecnai_microscope import TecnaiMicroscope as CamCls
    else:
        raise ValueError("No such microscope interface: %s" % interface)

    return CamCls


def get_camera(name: str = None):
    """Return an instance of camera interface `tecnai` or `simulate`"""

    if name in _cam_interfaces:
        interface = name
    else:
        interface = _conf.camera.interface
        name = _conf.default_settings['microscope']

    cls = get_camera_class(interface=interface)
    tem = cls(name=name)

    return tem



