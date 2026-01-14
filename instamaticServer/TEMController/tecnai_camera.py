import atexit
from functools import partial

import comtypes.client
import logging
from typing import Any, Generator, List, Optional, Tuple

from instamaticServer.TEMController.remote_movie import RemoteMovie
from instamaticServer.utils.config import config
from instamaticServer.utils.singleton import Singleton

try:
    import numpy as np
except ImportError:
    np = False


logger = logging.getLogger('cam')


class TecnaiCamera(metaclass=Singleton):
    """Interfaces any camera on an FEI Tecnai/Titan microscope."""

    streamable = True

    # Set by `load_defaults`
    camera_rotation_vs_stage_xy = None # type: float
    default_binsize = None             # type: int
    default_exposure = None            # type: float
    dimensions = None                  # type: Tuple[int, int]
    interface = None                   # type: str
    possible_binsizes = None           # type: List[int]
    stretch_amplitude = None           # type: float
    stretch_azimuth = None             # type: float

    def __init__(self, name='tecnai'):
        """Initialize camera module."""
        comtypes.CoInitialize()
        logger.info('FEI Scripting initializing...')
        self._tem = comtypes.client.CreateObject('TEMScripting.Instrument', comtypes.CLSCTX_ALL)
        self.name = name
        self.load_defaults()
        self._acq, self._cam = self.establish_connection()
        logger.info('Camera Tecnai connection established')
        atexit.register(self.release_connection)

    def __enter__(self):
        self.establish_connection()
        return self

    def __exit__(self, kind, value, traceback) -> None:
        self.release_connection()

    def get_binning(self) -> int:
        return self.default_binsize

    def get_camera_dimensions(self) -> Tuple[int, int]:
        return self.dimensions

    def get_name(self) -> str:
        return self.name

    def load_defaults(self) -> None:
        for key, val in config.camera.__dict__.items():
            setattr(self, key, val)

    def get_image(self, exposure: Optional[float] = None, binsize: Optional[int] = None):
        """Image acquisition interface."""
        self._cam.AcqParams.ExposureTime = exposure or self.default_exposure
        self._cam.AcqParams.Binning = binsize or self.default_binsize
        img = self._acq.AcquireImages()[0]
        sa = img.AsSafeArray
        if np:
            return np.stack(sa).T
        return [[sa[r, c] for c in range(img.Height)] for r in range(img.Width)]
        # try [[sa.GetElement([r, c]) or similar if direct indexing does not work...

    def get_image_dimensions(self) -> Tuple[int, int]:
        """Get the binned dimensions of the camera."""
        dx, dy = self.dimensions
        return dx // self.default_binsize, dy // self.default_binsize

    def get_movie(
            self,
            n_frames: int,
            exposure: Optional[float] = None,
            binsize: Optional[int] = None,
    ) -> Generator:
        """Yield n_frames images each collected using subsequent get_image"""
        get_image = partial(self.get_image, self)
        yield from RemoteMovie(get_image, n_frames=n_frames, exposure=exposure, binsize=binsize)

    def establish_connection(self) -> Tuple[Any, Any]:
        """Establish connection to the camera."""
        acq = self._tem.Acquisition
        acq.RemoveAllAcqDevices()
        cam = acq.Cameras[0]
        cam.AcqParams.ImageCorrection = 1  # bias and gain corr (0=off, 1=on)
        cam.AcqParams.ImageSize = 0  # sub area centered (0=full, 1=half, 2=quarter)
        acq.AddAcqDeviceByName(cam.Info.Name)
        return acq, cam

    def release_connection(self) -> None:
        """Release the connection to the camera."""
        pass


if __name__ == '__main__':
    cam = TecnaiCamera()
    from IPython import embed

    embed()
