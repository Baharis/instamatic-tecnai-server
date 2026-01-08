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
    """A wrapper that makes the movie thread into a generator"""
    def __init__(self, get_image: Callable, **kwargs) -> None:
        self.thread = MovieThread(get_image, **kwargs)

    def next(self):
        if not self.thread.is_alive():
            self.thread.start()
        image = self.thread.queue.get()
        if image is None:
            if self.thread.exception:
                raise self.thread.exception
            raise StopIteration
        return image
