:: VARIANT 1 - IF YOU HAVE PROPERLY WORKING VENV
cd c:\instamatic\instamatic-tecnai-server  &:: point to your installation directory
call .\venv\Scripts\activate.bat           &:: uncomment and point to venv if using one
python tem_server.py                       &:: use `py`, `py3`, or `python` as needed

:: VARIANT 2 - CALL DIRECTLY, REQUIRES UNCOMMENTED BOILERPLATE
:: cd Q:\DanielT\instamatic-tecnai-server
:: Q:\Malika\py\py34\python-3.4.4\python.exe Q:\DanielT\instamatic-tecnai-server\tem_server.py

:: If using cam server, this file can be copied and also adapted for cam_server.py
