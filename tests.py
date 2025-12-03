import pickle
import socket
import threading
import time
import unittest

from instamaticServer.TEMController.simu_microscope import SimuMicroscope
from instamaticServer.utils.config import NS, config, dict_to_namespace
from instamaticServer.tem_server import stop_program_event

_conf_dict = {'a': 1, 'b': {'c': 3, 'd': 4}}
_conf = config()
PRECISION_NM = 250
PRECISION_DEG = 0.1
TIMEOUT = 30


class TestConfig(unittest.TestCase):
    def test_namespace(self):
        ns = NS(**_conf_dict)
        self.assertEqual(ns.a, 1)
        self.assertEqual(ns.b, {'c': 3, 'd': 4})

    def test_dict_to_namespace(self):
        ns = dict_to_namespace(_conf_dict)
        self.assertEqual(ns.a, 1)
        self.assertEqual(ns.b, NS(**{'c': 3, 'd': 4}))

    def test_config(self):
        global _conf
        self.assertIn(_conf.micr_interface, {'tecnai', 'simulate'})
        self.assertIsInstance(_conf.camera, NS)


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


class TestServer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from instamaticServer.tem_server import CamServer, TemServer, listen
        cls.tem_server = TemServer()
        cls.tem_server.start()
        cls.tem_listener = threading.Thread(target=listen, args=(TemServer,), name='tem_listener')
        cls.tem_listener.start()
        cls.threads = [cls.tem_server, cls.tem_listener]

        t0 = time.perf_counter()
        while getattr(cls.tem_server, 'device', None) is None:
            if time.perf_counter() - t0 > 5:
                raise RuntimeError("Server device did not initialize")
            time.sleep(0.05)

        cls.cam_server = CamServer()
        cls.cam_server.start()
        cls.cam_listener = threading.Thread(target=listen, args=(CamServer,), name='cam_listener')
        cls.cam_listener.start()
        cls.threads.extend([cls.cam_server, cls.cam_listener])

        try:
            cls.const = cls.tem_server.device._tem_constant
        except AttributeError:
            cls.const = None

        tem_host = _conf.default_settings['tem_server_host']
        tem_port = _conf.default_settings['tem_server_port']
        cls.socket_tem = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cls.socket_tem.connect((tem_host, tem_port))
        cls.socket_tem.settimeout(TIMEOUT)
        # atexit.register(cls.socket_tem.close)

        cam_host = _conf.default_settings['cam_server_host']
        cam_port = _conf.default_settings['cam_server_port']
        cls.socket_cam = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cls.socket_cam.connect((cam_host, cam_port))
        cls.socket_cam.settimeout(TIMEOUT)
        # atexit.register(cls.socket_cam.close)

    @classmethod
    def tearDownClass(cls):
        stop_program_event.set()
        for thread in cls.threads:
            thread.join(timeout=5)
            if thread.is_alive():
                print('Thread %s did not exit' % thread.name)
        cls.socket_tem.close()

    @staticmethod
    def socket_send(s, func, args = (), kwargs = None):
        from instamaticServer.serializer import dumper, loader
        from instamaticServer.utils.exceptions import TEMCommunicationError, exception_list
        kwargs = kwargs or {}
        d = {'func_name': func, 'args': args, 'kwargs': kwargs}
        buffer_size = 1024
        if func in ('get_image', 'get_movie'):
            buffer_size += 8 * _conf.camera.dimensions[0] * _conf.camera.dimensions[1]
        s.sendall(dumper(d))
        response = s.recv(buffer_size)
        if response:
            for _ in range(10):  # warrants all image/movie is collected
                try:
                    status, data = loader(response)
                except (pickle.UnpicklingError, ValueError, RuntimeError):
                    response += s.recv(buffer_size)
                else:
                    break
        else:
            raise RuntimeError('Received empty response when evaluating %s' % d)
        if status == 200:
            return data
        elif status == 500:
            error_code, args = data
            raise exception_list.get(error_code, TEMCommunicationError)(*args)
        else:
            raise ConnectionError('Unknown status code: %s' % status)

    def tem_send(self, func, args = (), kwargs = None):
        return self.socket_send(self.socket_tem, func, args, kwargs)

    def cam_send(self, func, args = (), kwargs = None):
        return self.socket_send(self.socket_cam, func, args, kwargs)

    def test_20_getHolderType(self):
        r = self.tem_send('getHolderType')
        if not isinstance(self.tem_server.device, SimuMicroscope):
            self.assertIsInstance(r, self.const.StageHolderType)

    def test_21_getStagePosition(self):
        r = self.tem_send('getStagePosition')
        self.assertIsInstance(r, tuple)
        self.assertEqual(len(r), 5)

    def test_22_getStageSpeed(self):
        r = self.tem_send('getStageSpeed')
        self.assertEqual(r, 0.5)

    def test_23_is_goniotool_available(self):
        r = self.tem_send('is_goniotool_available')
        self.assertEqual(r, False)

    def test_24_isAThreadAlive(self):
        r = self.tem_send('isAThreadAlive')
        self.assertEqual(r, False)

    def test_25_isStageMoving(self):
        r = self.tem_send('isStageMoving')
        self.assertEqual(r, False)

    def test_30_setStagePosition(self):
        p = (0, 0, 0, 0, 0)
        self.tem_send('setStagePosition', p)
        r = self.tem_send('getStagePosition')
        self.assertAlmostEqual(r[0], p[0], delta=PRECISION_NM)
        self.assertAlmostEqual(r[1], p[1], delta=PRECISION_NM)
        self.assertAlmostEqual(r[2], p[2], delta=PRECISION_NM)
        self.assertAlmostEqual(r[3], p[3], delta=PRECISION_DEG)
        self.assertAlmostEqual(r[4], p[4], delta=PRECISION_DEG)

    def test_31_setStagePosition(self):
        self.tem_send('setStagePosition', (0, 0, 0, 0, 0))
        self.tem_send('setStagePosition', kwargs={'x': 10000, 'y': 10000})
        r = self.tem_send('getStagePosition')
        self.assertAlmostEqual(r[0], 10000, delta=PRECISION_NM)
        self.assertAlmostEqual(r[1], 10000, delta=PRECISION_NM)
        self.assertAlmostEqual(r[2], 0, delta=PRECISION_NM)
        self.assertAlmostEqual(r[3], 0, delta=PRECISION_DEG)
        self.assertAlmostEqual(r[4], 0, delta=PRECISION_DEG)

    def test_32_setStagePosition(self):
        self.tem_send('setStagePosition', (10000, 10000, 0, 0, 0))
        self.tem_send('setStagePosition', kwargs={'z': 10000})
        r = self.tem_send('getStagePosition')
        self.assertAlmostEqual(r[0], 10000, delta=PRECISION_NM)
        self.assertAlmostEqual(r[1], 10000, delta=PRECISION_NM)
        self.assertAlmostEqual(r[2], 10000, delta=PRECISION_NM)

    def test_33_setStagePosition(self):
        self.tem_send('setStagePosition', (0, 0, 0, 0, 0))
        self.tem_send('setStagePosition', kwargs={'a': 10})
        r = self.tem_send('getStagePosition')
        self.assertAlmostEqual(r[3], 10, delta=PRECISION_DEG)

    def test_35_setStagePosition(self):
        self.tem_send('setStagePosition', (0, 0, 0, 0, 0))
        t0 = time.perf_counter()
        self.tem_send('setStagePosition', kwargs={'x': 1000})
        t1 = time.perf_counter()
        self.tem_send('setStagePosition', kwargs={'x': 0, 'speed': 0.1})
        t2 = time.perf_counter()
        self.tem_send('setStagePosition', kwargs={'x': 1000, 'speed': 0.05})
        t3 = time.perf_counter()
        self.tem_send('setStagePosition', kwargs={'x': 0, 'speed': 0.02})
        t4 = time.perf_counter()
        if not isinstance(self.tem_server.device, SimuMicroscope):
            self.assertLess(t1 - t0, t2 - t1)
            self.assertLess(t2 - t1, t3 - t2)
            self.assertLess(t3 - t2, t4 - t3)

    def test_36_setStagePosition(self):
        self.tem_send('setStagePosition', (0, 0, 0, 0, 0))
        t0 = time.perf_counter()
        self.tem_send('setStagePosition', kwargs={'a': 2})
        t1 = time.perf_counter()
        self.tem_send('setStagePosition', kwargs={'a': 0, 'speed': 0.1})
        t2 = time.perf_counter()
        self.tem_send('setStagePosition', kwargs={'a': 2, 'speed': 0.05})
        t3 = time.perf_counter()
        self.tem_send('setStagePosition', kwargs={'a': 0, 'speed': 0.02})
        t4 = time.perf_counter()
        if not isinstance(self.tem_server.device, SimuMicroscope):
            self.assertLess(t2 - t1, t3 - t2)
            self.assertLess(t1 - t0, t2 - t1)
            self.assertLess(t3 - t2, t4 - t3)

    def test_38_setStagePosition(self):
        self.tem_send('setStagePosition', (0, 0, 0, 0, 0))
        t0 = time.perf_counter()
        self.tem_send('setStagePosition', kwargs={'a': 30, 'wait': False})
        t1 = time.perf_counter()
        self.tem_send('waitForStage', kwargs={'delay': 0.01})
        t2 = time.perf_counter()
        q = {'a': 0, 'wait': True}
        self.tem_send('setStagePosition', kwargs=q)
        t3 = time.perf_counter()
        self.assertLess(t1 - t0, t2 - t1)
        self.assertLess(t1 - t0, t3 - t2)

    def test_40_setStageA(self):
        p = (0, )
        self.tem_send('setStageA', p)
        r = self.tem_send('getStagePosition')
        self.assertAlmostEqual(r[3], p[0], delta=PRECISION_DEG)

    def test_46_setRotationSpeed(self):
        self.tem_send('setStageA', kwargs={'value': 0})
        t0 = time.perf_counter()
        self.tem_send('setRotationSpeed', (1.0, ))
        self.tem_send('setStageA', kwargs={'value': 5})
        t1 = time.perf_counter()
        self.tem_send('setRotationSpeed', (0.1, ))
        self.tem_send('setStageA', kwargs={'value': 0})
        t2 = time.perf_counter()
        self.assertLess(t1 - t0, t2 - t1)
        self.tem_send('setRotationSpeed', (0.05, ))
        self.tem_send('setStageA', kwargs={'value': 5})
        t3 = time.perf_counter()
        self.assertLess(t2 - t1, t3 - t2)
        self.tem_send('setRotationSpeed', (1.0, ))
        self.tem_send('setStageA', kwargs={'value': 0})

    def test_48_setStageA(self):
        self.tem_send('setStageA', (0, ))
        t0 = time.perf_counter()
        self.tem_send('setStageA', kwargs={'value': 10, 'wait': False})
        t1 = time.perf_counter()
        self.tem_send('waitForStage', kwargs={'delay': 0.01})
        t2 = time.perf_counter()
        self.tem_send('setStageA', kwargs={'value': 0, 'wait': True})
        t3 = time.perf_counter()
        self.assertLess(t1 - t0, t2 - t1)
        self.assertLess(t1 - t0, t3 - t2)

    def test_50_getGunShift(self):
        self.tem_send('getGunShift')

    def test_51_getHTValue(self):
        self.tem_send('getHTValue')

    def test_52_isBeamBlanked(self):
        self.tem_send('isBeamBlanked')

    def test_53_getBeamAlignShift(self):
        self.tem_send('getBeamAlignShift')

    def test_54_getSpotSize(self):
        self.tem_send('getSpotSize')

    def test_55_getBrightness(self):
        self.tem_send('getBrightness')

    def test_56_getBrightnessValue(self):
        self.tem_send('getBrightnessValue')

    def test_57_getBeamShift(self):
        self.tem_send('getBeamShift')

    def test_58_getBeamTilt(self):
        self.tem_send('getBeamTilt')

    def test_59_getCondensorLensStigmator(self):
        self.tem_send('getCondensorLensStigmator')

    def test_61_getScreenCurrent(self):
        self.tem_send('getScreenCurrent')

    def test_62_isfocusscreenin(self):
        r = self.tem_send('isfocusscreenin')
        self.assertIsInstance(r, bool)

    def test_63_getScreenPosition(self):
        r = self.tem_send('getScreenPosition')
        self.assertIn(r, {'up', 'down', ''})

    def test_64_getDiffFocus(self):
        func_mode = self.tem_send('getFunctionMode')
        self.tem_send('setFunctionMode', ('diff', ))
        r = self.tem_send('getDiffFocus')
        self.tem_send('setFunctionMode', (func_mode,))
        self.assertGreater(r, 0)
        self.assertLess(r, 65536)

    def test_65_getDiffFocusValue(self):
        func_mode = self.tem_send('getFunctionMode')
        self.tem_send('setFunctionMode', ('diff', ))
        r = self.tem_send('getDiffFocusValue')
        self.tem_send('setFunctionMode', (func_mode, ))
        if not isinstance(self.tem_server.device, SimuMicroscope):
            self.assertGreater(r, -1.0)
            self.assertLess(r, 1.0)

    def test_65_getFocus(self):
        r = self.tem_send('getFocus')
        if not isinstance(self.tem_server.device, SimuMicroscope):
            self.assertGreater(r, -1.0)
            self.assertLess(r, 1.0)

    def test_67_FunctionMode(self):
        r = self.tem_send('getFunctionMode')
        self.tem_send('setFunctionMode', (r, ))
        self.assertIn(r, ('lowmag', 'mag1', 'samag', 'mag2', 'diff'))

    def test_68_Magnification(self):
        r = self.tem_send('getMagnification')
        self.tem_send('setMagnification', (r, ))
        self.assertIsInstance(r, (int, float))

    def test_69_MagnificationIndex(self):
        r = self.tem_send('getMagnificationIndex')
        self.tem_send('setMagnificationIndex', (r, ))
        self.assertIsInstance(r, int)

    def test_70_getDarkFieldTilt(self):
        r = self.tem_send('getDarkFieldTilt')
        self.assertIsInstance(r[0], (int, float))
        self.assertIsInstance(r[1], (int, float))

    def test_71_getImageShift1(self):
        r = self.tem_send('getImageShift1')
        self.assertIsInstance(r[0], (int, float))
        self.assertIsInstance(r[1], (int, float))

    def test_72_getImageShift2(self):
        r = self.tem_send('getImageShift2')
        self.assertIsInstance(r[0], (int, float))
        self.assertIsInstance(r[1], (int, float))

    def test_73_getImageBeamShift(self):
        r = self.tem_send('getImageBeamShift')
        self.assertIsInstance(r[0], (int, float))
        self.assertIsInstance(r[1], (int, float))

    def test_74_getDiffShift(self):
        r = self.tem_send('getDiffShift')
        self.assertIsInstance(r[0], (int, float))
        self.assertIsInstance(r[1], (int, float))

    def test_76_getObjectiveLensStigmator(self):
        r = self.tem_send('getObjectiveLensStigmator')
        self.assertIsInstance(r[0], (int, float))
        self.assertIsInstance(r[1], (int, float))

    def test_77_getIntermediateLensStigmator(self):
        r = self.tem_send('getIntermediateLensStigmator')
        self.assertIsInstance(r[0], (int, float))
        self.assertIsInstance(r[1], (int, float))

    def test_90_get_binning(self):
        r = self.cam_send('get_binning')
        self.assertIsInstance(r, int)

    def test_91_default_binsize(self):
        r = self.cam_send('get_binning')
        s = self.cam_send('default_binsize')
        self.assertEqual(r, s)

    def test_92_dimensions(self):
        r = self.cam_send('dimensions')
        self.assertIsInstance(r[0], int)

    def test_93_get_camera_dimensions(self):
        r = self.cam_send('get_camera_dimensions')
        s = self.cam_send('dimensions')
        self.assertEqual(r, s)

    def test_94_get_image_dimensions(self):
        r = self.cam_send('get_image_dimensions')
        s = self.cam_send('get_camera_dimensions')
        self.assertEqual(r[0], s[0])
        self.assertEqual(r[1], s[1])

    def test_96_get_image(self):
        r = self.cam_send('get_image')
        s = self.cam_send('get_image_dimensions')
        self.assertEqual(len(r), s[0])

    def test_97_get_image(self):
        r = self.cam_send('get_image')
        s = self.cam_send('get_image_dimensions')
        self.assertEqual(len(r), s[0])

    def test_98_get_movie(self):
        r = self.cam_send('get_movie', (1, ))
        s = self.cam_send('get_image_dimensions')
        self.assertEqual(len(r[0]), s[0])
