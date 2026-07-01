from __future__ import annotations

import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.server import create_server


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        server = create_server(port=0, db_path=Path(tmp) / "batch-smoke.sqlite3")
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            command = [
                sys.executable,
                str(ROOT / "scripts" / "load_test.py"),
                "--port",
                str(port),
                "--count",
                "6",
                "--batch-size",
                "3",
            ]
            video_dir = ROOT / "data" / "test_videos"
            if video_dir.exists():
                command.extend(["--video-dir", str(video_dir)])
            command.append("--drain")
            subprocess.run(
                command,
                cwd=ROOT,
                check=True,
            )
            print("BATCH SMOKE PASS")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
