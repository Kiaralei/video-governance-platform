from __future__ import annotations

import base64
import hashlib
import hmac
import json
import mimetypes
import os
import re
import shutil
import sys
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GatewaySettings:
    host: str = os.environ.get("MODEL_GATEWAY_HOST", "127.0.0.1")
    port: int = int(os.environ.get("MODEL_GATEWAY_PORT", "9001"))
    api_key: str = os.environ.get("MODEL_GATEWAY_API_KEY", "")
    timeout_seconds: float = float(os.environ.get("MODEL_GATEWAY_TIMEOUT_SECONDS", "30"))
    asr_provider: str = os.environ.get("MODEL_GATEWAY_ASR_PROVIDER", "local").lower()
    ocr_provider: str = os.environ.get("MODEL_GATEWAY_OCR_PROVIDER", "local").lower()
    vision_provider: str = os.environ.get("MODEL_GATEWAY_VISION_PROVIDER", "local").lower()
    asr_upstream_url: str = os.environ.get("MODEL_GATEWAY_ASR_UPSTREAM_URL", "")
    ocr_upstream_url: str = os.environ.get("MODEL_GATEWAY_OCR_UPSTREAM_URL", "")
    vision_upstream_url: str = os.environ.get("MODEL_GATEWAY_VISION_UPSTREAM_URL", "")
    upstream_api_key: str = os.environ.get("MODEL_GATEWAY_UPSTREAM_API_KEY", "")
    azure_vision_endpoint: str = os.environ.get("AZURE_VISION_ENDPOINT", "")
    azure_vision_key: str = os.environ.get("AZURE_VISION_KEY", "")
    azure_vision_api_version: str = os.environ.get("AZURE_VISION_API_VERSION", "2024-02-01")
    tencent_secret_id: str = os.environ.get("TENCENTCLOUD_SECRET_ID", "")
    tencent_secret_key: str = os.environ.get("TENCENTCLOUD_SECRET_KEY", "")
    tencent_region: str = os.environ.get("TENCENTCLOUD_REGION", "ap-guangzhou")
    tencent_asr_endpoint: str = os.environ.get("TENCENT_ASR_ENDPOINT", "https://asr.tencentcloudapi.com")
    tencent_asr_action: str = os.environ.get("TENCENT_ASR_ACTION", "SentenceRecognition")
    tencent_asr_version: str = os.environ.get("TENCENT_ASR_VERSION", "2019-06-14")
    tencent_asr_engine: str = os.environ.get("TENCENT_ASR_ENGINE", "16k_zh")
    tencent_asr_voice_format: str = os.environ.get("TENCENT_ASR_VOICE_FORMAT", "wav")
    tencent_asr_word_info: int = int(os.environ.get("TENCENT_ASR_WORD_INFO", "0"))
    tencent_asr_max_base64_bytes: int = int(os.environ.get("TENCENT_ASR_MAX_BASE64_BYTES", "3145728"))
    tencent_ocr_endpoint: str = os.environ.get("TENCENT_OCR_ENDPOINT", "https://ocr.tencentcloudapi.com")
    tencent_ocr_action: str = os.environ.get("TENCENT_OCR_ACTION", "GeneralBasicOCR")
    tencent_ocr_version: str = os.environ.get("TENCENT_OCR_VERSION", "2018-11-19")
    ffmpeg_path: str = os.environ.get("MODEL_GATEWAY_FFMPEG_PATH") or os.environ.get("VGP_FFMPEG_PATH") or ""


def gateway_settings() -> GatewaySettings:
    return GatewaySettings()


