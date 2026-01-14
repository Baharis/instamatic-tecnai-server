# IF YOUR VENV DOES NOT WORK CORRECTLY, A BOILERPLATE LIKE THIS MAY BE REQUIRED
# import sys
# sys.path.insert(0, r'Q:\DanielT\instamatic-tecnai-server\venv\Lib\site-packages')
# BOILERPLATE END

import abc
import atexit
import pickle
import socket
import threading
import time
import unittest

from typing import Type

from instamaticServer.TEMController.simu_microscope import SimuMicroscope
from instamaticServer.utils.config import SimpleNamespace, config, dict_to_namespace
from cam_server import CamServer
from tem_server import DeviceServer, TemServer, listen


_conf_dict = {'a': 1, 'b': {'c': 3, 'd': 4}}
PRECISION_NM = 250
PRECISION_DEG = 0.1
TIMEOUT = 30


class TestConfig(unittest.TestCase):
    def test_namespace(self):
        ns = SimpleNamespace(**_conf_dict)
        self.assertEqual(ns.a, 1)
        self.assertEqual(ns.b, {'c': 3, 'd': 4})

    def test_dict_to_namespace(self):
        ns = dict_to_namespace(_conf_dict)
        self.assertEqual(ns.a, 1)
        self.assertEqual(ns.b, SimpleNamespace(**{'c': 3, 'd': 4}))

    def test_config(self):
        self.assertIn(config.micr_interface, {'tecnai', 'simulate'})
        self.assertIsInstance(config.camera, SimpleNamespace)


class TestSerializers(unittest.TestCase):
    def test_json_serializer(self):
        from instamaticServer.serializer import json_dumper, json_loader
        self.assertEqual(_conf_dict, json_loader(json_dumper(_conf_dict)))

    def test_pickle_serializer(self):
        from instamaticServer.serializer import pickle_dumper, pickle_loader
        self.assertEqual(_conf_dict, pickle_loader(pickle_dumper(_conf_dict)))

    def test_msgpack_serializer(self):
        try:
            from instamaticServer.serializer import msgpack_dumper, msgpack_loader
            self.assertEqual(_conf_dict, msgpack_loader(msgpack_dumper(_conf_dict)))
        except ImportError:
            pass


class TestDeviceServer(unittest.TestCase, metaclass=abc.ABCMeta):
    DeviceServer = None  # type: Type[DeviceServer]
    device_abbr = None   # type: str

    @classmethod
    def setUpClass(cls):
        cls.server = cls.DeviceServer()
        cls.server.start()
        ln = cls.device_abbr + '_listener'
        cls.listener = threading.Thread(target=listen, args=(cls.DeviceServer,), name=ln)
        cls.listener.start()
        cls.threads = [cls.server, cls.listener]
        atexit.register(cls.tearDownClass)

        t0 = time.perf_counter()
        while getattr(cls.server, 'device', None) is None:
            if time.perf_counter() - t0 > 5:
                raise RuntimeError(cls.device_abbr.upper() + ' device did not initialize')
            time.sleep(0.05)

        try:
            cls.const = cls.server.device._tem_constant
        except AttributeError:
            cls.const = None

        host = config.default_settings[cls.device_abbr + '_server_host']
        port = config.default_settings[cls.device_abbr + '_server_port']
        cls.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cls.socket.connect((host, port))
        cls.socket.settimeout(TIMEOUT)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop_event.set()
        while cls.threads:
            thread = cls.threads.pop(0)
            thread.join(timeout=5)
            if thread.is_alive():
                print('Thread %s did not exit' % thread.name)

        if hasattr(cls, 'socket') and cls.socket:
            try:
                cls.socket.close()
            except Exception as e:
                print('Error closing %s socket:' % cls.device_abbr, e)
            finally:
                cls.socket = None

    def send(self, func, args = (), kwargs = None):
        from instamaticServer.serializer import dumper, loader
        from instamaticServer.utils.exceptions import TEMCommunicationError, exception_list
        kwargs = kwargs or {}
        d = {'func_name': func, 'args': args, 'kwargs': kwargs}
        buffer_size = 1024
        if func in ('get_image', 'get_movie', '__gen_next__'):
            buffer_size += 8 * config.camera.dimensions[0] * config.camera.dimensions[1]
        self.socket.sendall(dumper(d))
        response = self.socket.recv(buffer_size)
        if response:
            for _ in range(100):  # warrants all image/movie is collected
                try:
                    status, data = loader(response)
                except (pickle.UnpicklingError, EOFError, ValueError):
                    response += self.socket.recv(buffer_size)
                    time.sleep(0.01)
                else:
                    break
            else:
                status = 500
                data = (None, None)
        else:
            raise RuntimeError('Received empty response when evaluating %s' % d)
        if status == 200:
            return data
        elif status == 500:
            error_code, args = data
            raise exception_list.get(error_code, TEMCommunicationError)(*args)
        else:
            raise ConnectionError('Unknown status code: %s' % status)


