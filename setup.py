import os

from setuptools import setup

MYPYC_MODULES = [
    "h11_mypyc/_abnf.py",
    "h11_mypyc/_util.py",
    "h11_mypyc/_receivebuffer.py",
    "h11_mypyc/_headers.py",
    "h11_mypyc/_events.py",
    "h11_mypyc/_readers.py",
    "h11_mypyc/_writers.py",
    "h11_mypyc/_state.py",
    "h11_mypyc/_connection.py",
]

if os.environ.get("H11_MYPYC") == "1":
    # Imported lazily: mypyc is not in build-system.requires, so it is absent
    # from the isolated build env used for the pure-Python path.
    from mypyc.build import mypycify

    setup(ext_modules=mypycify(MYPYC_MODULES))
else:
    setup()
