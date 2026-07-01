from __future__ import annotations

import uvicorn

from app.api import app
from app.config import settings


def main() -> None:
    print(f"Video Governance Platform MVP running at http://{settings.host}:{settings.port}")
    print(f"Interactive API docs at http://{settings.host}:{settings.port}/docs")
    print("Press Ctrl+C to stop.")
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
