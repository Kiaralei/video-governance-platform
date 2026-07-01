from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .config import settings


class ModalityModelRunner:
    """Calls optional external ASR/OCR/vision services and normalizes outputs."""

    def extract(
        self,
        *,
        media_asset: dict[str, Any],
        video_meta: dict[str, Any],
        frames: list[dict[str, Any]],
        title: str,
        description: str,
    ) -> dict[str, Any]:
        invocations: list[dict[str, Any]] = []

        content_metadata = {"title": title, "description": description}
        asr_result = self._call_asr(media_asset, video_meta, content_metadata, invocations)
        ocr_result = self._call_ocr(media_asset, video_meta, frames, content_metadata, invocations)
        vision_result = self._call_vision(media_asset, video_meta, frames, content_metadata, invocations)

        return {
            "asr_transcript": asr_result or [{"start_ms": 0, "end_ms": 12000, "text": description}],
            "ocr_results": ocr_result or [{"frame_id": "frame_002", "text": title, "bbox": [0.12, 0.18, 0.76, 0.24]}],
            "object_detections": vision_result.get("object_detections", []),
            "scene_tags": vision_result.get("scene_tags") or [{"tag": "general_video", "confidence": 0.68}],
            "modality_model_invocations": invocations,
        }

    def _call_asr(
        self,
        media_asset: dict[str, Any],
        video_meta: dict[str, Any],
        content_metadata: dict[str, str],
        invocations: list[dict[str, Any]],
    ) -> list[dict[str, Any]] | None:
        payload = self._base_payload(media_asset, video_meta, content_metadata)
        result = self._call_model("asr", settings.asr_model_url, payload, invocations)
        if not result:
            return None
        segments = result.get("segments", result.get("asr_transcript", []))
        if not isinstance(segments, list):
            return None
        normalized = []
        for segment in segments:
            if not isinstance(segment, dict) or not segment.get("text"):
                continue
            normalized.append(
                {
                    "start_ms": self._int_value(segment.get("start_ms"), 0),
                    "end_ms": self._int_value(segment.get("end_ms"), 0),
                    "text": str(segment["text"]),
                    "source": "external_asr",
                    "model_version": str(result.get("model_version", "")),
                }
            )
        return normalized or None

    def _call_ocr(
        self,
        media_asset: dict[str, Any],
        video_meta: dict[str, Any],
        frames: list[dict[str, Any]],
        content_metadata: dict[str, str],
        invocations: list[dict[str, Any]],
    ) -> list[dict[str, Any]] | None:
        payload = {**self._base_payload(media_asset, video_meta, content_metadata), "frames": frames}
        result = self._call_model("ocr", settings.ocr_model_url, payload, invocations)
        if not result:
            return None
        items = result.get("items", result.get("ocr_results", []))
        if not isinstance(items, list):
            return None
        normalized = []
        for item in items:
            if not isinstance(item, dict) or not item.get("text"):
                continue
            normalized.append(
                {
                    "frame_id": str(item.get("frame_id", "frame_001")),
                    "text": str(item["text"]),
                    "bbox": item.get("bbox", []),
                    "source": "external_ocr",
                    "model_version": str(result.get("model_version", "")),
                }
            )
        return normalized or None

    def _call_vision(
        self,
        media_asset: dict[str, Any],
        video_meta: dict[str, Any],
        frames: list[dict[str, Any]],
        content_metadata: dict[str, str],
        invocations: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        payload = {**self._base_payload(media_asset, video_meta, content_metadata), "frames": frames}
        result = self._call_model("vision", settings.vision_model_url, payload, invocations)
        if not result:
            return {"object_detections": [], "scene_tags": []}

        objects = result.get("object_detections", result.get("objects", []))
        scenes = result.get("scene_tags", result.get("scenes", []))
        return {
            "object_detections": self._normalize_objects(objects, result),
            "scene_tags": self._normalize_scenes(scenes, result),
        }

    def _call_model(
        self,
        modality: str,
        url: str,
        payload: dict[str, Any],
        invocations: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not url:
            invocations.append({"modality": modality, "status": "not_configured"})
            return None

        headers = {"Content-Type": "application/json"}
        if settings.model_api_key:
            headers["Authorization"] = f"Bearer {settings.model_api_key}"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=settings.model_timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            invocations.append({"modality": modality, "status": "failed", "error": str(exc)})
            return None

        if not isinstance(response_payload, dict):
            invocations.append({"modality": modality, "status": "invalid_response"})
            return None

        invocation = {
            "modality": modality,
            "status": "completed",
            "model_version": str(response_payload.get("model_version", "")),
        }
        if response_payload.get("provider"):
            invocation["provider"] = str(response_payload["provider"])
        if response_payload.get("warnings"):
            invocation["warnings"] = response_payload["warnings"]
        invocations.append(invocation)
        return response_payload

    def _base_payload(
        self,
        media_asset: dict[str, Any],
        video_meta: dict[str, Any],
        content_metadata: dict[str, str],
    ) -> dict[str, Any]:
        return {
            "asset_id": media_asset.get("asset_id"),
            "storage_uri": media_asset.get("storage_uri"),
            "local_path": media_asset.get("local_path"),
            "source_type": media_asset.get("source_type"),
            "video_meta": video_meta,
            "content_metadata": content_metadata,
        }

    def _normalize_objects(self, objects: Any, result: dict[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(objects, list):
            return []
        normalized = []
        for item in objects:
            if not isinstance(item, dict) or not item.get("label"):
                continue
            normalized.append(
                {
                    "frame_id": str(item.get("frame_id", "frame_001")),
                    "label": str(item["label"]),
                    "bbox": item.get("bbox", []),
                    "confidence": self._float_value(item.get("confidence"), 0.0),
                    "source": "external_vision",
                    "model_version": str(result.get("model_version", "")),
                }
            )
        return normalized

    def _normalize_scenes(self, scenes: Any, result: dict[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(scenes, list):
            return []
        normalized = []
        for item in scenes:
            if not isinstance(item, dict) or not item.get("tag"):
                continue
            normalized.append(
                {
                    "tag": str(item["tag"]),
                    "confidence": self._float_value(item.get("confidence"), 0.0),
                    "source": "external_vision",
                    "model_version": str(result.get("model_version", "")),
                }
            )
        return normalized

    def _int_value(self, value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _float_value(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
