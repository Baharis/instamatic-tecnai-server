from pathlib import Path
from types import SimpleNamespace
from typing import Dict

import yaml


_settings_file = 'settings.yaml'


def dict_to_namespace(d: Dict) -> SimpleNamespace:
    """Recursively converts a dictionary into a SimpleNamespace."""
    if isinstance(d, dict):
        return SimpleNamespace(**{k: dict_to_namespace(v) for k, v in d.items()})
    return d


class Config:
    def __init__(self, name:str=None):
        self.default_settings = self.settings()

        if name is not None:
            self.default_settings['microscope'] = name

        self.micr_interface, self.micr_wavelength, self.micr_ranges = self.microscope()
        try:
            self.camera = self.load_camera_config()
        except FileNotFoundError:
            self.camera = SimpleNamespace()

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
        with open(str(file), 'r') as stream:
            default = yaml.safe_load(stream)

        interface = default['interface']
        wavelength = default['wavelength']
        micr_ranges = default['ranges']

        return interface, wavelength, micr_ranges

    def load_camera_config(self) -> SimpleNamespace:
        directory = Path(__file__).resolve().parent
        file = directory / (str(self.default_settings['camera']) + '.yaml')
        with open(str(file), 'r') as stream:
            return dict_to_namespace(yaml.safe_load(stream))


config = Config()


if __name__ == '__main__':
    data = Config()
    print(data.default_settings['microscope'])
    print(data.micr_ranges['Mh'])
    

