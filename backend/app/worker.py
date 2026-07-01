from __future__ import annotations

import threading
import time

from .config import settings
from .services import GovernanceService


class PipelineWorker:
    """Small DB-backed worker used by the no-dependency MVP server."""

    def __init__(self, service: GovernanceService):
        self.service = service
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="vgp-pipeline-worker", daemon=True)

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.is_set():
            processed = self.service.process_next_pipeline_job()
            if not processed:
                time.sleep(settings.pipeline_poll_seconds)

