"""
Bagheera Viewer: a image viewer with KDE/Baloo.
"""

__appname__ = "BagheeraView"
__version__ = "1.1.0"
__author__ = "Ignacio Serantes"
__email__ = "kde@aynoa.net"
__license__ = "LGPL"
__status__ = "Production"
# "Prototype, Development, Alpha, Beta, Production, Stable, Deprecated"

from .core.app import main

__all__ = ["EvaluateExpression", "__version__"]
