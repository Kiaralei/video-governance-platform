from __future__ import annotations

import argparse
import http.client
import json
import time
from pathlib import Path
from typing import Any


def request(base_host: str, port: int, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    conn = http.client.HTTPConnection(base_host, port, timeout=30)
    raw = json.dumps(body or {}, ensure_ascii=False).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    try:
        conn.request(method, path, body=raw, headers=headers)
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
    finally:
        conn.close()
    if response.status >= 400:
        raise RuntimeError(f"{method} {path} failed: {response.status} {payload}")
    return payload


def load_video_paths(video_dir: str) -> list[str]:
    paths = sorted(Path(video_dir).resolve().glob("*.mp4"))
    return [str(path) for path in paths if path.is_file()]


def build_items(start: int, count: int, video_paths: list[str] | None = None) -> list[dict[str, str]]:
    items = []
    for index in range(start, start + count):
        video_url = f"https://example.local/load-test/{index}.mp4"
        if video_paths:
            video_url = video_paths[index % len(video_paths)]
        items.append(
            {
                "title": f"Load test video {index}",
                "description": "A neutral bulk-ingested video reference for pipeline load testing.",
                "creator_id": "creator_load_test",
                "poi": "global",
                "video_url": video_url,
            }
        )
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Create bulk video governance jobs through the public API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--video-dir", default="", help="Use local .mp4 fixtures from this directory as video_url.")
    parser.add_argument("--drain", action="store_true", help="Ask the API to drain queued jobs after ingestion.")
    args = parser.parse_args()

    if args.count <= 0:
        raise SystemExit("--count must be positive")
    if args.batch_size <= 0:
        raise SystemExit("--batch-size must be positive")
    video_paths = load_video_paths(args.video_dir) if args.video_dir else None
    if args.video_dir and not video_paths:
        raise SystemExit(f"no .mp4 files found in {args.video_dir}")

    started = time.perf_counter()
    accepted = 0
    failed = 0
    for start in range(0, args.count, args.batch_size):
        size = min(args.batch_size, args.count - start)
        result = request(
            args.host,
            args.port,
            "POST",
            "/api/v1/content/batch",
            {"items": build_items(start, size, video_paths)},
        )
        accepted += int(result["accepted"])
        failed += int(result["failed"])
        print(f"batch start={start} size={size} accepted={result['accepted']} failed={result['failed']}")

    drained = 0
    if args.drain:
        drain_result = request(args.host, args.port, "POST", "/api/v1/pipeline/drain", {"limit": args.count})
        drained = int(drain_result["processed"])

    summary = request(args.host, args.port, "GET", "/api/v1/dashboard/summary")
    elapsed = time.perf_counter() - started
    print(
        json.dumps(
            {
                "accepted": accepted,
                "failed": failed,
                "drained": drained,
                "elapsed_seconds": round(elapsed, 3),
                "summary": summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
