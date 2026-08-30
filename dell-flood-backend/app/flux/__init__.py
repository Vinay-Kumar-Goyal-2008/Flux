import sys
import os
flux_dir = os.path.dirname(os.path.abspath(__file__))
if flux_dir not in sys.path:
    sys.path.insert(0, flux_dir)
