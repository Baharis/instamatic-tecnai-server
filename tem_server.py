# BOILERPLATE TO MAKE THINGS WORK WITH THE VENV ISSUE
import sys
sys.path.insert(0, r'Q:\DanielT\instamatic-tecnai-server\venv\Lib\site-packages')
# BOILERPLATE END

import argparse
import datetime
import inspect
import logging
import queue
import socket
import sys
import threading
import time
import traceback
import uuid

from typing import Any, Type, Callable


from instamaticServer.TEMController.microscope import get_microscope
from instamaticServer.serializer import dumper, loader
from instamaticServer.utils.config import config


logging.addLevelName(15, "EVAL")
_conf = config()
_generators = {}
BUFSIZE = 1024
TIMEOUT = 0.5


def log_eval(logger, status, func_name, args, kwargs, ret):
    if logger.isEnabledFor(15):
        args_list = [repr(a) for a in args]
        args_list += ['%s=%r' % (k, v) for k, v in kwargs.items()]
        args_str = ', '.join(args_list)
        logger.log(15, '%s | %s(%s): %s', status, func_name, args_str, ret)


class DeviceServer(threading.Thread):
    """General microscope / camera (Acquisition) communication server.

    Takes a `name` of the microscope/camera and initializes appropriate device.
    When `TemServer.start` thread method is called, `TemServer.run` starts.
    The server will wait for cmd `requests` to appear in the queue, evaluate
    them in order, and return the result via each client's `response_queue`.
    """

    device_abbr = None    # type: str
    device_kind = None    # type: str
    device_getter = None  # type: Callable
    requests = None       # type: queue.Queue   
    responses = None      # type: queue.Queue
    stop_event = None     # type: threading.Event
    host = 'localhost'    # type: str
    port = None           # type: int

    def __init__(self, name = None) -> None:
        super().__init__(name=self.device_kind + '_server')
        self.interface_name = name
        self.logger = logging.getLogger(self.device_abbr)  # temS/camS server
        self.device = None
        self.verbose = False

    def run(self) -> None:
        """Start the server thread."""
        self.device = self.device_getter(name=self.interface_name)
        self.device.get_attrs = self.get_attrs
        self.logger.info('Initialized %s %s server thread', self.device_kind, self.device.name)

        while True:
            try:
                cmd = self.requests.get(timeout=TIMEOUT)
            except queue.Empty:
                if self.stop_event.is_set():
                    break
                continue

            func_name = cmd.get('func_name', cmd.get('attr_name'))
            args = cmd.get('args', ())
            kwargs = cmd.get('kwargs', {})

            try:
                ret = self.evaluate(func_name, args, kwargs)
                status = 200
                if inspect.isgenerator(ret):
                    gen_id = uuid.uuid4().hex
                    _generators[gen_id] = ret
                    ret = {'__generator__': gen_id}
            except Exception as e:
                traceback.print_exc()
                self.logger.exception(e)
                ret = (e.__class__.__name__, e.args)
                status = 500

            self.responses.put((status, ret))
            log_eval(self.logger, status, func_name, args, kwargs, ret)

        self.logger.info('Terminating %s %s server thread', self.device_kind, self.device.name)

    def evaluate(self, func_name: str, args: list, kwargs: dict) -> Any:
        """Eval function `func_name` on `self.device` with `args` & `kwargs`."""
        self.logger.debug('evaluate(func_name=%s, args=%s, kwargs=%s)', func_name, args, kwargs)

        if func_name == '__gen_next__':
            gen = _generators[kwargs['id']]
            try:
                return next(gen)
            except StopIteration:
                del _generators[kwargs['id']]
                return

        if func_name == "__gen_close__":
            _generators.pop(kwargs['id'], None)
            return

        f = getattr(self.device, func_name)
        return f(*args, **kwargs) if callable(f) else f

    def get_attrs(self):
        """Get attributes from cam object to update __dict__ on client side."""
        attrs = {}
        for item in dir(self.device):
            if item.startswith('_'):
                continue
            obj = getattr(self.device, item)
            if not callable(obj):
                attrs[item] = type(obj)

        return attrs


