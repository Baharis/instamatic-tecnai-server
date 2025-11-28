import atexit
import socket
import threading
import time
import unittest
from typing import Any, Dict

from instamaticServer.utils.config import NS, config, dict_to_namespace

_conf_dict = {'a': 1, 'b': {'c': 3, 'd': 4}}
_conf = config()
PRECISION_NM = 250
PRECISION_DEG = 0.1


class TestConfig(unittest.TestCase):
    def test_namespace(self):
        ns = NS(_conf_dict)
        self.assertEqual(ns.a, 1)
        self.assertEqual(ns.b, {'c': 3, 'd': 4})

    def test_dict_to_namespace(self):
        ns = dict_to_namespace(_conf_dict)
        self.assertEqual(ns.a, 1)
        self.assertEqual(ns.b, NS({'c': 3, 'd': 4}))

    def test_config(self):
        global _conf
        self.assertIn(_conf.micr_interface, {'tecnai', 'simulate'})
        self.assertIsInstance(_conf.camera, NS)


class TestSerializers(unittest.TestCase):

    def test_json_serializer(self):
        from instamaticServer.serializer import json_dumper, json_loader
        self.assertEqual(_conf, json_dumper(json_loader(_conf)))

    def test_pickle_serializer(self):
        from instamaticServer.serializer import pickle_dumper, pickle_loader
        self.assertEqual(_conf, pickle_dumper(pickle_loader(_conf)))

    def test_msgpack_serializer(self):
        from instamaticServer.serializer import msgpack_dumper, msgpack_loader
        self.assertEqual(_conf, msgpack_dumper(msgpack_loader(_conf)))


