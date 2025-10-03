"""This vendoring shim exists to enable vendored libraries to be accessible to
sculptor.

Vendored libraries are installed with
  uv pip install ../<library> [--no-deps] --target _vendor

which puts them into the _vendor/ directory

This shim enables sculptor to search that location for those imports.
"""

import importlib.resources as resources
import sys

assert __package__, "Please run sculptor from the distribution"
vendor = resources.files(__package__).joinpath("../_vendor")
sys.path.insert(0, str(vendor))
