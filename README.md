# Server for the Tecnai-Scripting interface

This "Tecnai-Server" is a supplementary TEM server used to control an FEI machine: Tecnai TEM, Titan TEM, or an integrated camera, via the instamatic software. It can be used in lieu of the full instamatic on computers that do not support modern Python. It has been tested on an FEI Tecnai G2 and an FEI Titan 80-300 microscope. The program provides access for the instamatic software to the com-scripting interface of the TEM.

## Installation and Requirement

The server software was developed in a Python 3.4 software environment (Windows XP). Following you have to install the Python 3.4 software package on your microscope-PC. The additional needed software-side packages and their last versions confirmed to work on Windows XP are:

- `comtypes` – version 1.2.1 ([link](https://pypi.org/project/comtypes/1.2.1/#comtypes-1.2.1-py2.py3-none-any.whl));
- `pip` – version 19.1.1 ([link](https://pypi.org/project/pip/19.1.1/#pip-19.1.1-py2.py3-none-any.whl));
- `PyYAML` – version 5.1.2 ([link](https://pypi.org/project/PyYAML/5.1.2/#PyYAML-5.1.2-cp34-cp34m-win32.whl));
- `typing` – version 3.10.0.0 ([link](https://pypi.org/project/typing/3.10.0.0/#typing-3.10.0.0-py3-none-any.whl));

If you furthermore intend to use `instamatic-tecnai-server` to interface an integrated camera:

- `numpy` – version 1.15.4 ([link](https://pypi.org/project/numpy/1.15.4/#files)).

The packages can be installed using pip, either automatically (if connected to the internet) or manually, by downloading, copying, and pointing to the wheel files linked above. Furthermore, the FEI com-scripting interface should be available on your TEM-PC. It is most convenient to create an installation in a custom virtual environment, e.g. using conda, on a removable or shared drive.

## Usage

On the Microscope PC, install this script. On the camera and/or support PC, install [instamatic software](https://github.com/instamatic-dev/instamatic). Follow example configuration 2 or 3 from the documentation. The instamatic GUI instance on the camera PC will communicate with "Tecnai-Server"-software [over the network](https://instamatic.readthedocs.io/en/latest/network/).

The "Tecnai-Server"-software is provided as a standard python-program. You can download and install the software in your chosen directory on the microscope-PC. After you have opened an MS-DOS command prompt you are navigating to the installation directory. The server will be started by the usual python invocation `py tem_server.py`. An integrated camera, if used, can be accessed using analogous `py cam_server.py`. A corresponding `start.bat` file provided in the installation directory can be adapted and used to run the command(s).

The software will be configured by the .yaml-files in the `utils`-subdirectory. For instance the correct network address of your microscope-PC is set in the `settings.yaml` file. The magnification table of your TEM or the scripting interface `tecnai` are saved in the `microscope.yaml` file.

In our experimental setup the [instamatic software](https://github.com/instamatic-dev/instamatic) is installed on a separate PC (camera PC). In this case the configuration files of Instamatic must be adapted like in the server software. Especially the `interface=tecnai`, the microscope, the network address and the flag `use_tem_server` should be verified. Afterward, the instamatic software should be starting without errors on your PC. You can use an IPython shell (`instamatic.controller`) to test if the TEMController-object has access to TEM.

## Credits

Thanks to Steffen Schmidt ([CUP, LMU München](https://www.cup.uni-muenchen.de/)) for providing the original script.
