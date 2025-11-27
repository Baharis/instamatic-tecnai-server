from __future__ import annotations

import atexit
import logging
from typing import Tuple, Any, Optional, List

from tecnai_microscope import Singleton, TecnaiMicroscope
from utils.config import config

try:
    import numpy as np
except ImportError:
    np = False


logger = logging.getLogger(__name__)


class TecnaiCamera(metaclass=Singleton):
    """Interfaces any camera on an FEI Tecnai/Titan microscope."""

    streamable = True

    # Set by `load_defaults`
    camera_rotation_vs_stage_xy: float
    default_binsize: int
    default_exposure: float
    dimensions: Tuple[int, int]
    interface: str
    possible_binsizes: List[int]
    stretch_amplitude: float
    stretch_azimuth: float

    def __init__(self, name='tecnai'):
        """Initialize camera module."""
        self.name = name
        self.load_defaults()
        self.acq, self.cam = self.establish_connection()
        logger.info(f'Camera Tecnai initialized')
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
        _conf = config()
        for key, val in _conf.camera.__dict__.items():
            setattr(self, key, val)

    def get_image(self, exposure: Optional[float] = None, binning: int = 1):
        """Image acquisition interface."""
        self.cam.AcqParams.ExposureTime = exposure or self.default_exposure
        self.cam.AcqParams.Binning = binning
        img = self.acq.AcquireImages()[0]
        sa = img.AsSafeArray
        if np:
            return np.stack(sa).T
        return [[sa[r, c] for c in range(img.Height)] for r in range(img.Width)]
        # try [[sa.GetElement([r, c]) or similar if direct indexing does not work...

    def get_image_dimensions(self) -> Tuple[int, int]:
        """Get the binned dimensions reported by the camera."""
        return self.cam.ImageSize

    def get_movie(
            self,
            n_frames: int,
            exposure: Optional[float] = None,
            binsize: Optional[int] = None,
    ):
        """Unfortunately not designed to work with generators, as a server..."""
        return [self.get_image(exposure, binsize) for _ in range(n_frames)]

    def establish_connection(self) -> Tuple[Any, Any]:
        """Establish connection to the camera."""
        acq = TecnaiMicroscope()._tem.Acquisition()
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
