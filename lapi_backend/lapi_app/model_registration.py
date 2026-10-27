"""Compatibility import; implementation lives in lapi_models.registration."""
import sys as _sys
from importlib import import_module as _import_module
_sys.modules[__name__] = _import_module("lapi_app.lapi_models.registration")