class TestTemServer(TestDeviceServer):
    DeviceServer = TemServer
    device_abbr = 'tem'

    def test_20_getHolderType(self):
        r = self.send('getHolderType')
        if not isinstance(self.server.device, SimuMicroscope):
            self.assertIsInstance(r, int)
            self.assertIn(r,list(self.const.StageHolderType.values()))

    def test_21_getStagePosition(self):
        r = self.send('getStagePosition')
        self.assertIsInstance(r, tuple)
        self.assertEqual(len(r), 5)

    def test_22_getStageSpeed(self):
        r = self.send('getStageSpeed')
        self.assertEqual(r, 0.5)

    def test_23_is_goniotool_available(self):
        r = self.send('is_goniotool_available')
        self.assertEqual(r, False)

    def test_24_isAThreadAlive(self):
        r = self.send('isAThreadAlive')
        self.assertEqual(r, False)

    def test_25_isStageMoving(self):
        r = self.send('isStageMoving')
        self.assertEqual(r, False)

    def test_30_setStagePosition(self):
        p = (0, 0, 0, 0, 0)
        self.send('setStagePosition', p)
        r = self.send('getStagePosition')
        self.assertAlmostEqual(r[0], p[0], delta=PRECISION_NM)
        self.assertAlmostEqual(r[1], p[1], delta=PRECISION_NM)
        self.assertAlmostEqual(r[2], p[2], delta=PRECISION_NM)
        self.assertAlmostEqual(r[3], p[3], delta=PRECISION_DEG)
        self.assertAlmostEqual(r[4], p[4], delta=PRECISION_DEG)

    def test_31_setStagePosition(self):
        self.send('setStagePosition', (0, 0, 0, 0, 0))
        self.send('setStagePosition', kwargs={'x': 10000, 'y': 10000})
        r = self.send('getStagePosition')
        self.assertAlmostEqual(r[0], 10000, delta=PRECISION_NM)
        self.assertAlmostEqual(r[1], 10000, delta=PRECISION_NM)
        self.assertAlmostEqual(r[2], 0, delta=PRECISION_NM)
        self.assertAlmostEqual(r[3], 0, delta=PRECISION_DEG)
        self.assertAlmostEqual(r[4], 0, delta=PRECISION_DEG)

    def test_32_setStagePosition(self):
        self.send('setStagePosition', (10000, 10000, 0, 0, 0))
        self.send('getStagePosition')
        self.send('setStagePosition', kwargs={'z': 10000})
        r = self.send('getStagePosition')
        self.assertAlmostEqual(r[2], 10000, delta=PRECISION_NM)
        self.send('setStagePosition', kwargs={'z': 0})
        r = self.send('getStagePosition')
        self.assertAlmostEqual(r[2], 0, delta=PRECISION_NM)
        self.send('setStagePosition', (10000, 10000, 10000, 0, 0))
        r = self.send('getStagePosition')
        self.assertAlmostEqual(r[0], 10000, delta=PRECISION_NM)
        self.assertAlmostEqual(r[1], 10000, delta=PRECISION_NM)
        self.assertAlmostEqual(r[2], 10000, delta=PRECISION_NM)

    def test_33_setStagePosition(self):
        self.send('setStagePosition', (0, 0, 0, 0, 0))
        self.send('setStagePosition', kwargs={'a': 10})
        r = self.send('getStagePosition')
        self.assertAlmostEqual(r[3], 10, delta=PRECISION_DEG)

    def test_35_setStagePosition(self):
        self.send('setStagePosition', (0, 0, 0, 0, 0))
        t0 = time.perf_counter()
        self.send('setStagePosition', kwargs={'x': 5000})
        t1 = time.perf_counter()
        self.send('setStagePosition', kwargs={'x': 0, 'speed': 0.1})
        t2 = time.perf_counter()
        self.send('setStagePosition', kwargs={'x': 5000, 'speed': 0.05})
        t3 = time.perf_counter()
        self.send('setStagePosition', kwargs={'x': 0, 'speed': 0.02})
        t4 = time.perf_counter()
        if not isinstance(self.server.device, SimuMicroscope):
            self.assertLess(t1 - t0, t2 - t1)
            self.assertLess(t2 - t1, t3 - t2)
            self.assertLess(t3 - t2, t4 - t3)

    def test_36_setStagePosition(self):
        self.send('setStagePosition', (0, 0, 0, 0, 0))
        t0 = time.perf_counter()
        self.send('setStagePosition', kwargs={'a': 2})
        t1 = time.perf_counter()
        self.send('setStagePosition', kwargs={'a': 0, 'speed': 0.1})
        t2 = time.perf_counter()
        self.send('setStagePosition', kwargs={'a': 2, 'speed': 0.05})
        t3 = time.perf_counter()
        self.send('setStagePosition', kwargs={'a': 0, 'speed': 0.02})
        t4 = time.perf_counter()
        if not isinstance(self.server.device, SimuMicroscope):
            self.assertLess(t2 - t1, t3 - t2)
            self.assertLess(t1 - t0, t2 - t1)
            self.assertLess(t3 - t2, t4 - t3)

    def test_38_setStagePosition(self):
        self.send('setStagePosition', (0, 0, 0, 0, 0))
        t0 = time.perf_counter()
        self.send('setStagePosition', kwargs={'a': 30, 'wait': False})
        t1 = time.perf_counter()
        time.sleep(0.1)
        self.send('waitForStage')
        t2 = time.perf_counter()
        q = {'a': 0, 'wait': True}
        self.send('setStagePosition', kwargs=q)
        t3 = time.perf_counter()
        self.assertLess(t1 - t0, t2 - t1)
        self.assertLess(t1 - t0, t3 - t2)

    def test_40_setStageA(self):
        p = (0, )
        self.send('setStageA', p)
        r = self.send('getStagePosition')
        self.assertAlmostEqual(r[3], p[0], delta=PRECISION_DEG)

    def test_46_setRotationSpeed(self):
        self.send('setStageA', kwargs={'value': 0})
        t0 = time.perf_counter()
        self.send('setRotationSpeed', (1.0,))
        self.send('setStageA', kwargs={'value': 5})
        t1 = time.perf_counter()
        self.send('setRotationSpeed', (0.1,))
        self.send('setStageA', kwargs={'value': 0})
        t2 = time.perf_counter()
        self.assertLess(t1 - t0, t2 - t1)
        self.send('setRotationSpeed', (0.05,))
        self.send('setStageA', kwargs={'value': 5})
        t3 = time.perf_counter()
        self.assertLess(t2 - t1, t3 - t2)
        self.send('setRotationSpeed', (1.0,))
        self.send('setStageA', kwargs={'value': 0})

    def test_48_setStageA(self):
        self.send('setStageA', (0,))
        t0 = time.perf_counter()
        self.send('setStageA', kwargs={'value': 10, 'wait': False})
        t1 = time.perf_counter()
        time.sleep(0.1)
        self.send('waitForStage', kwargs={'delay': 0.01})
        t2 = time.perf_counter()
        self.send('setStageA', kwargs={'value': 0, 'wait': True})
        t3 = time.perf_counter()
        self.assertLess(t1 - t0, t2 - t1)
        self.assertLess(t1 - t0, t3 - t2)

    def test_50_getGunShift(self):
        self.send('getGunShift')

    def test_51_getHTValue(self):
        self.send('getHTValue')

    def test_52_isBeamBlanked(self):
        self.send('isBeamBlanked')

    def test_53_getBeamAlignShift(self):
        self.send('getBeamAlignShift')

    def test_54_getSpotSize(self):
        self.send('getSpotSize')

    def test_55_getBrightness(self):
        self.send('getBrightness')

    def test_56_getBrightnessValue(self):
        self.send('getBrightnessValue')

    def test_57_getBeamShift(self):
        self.send('getBeamShift')

    def test_58_getBeamTilt(self):
        self.send('getBeamTilt')

    def test_59_getCondensorLensStigmator(self):
        self.send('getCondensorLensStigmator')

    def test_61_getScreenCurrent(self):
        self.send('getScreenCurrent')

    def test_62_isfocusscreenin(self):
        r = self.send('isfocusscreenin')
        self.assertIsInstance(r, bool)

    def test_63_getScreenPosition(self):
        r = self.send('getScreenPosition')
        self.assertIn(r, {'up', 'down', ''})

    def test_64_getDiffFocus(self):
        func_mode = self.send('getFunctionMode')
        self.send('setFunctionMode', ('diff',))
        r = self.send('getDiffFocus')
        self.send('setFunctionMode', (func_mode,))
        self.assertGreater(r, 0)
        self.assertLess(r, 65536)

    def test_65_getDiffFocusValue(self):
        func_mode = self.send('getFunctionMode')
        self.send('setFunctionMode', ('diff',))
        r = self.send('getDiffFocusValue')
        self.send('setFunctionMode', (func_mode,))
        if not isinstance(self.server.device, SimuMicroscope):
            self.assertGreater(r, -1.0)
            self.assertLess(r, 1.0)

    def test_65_getFocus(self):
        r = self.send('getFocus')
        if not isinstance(self.server.device, SimuMicroscope):
            self.assertGreater(r, -1.0)
            self.assertLess(r, 1.0)

    def test_67_FunctionMode(self):
        r = self.send('getFunctionMode')
        self.send('setFunctionMode', (r,))
        self.assertIn(r, ('lowmag', 'mag1', 'samag', 'mag2', 'diff'))

    def test_68_Magnification(self):
        r = self.send('getMagnification')
        self.send('setMagnification', (r,))
        self.assertIsInstance(r, (int, float))

    def test_69_MagnificationIndex(self):
        r = self.send('getMagnificationIndex')
        self.send('setMagnificationIndex', (r,))
        self.assertIsInstance(r, int)

    def test_70_getDarkFieldTilt(self):
        r = self.send('getDarkFieldTilt')
        self.assertIsInstance(r[0], (int, float))
        self.assertIsInstance(r[1], (int, float))

    def test_71_getImageShift1(self):
        r = self.send('getImageShift1')
        self.assertIsInstance(r[0], (int, float))
        self.assertIsInstance(r[1], (int, float))

    def test_72_getImageShift2(self):
        r = self.send('getImageShift2')
        self.assertIsInstance(r[0], (int, float))
        self.assertIsInstance(r[1], (int, float))

    def test_73_getImageBeamShift(self):
        r = self.send('getImageBeamShift')
        self.assertIsInstance(r[0], (int, float))
        self.assertIsInstance(r[1], (int, float))

    def test_74_getDiffShift(self):
        r = self.send('getDiffShift')
        self.assertIsInstance(r[0], (int, float))
        self.assertIsInstance(r[1], (int, float))

    def test_76_getObjectiveLensStigmator(self):
        r = self.send('getObjectiveLensStigmator')
        self.assertIsInstance(r[0], (int, float))
        self.assertIsInstance(r[1], (int, float))

    def test_77_getIntermediateLensStigmator(self):
        r = self.send('getIntermediateLensStigmator')
        self.assertIsInstance(r[0], (int, float))
        self.assertIsInstance(r[1], (int, float))