class TemServer(DeviceServer):
    """TEM communcation server."""

    device_abbr = 'tem'
    device_kind = 'microscope'
    device_getter = staticmethod(get_microscope)
    requests = queue.Queue(maxsize=1)
    responses = queue.Queue(maxsize=1)
    stop_event = threading.Event()
    host = _conf.default_settings['tem_server_host']
    port = _conf.default_settings['tem_server_port']
    

def handle(conn: socket.socket, server_type: Type[DeviceServer]) -> None:
    """Handle incoming connection, put command on the Queue `q`, which is then
    handled by TEMServer."""
    with conn:
        conn.settimeout(TIMEOUT)
        while True:
            if server_type.stop_event.is_set():
                break

            try:
                data = conn.recv(BUFSIZE)
            except socket.timeout:
                continue

            if not data:
                break

            data = loader(data)

            if data == 'exit' or data == 'kill':
                break

            server_type.requests.put(data)
            response = server_type.responses.get()
            serialized = dumper(response)
            conn.sendall(serialized)


def listen(server_type: Type[DeviceServer]) -> None:
    """Listen on a given server host/port and handle incoming instructions"""

    logger = logging.getLogger(server_type.device_abbr)  # tem/cam listener
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as device_client:
        device_client.bind((server_type.host, server_type.port))
        device_client.settimeout(TIMEOUT)
        device_client.listen(1)
        logger.info('Server listening on %s:%s', server_type.host, server_type.port)
        while True:
            if server_type.stop_event.is_set():
                break
            try:
                connection, _ = device_client.accept()
                handle(connection, server_type)
            except socket.timeout:
                pass
            except Exception as e:
                logger.exception('Exception when handling connection: %s', e)
        logger.info('Terminating %s listener thread', server_type.device_kind)


class MicrosecondFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        t = datetime.datetime.fromtimestamp(record.created)
        return t.strftime(datefmt) if datefmt else t.strftime("%H:%M:%S.%f")


def setup_logging(device_abbr='tem') -> logging.Logger:
    logger = logging.getLogger(device_abbr)
    logger.setLevel(15)

    logfile = '%s_server_%s.log' % (device_abbr, datetime.datetime.now().strftime('%Y-%m-%d'))
    fh = logging.FileHandler(logfile)
    sh = logging.StreamHandler(sys.stdout)

    fmt = MicrosecondFormatter('%(asctime)s %(name)-3s: %(levelname)-8s %(message)s')
    fh.setFormatter(fmt)
    sh.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(sh)

    logger.propagate = False
    return logger


def main() -> None:
    """
    Connects to the TEM and starts a server for microscope communication.
    Opens a socket on port {TemServer.host}:{TemServer.port}.

    This program initializes a connection to the TEM as defined in the config.
    The purpose of this program is to isolate the microscope connection in
    a separate process for improved stability of the interface in case
    instamatic crashes or is started and stopped frequently.
    For running the GUI, the temserver is required.
    Another reason is that it allows for remote connections from different PCs.
    The connection goes over a TCP socket.

    The host and port are defined in `config/settings.yaml`.

    The data sent over the socket is a serialized dictionary with the following:

    - `func_name`: Name of the function to call (str)
    - `args`: (Optional) List of arguments for the function (list)
    - `kwargs`: (Optiona) Dictionary of keyword arguments for the function (dict)

    The response is returned as a serialized object.
    """
    
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument('-t', '--microscope', action='store',
                        help='Override microscope to use.')
    parser.set_defaults(microscope=None)
    options = parser.parse_args()

    logger = setup_logging(device_abbr='tem')
    logger.info('Tecnai microscope server starting')

    tem_server = TemServer(name=options.microscope)
    tem_server.start()

    tem_listener = threading.Thread(target=listen, args=(TemServer,), name='tem_listener')
    tem_listener.start()

    try:
        while not TemServer.stop_event.is_set(): time.sleep(TIMEOUT)
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt, shutting down...")
    finally:
        TemServer.stop_event.set()
        tem_server.join()
        tem_listener.join()
        logger.info('Tecnai microscope server terminating')
        logging.shutdown()


if __name__ == '__main__':
    main()
