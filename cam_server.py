# BOILERPLATE TO MAKE THINGS WORK WITH THE VENV ISSUE
import sys
sys.path.insert(0, r'Q:\DanielT\instamatic-tecnai-server\venv\Lib\site-packages')
# BOILERPLATE END

import argparse
import logging
import queue
import sys
import threading
import time

from instamaticServer.TEMController.camera import get_camera
from tem_server import DeviceServer, _conf, listen, setup_logging


BUFSIZE = 1024
TIMEOUT = 0.5


class CamServer(DeviceServer):
    """FEI Tecnai/Titan Acquisition camera communication server."""

    device_abbr = 'cam'
    device_kind = 'camera'
    device_getter = staticmethod(get_camera)
    requests = queue.Queue(maxsize=1)
    responses = queue.Queue(maxsize=1)
    stop_event = threading.Event()
    host = _conf.default_settings['cam_server_host']
    port = _conf.default_settings['cam_server_port']

    def __init__(self, name=None) -> None:
        super(CamServer, self).__init__(name=name)
        self.logger.setLevel(logging.INFO)


def main() -> None:
    """
    Connects to the TEM and starts a server for camera communication.
    Opens a socket on port {CamServer.host}:{CamServer.port}.

    This program initializes a connection to the TEM as defined in the config.
    The purpose of this program is to isolate the camera connection in
    a separate process for improved stability of the interface in case
    instamatic crashes or is started and stopped frequently.
    For running the GUI, the cam server is required.
    Another reason is that it allows for remote connections from different PCs.
    The connection goes over a TCP socket.

    The host and port are defined in `config/settings.yaml`.

    The data sent over the socket is a serialized dictionary with the following:

    - `attr_name`: Name of the function to call (str)
    - `args`: (Optional) List of arguments for the function (list)
    - `kwargs`: (Optiona) Dictionary of keyword arguments for the function (dict)

    The response is returned as a serialized object.
    """

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument('-c', '--camera', action='store',
                        help='Override camera to use.')
    parser.set_defaults(camera=None)
    options = parser.parse_args()

    logger = setup_logging(device_abbr='cam')
    logger.info('Titan camera server starting')

    cam_server = CamServer(name=options.camera)
    cam_server.start()

    cam_listener = threading.Thread(target=listen, args=(CamServer,), name='cam_listener')
    cam_listener.start()

    try:
        while not CamServer.stop_event.is_set(): time.sleep(TIMEOUT)
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt, shutting down...")
    finally:
        CamServer.stop_event.set()
        cam_server.join()
        cam_listener.join()
        logger.info('Titan camera server terminating')
        logging.shutdown()


if __name__ == '__main__':
    main()
