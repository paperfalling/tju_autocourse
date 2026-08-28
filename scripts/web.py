"""Build output host and Web API launcher."""

import sys
from pathlib import Path

import uvicorn


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


if __name__ == "__main__":
    from web_api.main import app

    uvicorn.run(app, host="127.0.0.1", port=8000)
