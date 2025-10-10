# Config package
import sys
import os

# Add parent directory to path to import the main config.py
parent_dir = os.path.dirname(os.path.dirname(__file__))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Import the config from the main config.py file
import importlib.util
spec = importlib.util.spec_from_file_location("main_config", os.path.join(parent_dir, "config.py"))
main_config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main_config)

# Export the config object
config = main_config.config

__all__ = ['config']
