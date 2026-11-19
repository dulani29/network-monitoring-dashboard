"""Optional: add your own devices from the command line.
    python scripts/seed_devices.py "NAS" 192.168.1.20 server
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app          # noqa: E402
from config import Config           # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    app = create_app(type("C", (Config,), {"AUTO_MONITOR_DEFAULT": False, "TESTING": True}))
    name, host = sys.argv[1], sys.argv[2]
    dtype = sys.argv[3] if len(sys.argv) > 3 else "other"
    print(app.extensions["netmon"]["devices"].create(name, host, dtype))