class TestCamServer(TestDeviceServer):
    DeviceServer = CamServer
    device_abbr = 'cam'

    def test_90_get_binning(self):
        r = self.send('get_binning')
        self.assertIsInstance(r, int)

    def test_91_default_binsize(self):
        r = self.send('get_binning')
        s = self.send('default_binsize')
        self.assertEqual(r, s)

    def test_92_dimensions(self):
        r = self.send('dimensions')
        self.assertIsInstance(r[0], int)

    def test_93_get_camera_dimensions(self):
        r = self.send('get_camera_dimensions')
        s = self.send('dimensions')
        self.assertEqual(r, s)

    def test_94_get_image_dimensions(self):
        r = self.send('get_image_dimensions')
        s = self.send('get_camera_dimensions')
        self.assertEqual(r[0], s[0])
        self.assertEqual(r[1], s[1])

    def test_96_get_image(self):
        r = self.send('get_image')
        s = self.send('get_image_dimensions')
        self.assertEqual(len(r), s[0])

    def test_97_get_image(self):
        r = self.send('get_image')
        s = self.send('get_image_dimensions')
        self.assertEqual(len(r), s[0])

    def test_98_get_movie(self):
        r = self.send('get_movie', (1, ))
        s = self.send('get_image_dimensions')
        self.assertEqual(len(r[0]), s[0])
