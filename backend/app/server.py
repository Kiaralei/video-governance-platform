from __future__ import annotations

import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import settings
from .services import ConflictError, GovernanceService, NotFoundError, ValidationError, config_payload
from .worker import PipelineWorker


class VgpServer(ThreadingHTTPServer):
    def __init__(self, server_address, request_handler_class, service: GovernanceService):
        super().__init__(server_address, request_handler_class)
        self.service = service
        self.worker = PipelineWorker(service)

    def start_worker(self) -> None:
        self.worker.start()

    def server_close(self) -> None:
        self.worker.stop()
        super().server_close()


class ApiHandler(SimpleHTTPRequestHandler):
    server_version = "VGP-MVP/1.0"

    def __init__(self, *args, directory: str | None = None, **kwargs):
        super().__init__(*args, directory=directory or str(settings.frontend_dir), **kwargs)

    @property
    def service(self) -> GovernanceService:
        return self.server.service  # type: ignore[attr-defined]

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api("GET", parsed.path, parse_qs(parsed.query))
            return
        if parsed.path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api("POST", parsed.path, parse_qs(parsed.query))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def _handle_api(self, method: str, path: str, query: dict[str, list[str]]) -> None:
        try:
            body = self._read_json() if method == "POST" else {}
            result = self._route(method, path, query, body)
            self._json(result)
        except ValidationError as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except NotFoundError as exc:
            self._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
        except ConflictError as exc:
            self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
        except Exception as exc:  # pragma: no cover - final defensive boundary
            self._json({"error": "服务内部错误", "detail": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _route(self, method: str, path: str, query: dict[str, list[str]], body: dict) -> dict:
        if method == "GET" and path == "/api/v1/health":
            return {"status": "ok", "app": settings.app_name}
        if method == "GET" and path == "/api/v1/config":
            return config_payload()
        if method == "GET" and path == "/api/v1/dashboard/summary":
            return self.service.summary()
        if method == "GET" and path == "/api/v1/pipeline/jobs":
            offset = int(query.get("offset", ["0"])[0])
            limit = int(query.get("limit", ["50"])[0])
            status = query.get("status", [None])[0]
            return self.service.list_pipeline_jobs(offset=offset, limit=limit, status=status)
        if method == "POST" and path == "/api/v1/pipeline/drain":
            limit = body.get("limit")
            return {"processed": self.service.drain_pipeline(limit=int(limit) if limit is not None else None)}
        if method == "GET" and path == "/api/v1/machine/reviews":
            offset = int(query.get("offset", ["0"])[0])
            limit = int(query.get("limit", ["50"])[0])
            return self.service.list_machine_reviews(offset=offset, limit=limit)
        if method == "GET" and path.startswith("/api/v1/machine/reviews/"):
            return self.service.get_machine_review(path.rsplit("/", 1)[-1])
        if method == "POST" and path == "/api/v1/dev/reset":
            return self.service.reset()
        if method == "POST" and path == "/api/v1/dev/seed":
            return self.service.seed()
        if method == "POST" and path == "/api/v1/content/upload":
            return self.service.ingest_content(body)
        if method == "POST" and path == "/api/v1/content/batch":
            return self.service.ingest_batch(body)
        if method == "GET" and path == "/api/v1/review/human/queue":
            offset = int(query.get("offset", ["0"])[0])
            limit = int(query.get("limit", ["20"])[0])
            status = query.get("status", ["pending"])[0]
            return self.service.list_queue(offset=offset, limit=limit, status=status)
        if method == "GET" and path == "/api/v1/audit":
            content_id = query.get("content_id", [None])[0]
            return self.service.get_audit(content_id=content_id)
        if method == "GET" and path.startswith("/api/v1/evidence/"):
            return self.service.get_evidence(path.rsplit("/", 1)[-1])
        if path.startswith("/api/v1/review/human/"):
            parts = path.split("/")
            task_id = parts[5] if len(parts) > 5 else ""
            if method == "GET" and len(parts) == 6:
                return self.service.get_case(task_id)
            if method == "POST" and len(parts) == 7 and parts[6] == "claim":
                return self.service.claim_task(task_id, str(body.get("reviewer_id", "reviewer_demo")))
            if method == "POST" and len(parts) == 7 and parts[6] == "decide":
                return self.service.decide_task(task_id, body)
        raise NotFoundError("接口不存在")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError("请求体不是合法 JSON") from exc
        if not isinstance(data, dict):
            raise ValidationError("JSON 请求体必须是对象")
        return data

    def _json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args) -> None:
        if not self.path.startswith("/api/v1/health"):
            super().log_message(format, *args)


def create_server(host: str | None = None, port: int | None = None, db_path: Path | None = None) -> ThreadingHTTPServer:
    service = GovernanceService(db_path=db_path)
    server = VgpServer((host or settings.host, port if port is not None else settings.port), ApiHandler, service)
    server.start_worker()
    return server