class ModelGateway:
    """Small adapter service for ASR, OCR, and vision model providers."""

    def __init__(self, settings: GatewaySettings | None = None):
        self.settings = settings or gateway_settings()

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "model_gateway",
            "providers": {
                "asr": self.settings.asr_provider,
                "ocr": self.settings.ocr_provider,
                "vision": self.settings.vision_provider,
            },
            "azure_vision_configured": bool(self.settings.azure_vision_endpoint and self.settings.azure_vision_key),
            "tencent_asr_configured": bool(self.settings.tencent_secret_id and self.settings.tencent_secret_key),
            "tencent_ocr_configured": bool(self.settings.tencent_secret_id and self.settings.tencent_secret_key),
        }

    def asr(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.settings.asr_upstream_url or self.settings.asr_provider == "upstream":
            return self._call_upstream(self.settings.asr_upstream_url, payload)
        if self.settings.asr_provider in {"tencent", "tencent_asr"}:
            return self._tencent_asr(payload)
        return self._local_asr(payload)

    def ocr(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.settings.ocr_upstream_url or self.settings.ocr_provider == "upstream":
            return self._call_upstream(self.settings.ocr_upstream_url, payload)
        if self.settings.ocr_provider in {"azure", "azure_vision"}:
            return self._azure_ocr(payload)
        if self.settings.ocr_provider in {"tencent", "tencent_ocr"}:
            return self._tencent_ocr(payload)
        return self._local_ocr(payload)

    def vision(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.settings.vision_upstream_url or self.settings.vision_provider == "upstream":
            return self._call_upstream(self.settings.vision_upstream_url, payload)
        if self.settings.vision_provider in {"azure", "azure_vision"}:
            return self._azure_vision(payload)
        return self._local_vision(payload)

    def _call_upstream(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not url:
            raise GatewayError("upstream provider selected but upstream URL is empty", HTTPStatus.BAD_GATEWAY)
        headers = {"Content-Type": "application/json"}
        if self.settings.upstream_api_key:
            headers["Authorization"] = f"Bearer {self.settings.upstream_api_key}"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GatewayError(f"upstream request failed: {exc}", HTTPStatus.BAD_GATEWAY) from exc
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise GatewayError("upstream returned invalid JSON", HTTPStatus.BAD_GATEWAY) from exc
        if not isinstance(data, dict):
            raise GatewayError("upstream JSON response must be an object", HTTPStatus.BAD_GATEWAY)
        return data

    def _local_asr(self, payload: dict[str, Any]) -> dict[str, Any]:
        metadata = self._content_metadata(payload)
        description = metadata.get("description") or ""
        text = description.strip()
        if not text:
            text = "local gateway did not receive audio or description text"
        return {
            "model_version": "local-gateway-asr-v1",
            "provider": "local_heuristic",
            "segments": [{"start_ms": 0, "end_ms": self._duration_hint(payload), "text": text}],
            "warnings": ["ASR provider is local heuristic; configure an upstream ASR service for real speech-to-text."],
        }

    def _local_ocr(self, payload: dict[str, Any]) -> dict[str, Any]:
        metadata = self._content_metadata(payload)
        title = (metadata.get("title") or "").strip()
        frames = payload.get("frames") if isinstance(payload.get("frames"), list) else []
        items: list[dict[str, Any]] = []
        if title:
            items.append({"frame_id": "frame_001", "text": title, "bbox": [0.05, 0.08, 0.9, 0.18]})
        for frame in frames[:3]:
            if isinstance(frame, dict) and frame.get("caption"):
                items.append(
                    {
                        "frame_id": str(frame.get("frame_id", "frame_001")),
                        "text": str(frame["caption"]),
                        "bbox": [0.08, 0.72, 0.86, 0.18],
                    }
                )
        if not items:
            items.append({"frame_id": "frame_001", "text": "local gateway found no OCR text", "bbox": []})
        return {
            "model_version": "local-gateway-ocr-v1",
            "provider": "local_heuristic",
            "items": items,
            "warnings": ["OCR provider is local heuristic; configure Azure Vision or another OCR service for real OCR."],
        }

    def _local_vision(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = self._combined_text(payload).lower()
        scenes = [{"tag": "general_video", "confidence": 0.62}]
        keyword_tags = [
            ("kitchen", {"cooking", "recipe", "food", "kitchen"}),
            ("education", {"tutorial", "lesson", "course", "education"}),
            ("travel", {"travel", "hotel", "poi", "city"}),
            ("marketing", {"bonus", "promo", "discount", "scan", "qr"}),
            ("gaming_or_betting", {"bet", "betting", "gambling", "casino"}),
        ]
        for tag, words in keyword_tags:
            if any(word in text for word in words):
                scenes.insert(0, {"tag": tag, "confidence": 0.78})
        objects = []
        if any(word in text for word in {"qr", "scan"}):
            objects.append({"frame_id": "frame_001", "label": "qr_code_or_scan_prompt", "confidence": 0.66})
        return {
            "model_version": "local-gateway-vision-v1",
            "provider": "local_heuristic",
            "objects": objects,
            "scenes": scenes[:4],
            "warnings": [
                "Vision provider is local heuristic; configure Azure Vision or another detector for real image analysis."
            ],
        }

    def _tencent_asr(self, payload: dict[str, Any]) -> dict[str, Any]:
        audio_bytes, voice_format = self._first_audio_bytes(payload)
        if not audio_bytes:
            raise GatewayError("Tencent ASR audio payload is empty", HTTPStatus.BAD_REQUEST)
        encoded = base64.b64encode(audio_bytes).decode("ascii")
        if len(encoded.encode("ascii")) > self.settings.tencent_asr_max_base64_bytes:
            raise GatewayError(
                "Tencent ASR audio payload exceeds the SentenceRecognition size limit",
                HTTPStatus.BAD_REQUEST,
            )

        params = {
            "SubServiceType": 2,
            "ProjectId": 0,
            "EngSerViceType": self.settings.tencent_asr_engine,
            "VoiceFormat": voice_format,
            "SourceType": 1,
            "Data": encoded,
            "DataLen": len(audio_bytes),
        }
        if self.settings.tencent_asr_word_info:
            params["WordInfo"] = self.settings.tencent_asr_word_info

        data = self._call_tencent_asr_api(params)
        text = str(data.get("Result") or "").strip()
        word_list = data.get("WordList") if isinstance(data.get("WordList"), list) else []
        if not text and word_list:
            text = "".join(str(item.get("Word", "")) for item in word_list if isinstance(item, dict)).strip()
        duration_ms = self._int_value(data.get("AudioDuration"), self._duration_hint(payload))
        segments = [{"start_ms": 0, "end_ms": duration_ms, "text": text}] if text else []
        return {
            "model_version": f"tencent-asr-{self.settings.tencent_asr_engine}",
            "provider": "tencent_asr",
            "segments": segments,
            "raw_provider_status": "completed",
            "request_id": data.get("RequestId", ""),
        }

    def _azure_ocr(self, payload: dict[str, Any]) -> dict[str, Any]:
        analysis = self._call_azure_image_analysis(payload, features=("read",))
        items: list[dict[str, Any]] = []
        read_result = analysis.get("readResult", {})
        blocks = read_result.get("blocks") if isinstance(read_result, dict) else []
        for block in blocks or []:
            for line in block.get("lines", []) if isinstance(block, dict) else []:
                text = line.get("text") if isinstance(line, dict) else None
                if text:
                    items.append({"frame_id": "frame_001", "text": str(text), "bbox": line.get("boundingPolygon", [])})
        return {
            "model_version": "azure-vision-image-analysis",
            "provider": "azure_vision",
            "items": items,
            "raw_provider_status": "completed",
        }

    def _azure_vision(self, payload: dict[str, Any]) -> dict[str, Any]:
        analysis = self._call_azure_image_analysis(payload, features=("caption", "objects", "tags"))
        objects: list[dict[str, Any]] = []
        objects_result = analysis.get("objectsResult", {})
        values = objects_result.get("values") if isinstance(objects_result, dict) else []
        for item in values or []:
            if not isinstance(item, dict):
                continue
            tags = item.get("tags") if isinstance(item.get("tags"), list) else []
            label = tags[0].get("name") if tags and isinstance(tags[0], dict) else item.get("name")
            confidence = tags[0].get("confidence") if tags and isinstance(tags[0], dict) else item.get("confidence", 0)
            if label:
                objects.append(
                    {
                        "frame_id": "frame_001",
                        "label": str(label),
                        "confidence": self._float_value(confidence, 0.0),
                        "bbox": item.get("boundingBox", []),
                    }
                )
        scenes: list[dict[str, Any]] = []
        caption = analysis.get("captionResult", {})
        if isinstance(caption, dict) and caption.get("text"):
            scenes.append(
                {
                    "tag": self._slug(str(caption["text"]))[:80],
                    "confidence": self._float_value(caption.get("confidence"), 0.0),
                }
            )
        tags_result = analysis.get("tagsResult", {})
        values = tags_result.get("values") if isinstance(tags_result, dict) else []
        for item in values or []:
            if isinstance(item, dict) and item.get("name"):
                scenes.append(
                    {
                        "tag": self._slug(str(item["name"])),
                        "confidence": self._float_value(item.get("confidence"), 0.0),
                    }
                )
        return {
            "model_version": "azure-vision-image-analysis",
            "provider": "azure_vision",
            "objects": objects,
            "scenes": scenes,
            "raw_provider_status": "completed",
        }

    def _tencent_ocr(self, payload: dict[str, Any]) -> dict[str, Any]:
        image_bytes, _content_type = self._first_image_bytes(payload)
        if not image_bytes:
            raise GatewayError("no extracted frame image is available for Tencent OCR", HTTPStatus.BAD_REQUEST)

        params = {
            "ImageBase64": base64.b64encode(image_bytes).decode("ascii"),
        }
        data = self._call_tencent_ocr_api(params)
        detections = data.get("TextDetections") if isinstance(data, dict) else []
        items: list[dict[str, Any]] = []
        for detection in detections or []:
            if not isinstance(detection, dict):
                continue
            text = detection.get("DetectedText")
            if not text:
                continue
            items.append(
                {
                    "frame_id": "frame_001",
                    "text": str(text),
                    "confidence": self._confidence_value(detection.get("Confidence"), 0.0),
                    "bbox": detection.get("Polygon") or detection.get("ItemPolygon") or [],
                }
            )
        return {
            "model_version": f"tencent-ocr-{self.settings.tencent_ocr_action}",
            "provider": "tencent_ocr",
            "items": items,
            "raw_provider_status": "completed",
            "request_id": data.get("RequestId", ""),
        }

    def _call_tencent_asr_api(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._call_tencent_api(
            params=params,
            endpoint=self.settings.tencent_asr_endpoint,
            service="asr",
            action=self.settings.tencent_asr_action,
            version=self.settings.tencent_asr_version,
            region=self.settings.tencent_region,
            product_name="ASR",
        )

    def _call_tencent_ocr_api(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._call_tencent_api(
            params=params,
            endpoint=self.settings.tencent_ocr_endpoint,
            service="ocr",
            action=self.settings.tencent_ocr_action,
            version=self.settings.tencent_ocr_version,
            region=self.settings.tencent_region,
            product_name="OCR",
        )

    def _call_tencent_api(
        self,
        *,
        params: dict[str, Any],
        endpoint: str,
        service: str,
        action: str,
        version: str,
        region: str,
        product_name: str,
    ) -> dict[str, Any]:
        if not self.settings.tencent_secret_id or not self.settings.tencent_secret_key:
            raise GatewayError(f"Tencent {product_name} secret id/key are not configured", HTTPStatus.BAD_GATEWAY)

        endpoint = endpoint.rstrip("/")
        host = urllib.parse.urlparse(endpoint).netloc or f"{service}.tencentcloudapi.com"
        timestamp = int(time.time())
        date = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
        payload = json.dumps(params, ensure_ascii=False, separators=(",", ":"))

        authorization = self._tencent_authorization(
            payload=payload,
            host=host,
            service=service,
            timestamp=timestamp,
            date=date,
        )
        headers = {
            "Authorization": authorization,
            "Content-Type": "application/json; charset=utf-8",
            "Host": host,
            "X-TC-Action": action,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": version,
        }
        if region:
            headers["X-TC-Region"] = region
        request = urllib.request.Request(endpoint, data=payload.encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.settings.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GatewayError(f"Tencent {product_name} request failed: {exc}", HTTPStatus.BAD_GATEWAY) from exc
        try:
            raw = json.loads(body)
        except json.JSONDecodeError as exc:
            raise GatewayError(f"Tencent {product_name} returned invalid JSON", HTTPStatus.BAD_GATEWAY) from exc
        if not isinstance(raw, dict):
            raise GatewayError(f"Tencent {product_name} JSON response must be an object", HTTPStatus.BAD_GATEWAY)
        response = raw.get("Response", raw)
        if not isinstance(response, dict):
            raise GatewayError(f"Tencent {product_name} response payload must be an object", HTTPStatus.BAD_GATEWAY)
        if isinstance(response.get("Error"), dict):
            error = response["Error"]
            code = error.get("Code", "Unknown")
            message = error.get("Message", "")
            raise GatewayError(f"Tencent {product_name} error {code}: {message}", HTTPStatus.BAD_GATEWAY)
        return response

    def _tencent_authorization(
        self,
        *,
        payload: str,
        host: str,
        service: str,
        timestamp: int,
        date: str,
    ) -> str:
        algorithm = "TC3-HMAC-SHA256"
        canonical_headers = (
            "content-type:application/json; charset=utf-8\n"
            f"host:{host}\n"
        )
        signed_headers = "content-type;host"
        hashed_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        canonical_request = "\n".join(
            [
                "POST",
                "/",
                "",
                canonical_headers,
                signed_headers,
                hashed_payload,
            ]
        )
        credential_scope = f"{date}/{service}/tc3_request"
        string_to_sign = "\n".join(
            [
                algorithm,
                str(timestamp),
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        secret_date = hmac.new(
            ("TC3" + self.settings.tencent_secret_key).encode("utf-8"),
            date.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        secret_service = hmac.new(secret_date, service.encode("utf-8"), hashlib.sha256).digest()
        secret_signing = hmac.new(secret_service, b"tc3_request", hashlib.sha256).digest()
        signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        return (
            f"{algorithm} Credential={self.settings.tencent_secret_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )

    def _call_azure_image_analysis(self, payload: dict[str, Any], features: tuple[str, ...]) -> dict[str, Any]:
        if not self.settings.azure_vision_endpoint or not self.settings.azure_vision_key:
            raise GatewayError("Azure Vision endpoint/key are not configured", HTTPStatus.BAD_GATEWAY)
        image_bytes, content_type = self._first_image_bytes(payload)
        if not image_bytes:
            raise GatewayError("no extracted frame image is available for Azure Vision", HTTPStatus.BAD_REQUEST)
        endpoint = self.settings.azure_vision_endpoint.rstrip("/")
        query = urllib.parse.urlencode(
            {"api-version": self.settings.azure_vision_api_version, "features": ",".join(features)}
        )
        request = urllib.request.Request(
            f"{endpoint}/computervision/imageanalysis:analyze?{query}",
            data=image_bytes,
            headers={"Content-Type": content_type, "Ocp-Apim-Subscription-Key": self.settings.azure_vision_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GatewayError(f"Azure Vision request failed: {exc}", HTTPStatus.BAD_GATEWAY) from exc
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise GatewayError("Azure Vision returned invalid JSON", HTTPStatus.BAD_GATEWAY) from exc
        if not isinstance(data, dict):
            raise GatewayError("Azure Vision JSON response must be an object", HTTPStatus.BAD_GATEWAY)
        return data

    def _first_image_bytes(self, payload: dict[str, Any]) -> tuple[bytes, str]:
        frames = payload.get("frames") if isinstance(payload.get("frames"), list) else []
        candidates: list[str] = []
        for frame in frames:
            if isinstance(frame, dict):
                for key in ("thumbnail_path", "local_path", "path"):
                    if frame.get(key):
                        candidates.append(str(frame[key]))
        if payload.get("local_path") and self._looks_like_image(str(payload["local_path"])):
            candidates.append(str(payload["local_path"]))
        for candidate in candidates:
            path = Path(candidate)
            if path.is_file():
                content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                return path.read_bytes(), content_type
        return b"", "application/octet-stream"

    def _first_audio_bytes(self, payload: dict[str, Any]) -> tuple[bytes, str]:
        for key in ("audio_path", "local_path", "path"):
            value = payload.get(key)
            if not value:
                continue
            path = Path(str(value))
            if not path.is_file():
                continue
            voice_format = self._voice_format_for_path(path)
            if voice_format:
                return path.read_bytes(), voice_format
            return self._extract_audio_for_asr(path)
        raise GatewayError("no local media file is available for Tencent ASR", HTTPStatus.BAD_REQUEST)

    def _extract_audio_for_asr(self, source: Path) -> tuple[bytes, str]:
        voice_format = self.settings.tencent_asr_voice_format.lower().strip() or "wav"
        if voice_format not in {"wav", "mp3", "m4a", "aac"}:
            raise GatewayError(f"unsupported Tencent ASR extraction format: {voice_format}", HTTPStatus.BAD_REQUEST)
        ffmpeg = self.settings.ffmpeg_path or shutil.which("ffmpeg")
        if not ffmpeg:
            raise GatewayError("ffmpeg is required to extract audio for Tencent ASR", HTTPStatus.BAD_REQUEST)

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / f"asr_audio.{voice_format}"
            command = [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(source),
                "-vn",
                "-t",
                "60",
                "-ac",
                "1",
                "-ar",
                "16000",
                str(target),
            ]
            try:
                completed = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise GatewayError(f"ffmpeg failed to extract audio for Tencent ASR: {exc}", HTTPStatus.BAD_REQUEST) from exc
            if completed.returncode != 0 or not target.is_file():
                detail = (completed.stderr or "unknown ffmpeg error").strip()
                raise GatewayError(f"ffmpeg could not extract audio for Tencent ASR: {detail}", HTTPStatus.BAD_REQUEST)
            return target.read_bytes(), voice_format

    def _voice_format_for_path(self, path: Path) -> str:
        suffix = path.suffix.lower().lstrip(".")
        if suffix in {"wav", "pcm", "speex", "silk", "mp3", "m4a", "aac", "amr"}:
            return suffix
        if suffix in {"ogg", "opus"}:
            return "ogg-opus"
        return ""

    def _content_metadata(self, payload: dict[str, Any]) -> dict[str, str]:
        value = payload.get("content_metadata")
        return value if isinstance(value, dict) else {}

    def _combined_text(self, payload: dict[str, Any]) -> str:
        metadata = self._content_metadata(payload)
        parts = [str(metadata.get("title", "")), str(metadata.get("description", ""))]
        frames = payload.get("frames") if isinstance(payload.get("frames"), list) else []
        parts.extend(str(frame.get("caption", "")) for frame in frames if isinstance(frame, dict))
        return " ".join(part for part in parts if part)

    def _duration_hint(self, payload: dict[str, Any]) -> int:
        meta = payload.get("video_meta") if isinstance(payload.get("video_meta"), dict) else {}
        try:
            return max(1000, int(meta.get("duration_ms") or 12000))
        except (TypeError, ValueError):
            return 12000

    def _looks_like_image(self, value: str) -> bool:
        return Path(value).suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

    def _float_value(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _int_value(self, value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _confidence_value(self, value: Any, default: float) -> float:
        confidence = self._float_value(value, default)
        if confidence > 1:
            confidence = confidence / 100
        return min(max(confidence, 0.0), 1.0)

    def _slug(self, value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9_ -]+", "", value.strip().lower())
        return re.sub(r"\s+", "_", slug) or "visual_scene"


class GatewayError(RuntimeError):
    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.status = status


class ModelGatewayHandler(BaseHTTPRequestHandler):
    server_version = "VGP-Model-Gateway/1.0"

    @property
    def gateway(self) -> ModelGateway:
        return self.server.gateway  # type: ignore[attr-defined]

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(self.gateway.health())
            return
        self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if not self._authorized():
            self._json({"error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
            return
        try:
            payload = self._read_json()
            if self.path == "/asr":
                result = self.gateway.asr(payload)
            elif self.path == "/ocr":
                result = self.gateway.ocr(payload)
            elif self.path == "/vision":
                result = self.gateway.vision(payload)
            else:
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            self._json(result)
        except GatewayError as exc:
            self._json({"error": str(exc)}, exc.status)
        except Exception as exc:  # pragma: no cover - final defensive boundary
            self._json({"error": "gateway internal error", "detail": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _authorized(self) -> bool:
        api_key = self.gateway.settings.api_key
        if not api_key:
            return True
        return self.headers.get("Authorization") == f"Bearer {api_key}"

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise GatewayError("request body must be valid JSON") from exc
        if not isinstance(data, dict):
            raise GatewayError("request body must be a JSON object")
        return data

    def _json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args: Any) -> None:
        if self.path != "/health":
            super().log_message(format, *args)


class ModelGatewayServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], gateway: ModelGateway):
        super().__init__(address, ModelGatewayHandler)
        self.gateway = gateway


def create_server(host: str | None = None, port: int | None = None) -> ModelGatewayServer:
    settings = gateway_settings()
    gateway = ModelGateway(settings)
    return ModelGatewayServer((host or settings.host, port if port is not None else settings.port), gateway)


def main() -> int:
    server = create_server()
    host, port = server.server_address
    print(f"model gateway listening on http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
