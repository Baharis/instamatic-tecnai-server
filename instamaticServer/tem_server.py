import datetime
import logging
import queue
import socket
import threading
import time
import traceback

from TEMController.microscope import get_microscope
from serializer import dumper, loader
from utils.config import config
from typing import Any, List, Tuple, Type

stop_program_event = threading.Event()

_conf = config()
BUFSIZE = 1024
TIMEOUT = 0.5

logfile = 'tem_server_%s.log' % datetime.datetime.now().strftime('%Y-%m-%d')
logging_fmt = '%(asctime)s %(name)-4s: %(levelname)-8s %(message)s'
logging.basicConfig(level=logging.INFO, filename='tem_server.log', format=logging_fmt)


class DeviceServer(threading.Thread):
    """General microscope / camera (Acquisition) communication server.

    Takes a `name` of the microscope/camera and initializes appropriate device.
    When `TemServer.start` thread method is called, `TemServer.run` starts.
    The server will wait for cmd `requests` to appear in the queue, evaluate
    them in order, and return the result via each client's `response_queue`.
    """

    device_abbr: str
    device_kind: str
    requests: queue.Queue
    responses: queue.Queue
    host: str = 'localhost'
    port: int

    def __init__(self, name=None) -> None:
        super().__init__()
        self._name = name  # self.name is a reserved parameter for threads
        self.logger = logging.getLogger(self.device_abbr + 'S')  # temS/camS server
        self.tem = None
        self.verbose = False

    def run(self) -> None:
        """Start the server thread."""
        self.tem = get_microscope(name=self._name)
        self._name = self.tem.name
        self.logger.info('Initialized %s %s server thread', self.device_kind, self._name)

        while True:
            now = datetime.datetime.now().strftime('%H:%M:%S.%f')
            try:
                cmd = self.requests.get(timeout=TIMEOUT)
            except queue.Empty:
                if stop_program_event.is_set():
                    break
                continue

            func_name = cmd.get('func_name', cmd.get('attr_name'))
            args = cmd.get('args', ())
            kwargs = cmd.get('kwargs', {})

            try:
                ret = self.evaluate(func_name, args, kwargs)
                status = 200
            except Exception as e:
                traceback.print_exc()
                self.logger.exception(e)
                ret = (e.__class__.__name__, e.args)
                status = 500

            self.responses.put((status, ret))
            self.logger.info("%s  |  %s  %s: %s", now, status, func_name, ret)

        self.logger.info('Terminating %s %s server thread', self.device_kind, self._name)

    def evaluate(self, func_name: str, args: list, kwargs: dict) -> Any:
        """Evaluate the function `func_name` on `self.tem` and call it with
        `args` and `kwargs`."""
        self.logger.debug('eval %s %s %s', func_name, args, kwargs)
        f = getattr(self.tem, func_name)
        ret = f(*args, **kwargs)
        return ret


class TemServer(DeviceServer):
    """TEM communcation server."""

    device_abbr: str = 'tem'
    device_kind: str = 'microscope'
    requests = queue.Queue(maxsize=1)
    responses = queue.Queue(maxsize=1)
    host = _conf.default_settings['tem_server_host']
    port = _conf.default_settings['tem_server_port']
    

class CamServer(DeviceServer):
    """FEI Tecnai/Titan Acquisition camera communication server."""

    device_abbr: str = 'cam'
    device_kind: str = 'camera'
    requests = queue.Queue(maxsize=1)
    responses = queue.Queue(maxsize=1)
    host = _conf.default_settings['cam_server_host']
    port = _conf.default_settings['cam_server_port']

    def __init__(self, name=None) -> None:
        super(CamServer, self).__init__(name=name)
        self.logger.setLevel(logging.WARNING)


def handle(conn: socket.socket, server_type: Type[DeviceServer]) -> None:
    """Handle incoming connection, put command on the Queue `q`, which is then
    handled by TEMServer."""
    with conn:
        while True:
            if stop_program_event.is_set():
                break
            
            data = conn.recv(BUFSIZE)
            if not data:
                break

            data = loader(data)
            
            if data == 'exit' or data == 'kill':
                break

            server_type.requests.put(data)
            response = server_type.responses.get()
            conn.send(dumper(response))


def listen(server_type: Type[DeviceServer]) -> None:
    """Listen on a given server host/port and handle incoming instructions"""

    logger = logging.getLogger(server_type.device_abbr + 'L')  # temL/camL listener
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as device_client:
        device_client.bind((server_type.host, server_type.port))
        device_client.settimeout(TIMEOUT)
        device_client.listen(0)
        logger.info('Server listening on %s:%s', server_type.host, server_type.port)
        while True:
            if stop_program_event.is_set():
                break
            try:
                connection, _ = device_client.accept()
                handle(connection, server_type)
            except socket.timeout:
                pass
            except Exception as e:
                logger.exception('Exception when handling connection: %s', e)
        logger.info('Terminating %s listener thread', server_type.device_kind)


def main() -> None:
    """
    Connects to the TEM and starts a server for microscope communication.
    Opens a socket on port {HOST}:{PORT}.

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

    import argparse
    
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument('-t', '--microscope', action='store',
                        help='Override microscope to use.')
    parser.add_argument('-c', '--camera', action='store_true',
                        help='If selected, start separate threads for a camera')

    parser.set_defaults(microscope=None)
    options = parser.parse_args()

    logging.info('Tecnai server starting')

    tem_server = TemServer(name=options.microscope)
    tem_server.start()

    tem_listener = threading.Thread(target=listen, args=(TemServer,))
    tem_listener.start()

    threads = [tem_server, tem_listener]

    if options.camera:
        logging.info('Waiting for the TEM singleton to initialize')
        for _ in range(100):
            if getattr(tem_server, 'tem') is not None:  # wait until TEM initialized
                break
            time.sleep(0.05)
        else:  # necessary check, Error extremely unlikely, TEM typically starts in ms
            raise RuntimeError('Could not start TEM device on server in 5 seconds')

        cam_server = CamServer(name=None)
        cam_server.start()

        cam_listener = threading.Thread(target=listen, args=(CamServer,))
        cam_listener.start()

        threads.extend([cam_server, cam_listener])

    try:
        while not stop_program_event.is_set(): time.sleep(TIMEOUT)
    except KeyboardInterrupt:
        logging.info("Received KeyboardInterrupt, shutting down...")
    finally:
        stop_program_event.set()
        for thread in threads:
            thread.join()
        logging.info('Tecnai server terminating')
        logging.shutdown()


if __name__ == '__main__':
    main()
