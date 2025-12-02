from instamaticServer.utils.config import config


_conf = config()
_tem_interfaces = ('simulate', 'tecnai')

__all__ = ['get_microscope', 'get_microscope_class']


def get_microscope_class(interface: str):
    """Grab the tem class with the given 'interface'."""

    if interface == 'simulate':
        from .simu_microscope import SimuMicroscope as TemCls
    elif interface == 'tecnai':
        from .tecnai_microscope import TecnaiMicroscope as TemCls
    else:
        raise ValueError("No such microscope interface: %s" % interface)

    return TemCls


def get_microscope(name: str = None):
    """Return an instance of microscope interface `tecnai` or `simulate`"""

    if name in _tem_interfaces:
        interface = name
    else:
        interface = _conf.micr_interface
        name = _conf.default_settings['microscope']

    cls = get_microscope_class(interface=interface)
    tem = cls(name=name)

    return tem
