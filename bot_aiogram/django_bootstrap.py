import os
import sys
from pathlib import Path

backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "miniapp_backend.settings")

import django

django.setup()