class TestServer(unittest.TestCase):
    def test_00_init_tem_server(self):
        from instamaticServer.tem_server import TemServer, listen
        self.tem_server = TemServer()
        self.tem_server.start()
        self.tem_listener = threading.Thread(target=listen, args=(TemServer,))
        self.tem_listener.start()
        self.threads = [self.tem_server, self.tem_listener]
        for _ in range(100):
            if getattr(self.tem_server, 'device') is not None:
                break
            time.sleep(0.05)
        else:
            raise RuntimeError('Could not start TEM device on server in 5 seconds')
        self.const = self.tem_server.device._tem_constant

    def test_01_client_tem_connect(self):
        host = _conf.default_settings['tem_server_host']
        port = _conf.default_settings['tem_server_port']
        self.socket_tem = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket_tem.connect((host, port))
        atexit.register(self.socket_tem.close)

    @staticmethod
    def socket_send(socket, d):
        from instamaticServer.serializer import dumper, loader
        from instamaticServer.utils.exceptions import TEMCommunicationError, exception_list
        if d.get('args', None) is None:
            d['args'] = ()
        if d.get('kwargs', None) is None:
            d['kwargs'] = {}
        socket.send(dumper(d))
        response = socket.recv(1024)
        if response:
            status, data = loader(response)
        else:
            raise RuntimeError(f'Received empty response when evaluating {d}')
        if status == 200:
            return data
        elif status == 500:
            error_code, args = data
            raise exception_list.get(error_code, TEMCommunicationError)(*args)
        else:
            raise ConnectionError(f'Unknown status code: {status}')

    def tem_send(self, d: Dict[str, Any]):
        return self.socket_send(self.socket_tem, d)

    def test_20_getHolderType(self):
        r = self.tem_send({'func_name': 'getHolderType'})
        self.assertIsInstance(r, self.const.StageHolderType)

    def test_21_getStagePosition(self):
        r = self.tem_send({'func_name': 'getStagePosition'})
        self.assertIsInstance(r, tuple)
        self.assertEqual(len(r), 5)

    def test_22_getStageSpeed(self):
        r = self.tem_send({'func_name': 'getStageSpeed'})
        self.assertEqual(r, 0.5)

    def test_23_is_goniotool_available(self):
        r = self.tem_send({'func_name': 'is_goniotool_available'})
        self.assertEqual(r, False)

    def test_24_isAThreadAlive(self):
        r = self.tem_send({'func_name': 'isAThreadAlive'})
        self.assertEqual(r, False)

    def test_25_isStageMoving(self):
        r = self.tem_send({'func_name': 'isStageMoving'})
        self.assertEqual(r, False)

    def test_30_setStagePosition(self):
        p = (0, 0, 0, 0, 0)
        self.tem_send({'func_name': 'setStagePosition', 'args': p})
        r = self.tem_send({'func_name': 'getStagePosition'})
        self.assertAlmostEqual(r[0], p[0], delta=PRECISION_NM)
        self.assertAlmostEqual(r[1], p[1], delta=PRECISION_NM)
        self.assertAlmostEqual(r[2], p[2], delta=PRECISION_NM)
        self.assertAlmostEqual(r[3], p[3], delta=PRECISION_DEG)
        self.assertAlmostEqual(r[4], p[4], delta=PRECISION_DEG)

    def test_31_setStagePosition(self):
        p = {'x': 10_000, 'y': 10_000}
        self.tem_send({'func_name': 'setStagePosition', 'kwargs': p})
        r = self.tem_send({'func_name': 'getStagePosition'})
        self.assertAlmostEqual(r[0], 10_000, delta=PRECISION_NM)
        self.assertAlmostEqual(r[1], 10_000, delta=PRECISION_NM)
        self.assertAlmostEqual(r[2], 0, delta=PRECISION_NM)
        self.assertAlmostEqual(r[3], 0, delta=PRECISION_DEG)
        self.assertAlmostEqual(r[4], 0, delta=PRECISION_DEG)

    def test_32_setStagePosition(self):
        p = {'z': 10_000}
        self.tem_send({'func_name': 'setStagePosition', 'kwargs': p})
        r = self.tem_send({'func_name': 'getStagePosition'})
        self.assertAlmostEqual(r[0], 10_000, delta=PRECISION_NM)
        self.assertAlmostEqual(r[1], 10_000, delta=PRECISION_NM)
        self.assertAlmostEqual(r[2], 10_000, delta=PRECISION_NM)

    def test_33_setStagePosition(self):
        self.tem_send({'func_name': 'setStagePosition', 'args': (0, 0, 0, 0, 0)})
        p = {'a': 10}
        self.tem_send({'func_name': 'setStagePosition', 'kwargs': p})
        r = self.tem_send({'func_name': 'getStagePosition'})
        self.assertAlmostEqual(r[3], 10, delta=PRECISION_DEG)

    def test_35_setStagePosition(self):
        d = {'func_name': 'setStagePosition'}
        self.tem_send({**d, 'args': (0, 0, 0, 0, 0)})
        t0 = time.perf_counter()
        self.tem_send({**d, 'kwargs': {'x': 10_000}})
        t1 = time.perf_counter()
        self.tem_send({**d, 'kwargs': {'x': 0, 'speed': 0.1}})
        t2 = time.perf_counter()
        self.assertLess(t1 - t0, t2 - t1)
        self.tem_send({**d, 'kwargs': {'x': 10_000, 'speed': 0.05}})
        t3 = time.perf_counter()
        self.assertLess(t2 - t1, t3 - t2)
        self.tem_send({**d, 'kwargs': {'x': 0, 'speed': 0.02}})
        t4 = time.perf_counter()
        self.assertLess(t3 - t2, t4 - t3)

    def test_36_setStagePosition(self):
        d = {'func_name': 'setStagePosition'}
        self.tem_send({**d, 'args': (0, 0, 0, 0, 0)})
        t0 = time.perf_counter()
        self.tem_send({**d, 'kwargs': {'a': 5}})
        t1 = time.perf_counter()
        self.tem_send({**d, 'kwargs': {'a': 0, 'speed': 0.1}})
        t2 = time.perf_counter()
        self.assertLess(t1 - t0, t2 - t1)
        self.tem_send({**d, 'kwargs': {'a': 5, 'speed': 0.05}})
        t3 = time.perf_counter()
        self.assertLess(t2 - t1, t3 - t2)
        self.tem_send({**d, 'kwargs': {'a': 0, 'speed': 0.02}})
        t4 = time.perf_counter()
        self.assertLess(t3 - t2, t4 - t3)

    def test_38_setStagePosition(self):
        self.tem_send({'func_name': 'setStagePosition', 'args': (0, 0, 0, 0, 0)})
        p = {'a': 30, 'wait': False}
        t0 = time.perf_counter()
        self.tem_send({'func_name': 'setStagePosition', 'kwargs': p})
        t1 = time.perf_counter()
        self.tem_send({'func_name': 'waitForStage', 'kwargs': {'delay': 0.01}})
        t2 = time.perf_counter()
        q = {'a': 0, 'wait': True}
        self.tem_send({'func_name': 'setStagePosition', 'kwargs': q})
        t3 = time.perf_counter()
        self.assertLess(t1 - t0, t2 - t1)
        self.assertLess(t1 - t0, t3 - t2)

    def test_40_setStageA(self):
        p = (0, )
        self.tem_send({'func_name': 'setStageA', 'args': p})
        r = self.tem_send({'func_name': 'getStagePosition'})
        self.assertAlmostEqual(r[3], p[0], delta=PRECISION_DEG)

    def test_41_setStageA(self):
        p = (10, )
        self.tem_send({'func_name': 'setStageA', 'args': p})
        r = self.tem_send({'func_name': 'getStagePosition'})
        self.assertAlmostEqual(r[3], 0, delta=PRECISION_DEG)

    def test_46_setRotationSpeed(self):
        d = {'func_name': 'setStageA'}
        self.tem_send({**d, 'kwargs': {'a': 0}})
        t0 = time.perf_counter()
        self.tem_send({'func_name': 'setRotationSpeed', 'args': (1.0, )})
        self.tem_send({**d, 'kwargs': {'a': 5}})
        t1 = time.perf_counter()
        self.tem_send({'func_name': 'setRotationSpeed', 'args': (0.1, )})
        self.tem_send({**d, 'kwargs': {'a': 0}})
        t2 = time.perf_counter()
        self.assertLess(t1 - t0, t2 - t1)
        self.tem_send({'func_name': 'setRotationSpeed', 'args': (0.05, )})
        self.tem_send({**d, 'kwargs': {'a': 5}})
        t3 = time.perf_counter()
        self.assertLess(t2 - t1, t3 - t2)
        self.tem_send({'func_name': 'setRotationSpeed', 'args': (0.02, )})
        self.tem_send({**d, 'kwargs': {'a': 0}})
        t4 = time.perf_counter()
        self.assertLess(t3 - t2, t4 - t3)
        s = self.tem_send({'func_name': 'setRotationSpeed'})
        self.assertEqual(s, 0.02)
        self.tem_send({'func_name': 'setRotationSpeed', 'args': (1.0, )})

    def test_48_setStageA(self):
        self.tem_send({'func_name': 'setStageA', 'args': (0, )})
        p = {'a': 10, 'wait': False}
        t0 = time.perf_counter()
        self.tem_send({'func_name': 'setStageA', 'kwargs': p})
        t1 = time.perf_counter()
        self.tem_send({'func_name': 'waitForStage', 'kwargs': {'delay': 0.01}})
        t2 = time.perf_counter()
        q = {'a': 0, 'wait': True}
        self.tem_send({'func_name': 'setStageA', 'kwargs': q})
        t3 = time.perf_counter()
        self.assertLess(t1 - t0, t2 - t1)
        self.assertLess(t1 - t0, t3 - t2)

    def test_50_getGunShift(self):
        self.tem_send({'func_name': 'getGunShift'})

    def test_51_getHTValue(self):
        self.tem_send({'func_name': 'getHTValue'})

    def test_52_isBeamBlanked(self):
        self.tem_send({'func_name': 'isBeamBlanked'})

    def test_53_getBeamAlignShift(self):
        self.tem_send({'func_name': 'getBeamAlignShift'})

    def test_54_getSpotSize(self):
        self.tem_send({'func_name': 'getSpotSize'})

    def test_55_getBrightness(self):
        self.tem_send({'func_name': 'getBrightness'})

    def test_56_getBrightnessValue(self):
        self.tem_send({'func_name': 'getBrightnessValue'})

    def test_57_getBeamShift(self):
        self.tem_send({'func_name': 'getBeamShift'})

    def test_58_getBeamTilt(self):
        self.tem_send({'func_name': 'getBeamTilt'})

    def test_59_getCondensorLensStigmator(self):
        self.tem_send({'func_name': 'getCondensorLensStigmator'})

    def test_61_getScreenCurrent(self):
        self.tem_send({'func_name': 'getScreenCurrent'})

    def test_62_isfocusscreenin(self):
        r = self.tem_send({'func_name': 'isfocusscreenin'})
        self.assertIsInstance(r, bool)

    def test_63_getScreenPosition(self):
        r = self.tem_send({'func_name': 'getScreenPosition'})
        self.assertIn(r, {'up', 'down', ''})

    def test_64_getDiffFocus(self):
        r = self.tem_send({'func_name': 'getDiffFocus'})
        self.assertGreater(r, 0)
        self.assertLess(r, 65536)

    def test_65_getDiffFocusValue(self):
        r = self.tem_send({'func_name': 'getDiffFocusValue'})
        self.assertGreater(r, -1.0)
        self.assertLess(r, 1.0)

    def test_65_getFocus(self):
        r = self.tem_send({'func_name': 'getFocus'})
        self.assertGreater(r, -1.0)
        self.assertLess(r, 1.0)

    def test_67_FunctionMode(self):
        r = self.tem_send({'func_name': 'getFunctionMode'})
        r = self.tem_send({'func_name': 'setFunctionMode', 'args': (r, )})
        self.assertIn(r, ('lowmag', 'mag1', 'samag', 'mag2', 'diff'))

    def test_68_Magnification(self):
        r = self.tem_send({'func_name': 'getMagnification'})
        r = self.tem_send({'func_name': 'setMagnification', 'args': (r, )})
        self.assertIsInstance(r, float)

    def test_69_MagnificationIndex(self):
        r = self.tem_send({'func_name': 'getMagnificationIndex'})
        r = self.tem_send({'func_name': 'setMagnificationIndex', 'args': (r, )})
        self.assertIsInstance(r, int)

    def test_70_getDarkFieldTilt(self):
        r = self.tem_send({'func_name': 'getDarkFieldTilt'})
        self.assertIsInstance(r[0], float)

    def test_71_getImageShift1(self):
        r = self.tem_send({'func_name': 'getImageShift1'})
        self.assertIsInstance(r[0], float)

    def test_72_getImageShift2(self):
        r = self.tem_send({'func_name': 'getImageShift1'})
        self.assertEqual(r[0], 0)

    def test_73_getImageBeamShift(self):
        r = self.tem_send({'func_name': 'getImageBeamShift'})
        self.assertIsInstance(r[0], float)

    def test_74_getDiffShift(self):
        r = self.tem_send({'func_name': 'getDiffShift'})
        self.assertIsInstance(r[0], float)

    def test_76_getObjectiveLensStigmator(self):
        r = self.tem_send({'func_name': 'getObjectiveLensStigmator'})
        self.assertIsInstance(r[0], float)

    def test_77_getIntermediateLensStigmator(self):
        r = self.tem_send({'func_name': 'getIntermediateLensStigmator'})
        self.assertIsInstance(r[0], float)

    def test_80_init_cam_server(self):
        from instamaticServer.tem_server import CamServer, listen
        self.cam_server = CamServer()
        self.cam_server.start()
        self.cam_listener = threading.Thread(target=listen, args=(CamServer,))
        self.cam_listener.start()
        self.threads.extend([self.cam_server, self.cam_listener])

    def test_81_client_cam_connect(self):
        host = _conf.default_settings['cam_server_host']
        port = _conf.default_settings['cam_server_port']
        self.socket_cam = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket_cam.connect((host, port))
        atexit.register(self.socket_cam.close)

    def cam_send(self, d: Dict[str, Any]):
        return self.socket_send(self.socket_cam, d)

    def test_90_get_binning(self):
        r = self.cam_send({'attr_name': 'get_binning'})
        self.assertIsInstance(r, int)

    def test_91_default_binsize(self):
        r = self.cam_send({'attr_name': 'get_binning'})
        s = self.cam_send({'attr_name': 'default_binsize'})
        self.assertEqual(r, s)

    def test_92_dimensions(self):
        r = self.cam_send({'attr_name': 'dimensions'})
        self.assertIsInstance(r[0], int)

    def test_93_get_camera_dimensions(self):
        r = self.cam_send({'attr_name': 'get_camera_dimensions'})
        s = self.cam_send({'attr_name': 'dimensions'})
        self.assertEqual(r, s)

    def test_94_get_image_dimensions(self):
        r = self.cam_send({'attr_name': 'get_image_dimensions'})
        s = self.cam_send({'attr_name': 'get_camera_dimensions'})
        self.assertEqual(r, s)

    def test_96_get_image(self):
        r = self.cam_send({'attr_name': 'get_image'})
        r = self.cam_send({'attr_name': 'get_image_dimensions'})
        self.assertEqual(len(r))

    def test_97_get_image(self):
        r = self.cam_send({'attr_name': 'get_image'})
        s = self.cam_send({'attr_name': 'get_image_dimensions'})
        self.assertEqual(len(r), s[0])

    def test_98_get_movie(self):
        r = self.cam_send({'attr_name': 'get_movie'})
        s = self.cam_send({'attr_name': 'get_image_dimensions'})
        self.assertEqual(len(r[0]), s[0])

    def test_99_shutdown(self):
        from instamaticServer.tem_server import stop_program_event
        stop_program_event.set()
        for thread in [self.tem_server, self.tem_listener]:
            thread.join()
