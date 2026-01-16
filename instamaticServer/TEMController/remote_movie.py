from typing import Callable


class RemoteMovie:
    """A lazy single-threaded image iterator, can't pass acq to other thread."""
    def __init__(self, get_image: Callable, **kwargs) -> None:
        self._get_image = get_image
        self._kwargs = dict(kwargs)
        self._n_frames = self._kwargs.pop('n_frames')
        self._i = 0
        self._started = False

    def __iter__(self):
        return self

    def __next__(self):
        if self._i >= self._n_frames:
            raise StopIteration
        self._started = True
        self._i += 1
        return self._get_image(**self._kwargs)
