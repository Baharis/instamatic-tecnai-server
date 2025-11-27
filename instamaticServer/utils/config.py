from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Any

import yaml


_settings_file = 'settings.yaml'


class NS(SimpleNamespace):
    def get(self, key, default=None):
        return getattr(self, key, default)


def dict_to_namespace(d: Dict) -> NS[Any]:
    """Recursively converts a dictionary into a SimpleNamespace."""
    if isinstance(d, dict):
        return NS(**{k: dict_to_namespace(v) for k, v in d.items()})
    return d


class config:

    def __init__(self, name:str=None):
        self.default_settings = self.settings()

        if name != None:
            self.default_settings['microscope'] = name

        self.micr_interface, self.micr_wavelength, self.micr_ranges = self.microscope()
        try:
            self.camera = self.load_camera_config()
        except FileNotFoundError:
            self.camera = NS()

    def settings(self) -> dict:
        """load the settings.yaml file."""
        directory = Path(__file__).resolve().parent
        file = directory.joinpath(_settings_file)
        with open(str(file), 'r') as stream:
            return yaml.safe_load(stream)

    def microscope(self):
        """load the microscope.yaml file."""
        directory = Path(__file__).resolve().parent
        file = directory / (str(self.default_settings['microscope']) + '.yaml')
        with open(file, 'r') as stream:
            default = yaml.safe_load(stream)

        interface = default['interface']
        wavelength = default['wavelength']
        micr_ranges = default['ranges']

        return interface, wavelength, micr_ranges

    def load_camera_config(self) -> NS:
        directory = Path(__file__).resolve().parent
        file = directory / (str(self.default_settings['camera']) + '.yaml')
        with open(file, 'r') as stream:
            return dict_to_namespace(yaml.safe_load(stream))


if __name__ == '__main__':
    data = config()
    print(data.default_settings['microscope'])
    print(data.micr_ranges['Mh'])
    

