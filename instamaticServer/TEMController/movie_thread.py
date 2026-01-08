import queue
import threading
from typing import Any, Callable, Dict


class MovieThread(threading.Thread):
    """Collects movie images and keeps them in a thread-safe queue."""

    def __init__(self, get_image: Callable, **kwargs) -> None:
        super().__init__()
        self.daemon = True
        self._get_image = get_image
        self._kwargs: Dict[str, Any] = dict(kwargs)
        self._n_frames = self._kwargs.pop('n_frames')
        self.exception = None
        self.queue = queue.Queue()

    def run(self):
        try:
            for _ in range(self._n_frames):
                self.queue.put(self._get_image(**self._kwargs))
        except Exception as e:
            self.exception = e
        finally:
            self.queue.put(None)


class RemoteMovie:
    """A lazy single-threaded image iterator, can't pass acq to other thread."""
    def __init__(self, get_image: Callable, **kwargs) -> None:
        self._get_image = get_image
        self._kwargs: Dict[str, Any] = dict(kwargs)
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
