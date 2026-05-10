import ctypes
import glob
import os

_current_dir = os.path.dirname(__file__)
_so_files = glob.glob(os.path.join(_current_dir, "baloo_wrapper*.so"))

if _so_files:
    baloo_lib = ctypes.CDLL(_so_files[0])
