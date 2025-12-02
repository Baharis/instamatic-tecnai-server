from __future__ import annotations

import atexit
import logging
import time
from typing import Tuple, Any, Optional, List

from instamaticServer.utils.config import config
from instamaticServer.utils.singleton import Singleton

try:
    import numpy as np
except ImportError:
    np = False


logger = logging.getLogger(__name__)


class SimuCamera(metaclass=Singleton):
    """Simple class that simulates the camera interface and mocks the method calls."""

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

    def __init__(self, name='simulate'):
        """Initialize camera module."""
        self.name = name
        self.load_defaults()
        self.establish_connection()
        logger.info(f'Camera simulate initialized')
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

    def get_image(self, exposure: Optional[float] = None, binsize: int = 1):
        """Image acquisition interface."""
        exposure = exposure or self.default_exposure
        binsize = binsize or self.default_binsize
        t0 = time.perf_counter()
        dx, dy = self.dimensions
        dx, dy = dx // binsize, dy // binsize
        if np:
            img = 256 * np.random.random_sample((dx, dy))
        else:
            import random
            v = list(range(0, 256))
            img = [random.sample(v, dx) for _ in range(dy)]
        while time.perf_counter() - t0 < exposure:
            time.sleep(0.001)
        return img

    def get_image_dimensions(self) -> Tuple[int, int]:
        """Get the binned dimensions reported by the camera."""
        dx, dy = self.dimensions
        return dx // self.default_binsize, dy // self.default_binsize

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
        pass

    def release_connection(self) -> None:
        """Release the connection to the camera."""
        pass


if __name__ == '__main__':
    cam = SimuCamera()
    from IPython import embed

    embed()
