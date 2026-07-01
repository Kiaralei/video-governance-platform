from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .config import settings
from .media_assets import MediaAssetStore
from .modality_models import ModalityModelRunner


class EvidenceExtractor:
    """Best-effort video evidence extractor with graceful local fallbacks."""

    def __init__(self, evidence_root: Path | None = None):
        self.evidence_root = evidence_root or settings.evidence_dir

    def extract(self, video_url: str, content_id: str, title: str, description: str) -> dict[str, Any]:
        source = (video_url or "").strip()
        notes: list[str] = []
        frames: list[dict[str, Any]] = []
        availability = self._base_availability()
        asset = MediaAssetStore().prepare(source, content_id)
        video_meta: dict[str, Any] = {
            "source": asset["source"],
            "source_type": asset["source_type"],
            "asset_id": asset["asset_id"],
            "asset_status": asset["status"],
            "storage_uri": asset["storage_uri"],
            "duration_ms": None,
        }

        for field in ("local_path", "sha256", "file_size_bytes", "mime_type", "extension"):
            if asset.get(field) is not None:
                video_meta[field] = asset[field]
        if asset["source_type"] == "remote_url":
            video_meta["source_url"] = source
        if asset.get("error"):
            notes.append(asset["error"])

        if asset["status"] == "stored" and asset.get("local_path"):
            availability["video_source"]["available"] = True
            availability["video_source"]["mode"] = "stored_asset"
            path = Path(asset["local_path"])
            probe_meta = self._probe_video(path, availability, notes)
            video_meta.update(probe_meta)
            frames = self._extract_frames(path, content_id, availability, notes)
            if not frames:
                notes.append("No keyframes were extracted; the pipeline will keep text-derived frame evidence.")
        elif asset["status"] == "remote_reference":
            availability["video_source"]["available"] = True
            availability["video_source"]["mode"] = "remote_reference"
            notes.append("Remote video URL was recorded as an asset reference but not downloaded.")
        else:
            notes.append("Video binary is unavailable; using title and description as text-only evidence.")

        model_result = ModalityModelRunner().extract(
            media_asset=asset,
            video_meta=video_meta,
            frames=frames,
            title=title,
            description=description,
        )
        self._merge_model_availability(availability, model_result)

        return self._result(video_meta, frames, availability, notes, asset, model_result)

    def _result(
        self,
        video_meta: dict[str, Any],
        frames: list[dict[str, Any]],
        availability: dict[str, Any],
        notes: list[str],
        media_asset: dict[str, Any],
        model_result: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "media_asset": media_asset,
            "video_meta": video_meta,
            "frames": frames,
            "asr_transcript": model_result["asr_transcript"],
            "ocr_results": model_result["ocr_results"],
            "object_detections": model_result["object_detections"],
            "scene_tags": model_result["scene_tags"],
            "modality_model_invocations": model_result["modality_model_invocations"],
            "modality_availability": availability,
            "extraction_notes": notes,
        }

    def _base_availability(self) -> dict[str, Any]:
        ffprobe_path = settings.ffprobe_path or shutil.which("ffprobe")
        ffmpeg_path = settings.ffmpeg_path or shutil.which("ffmpeg")
        return {
            "video_source": {"available": False, "mode": "none"},
            "ffprobe": {"available": bool(ffprobe_path), "path": ffprobe_path},
            "ffmpeg": {"available": bool(ffmpeg_path), "path": ffmpeg_path},
            "video_metadata": {"available": False, "source": None},
            "frame_extraction": {"available": False, "extracted_count": 0},
            "asr": {"available": False, "source": "metadata_description_fallback"},
            "ocr": {"available": False, "source": "metadata_title_fallback"},
            "object_detection": {"available": False, "source": "not_configured"},
            "scene_classification": {"available": False, "source": "fallback"},
        }

    def _merge_model_availability(self, availability: dict[str, Any], model_result: dict[str, Any]) -> None:
        statuses = {
            item["modality"]: item["status"]
            for item in model_result["modality_model_invocations"]
            if "modality" in item and "status" in item
        }
        if statuses.get("asr") == "completed":
            availability["asr"] = {"available": True, "source": "external_asr"}
        if statuses.get("ocr") == "completed":
            availability["ocr"] = {"available": True, "source": "external_ocr"}
        if statuses.get("vision") == "completed":
            availability["object_detection"] = {"available": True, "source": "external_vision"}
            availability["scene_classification"] = {"available": True, "source": "external_vision"}

    def _probe_video(
        self,
        path: Path,
        availability: dict[str, Any],
        notes: list[str],
    ) -> dict[str, Any]:
        tool = availability["ffprobe"]["path"]
        if not tool:
            notes.append("ffprobe is not installed; duration, resolution, and codec metadata are unavailable.")
            return {}

        command = [
            tool,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,width,height",
            "-of",
            "json",
            str(path),
        ]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            notes.append(f"ffprobe failed: {exc}")
            return {}

        if completed.returncode != 0:
            detail = (completed.stderr or "unknown ffprobe error").strip()
            notes.append(f"ffprobe could not parse the file: {detail}")
            return {}

        try:
            payload = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError as exc:
            notes.append(f"ffprobe returned invalid JSON: {exc}")
            return {}

        meta: dict[str, Any] = {}
        duration = payload.get("format", {}).get("duration")
        if duration is not None:
            try:
                meta["duration_ms"] = int(float(duration) * 1000)
            except (TypeError, ValueError):
                pass

        for stream in payload.get("streams", []):
            if stream.get("codec_type") == "video":
                meta["width"] = stream.get("width")
                meta["height"] = stream.get("height")
                meta["video_codec"] = stream.get("codec_name")
                break

        availability["video_metadata"]["available"] = bool(meta)
        availability["video_metadata"]["source"] = "ffprobe" if meta else None
        return meta

    def _extract_frames(
        self,
        path: Path,
        content_id: str,
        availability: dict[str, Any],
        notes: list[str],
    ) -> list[dict[str, Any]]:
        tool = availability["ffmpeg"]["path"]
        if not tool:
            notes.append("ffmpeg is not installed; keyframe extraction is skipped.")
            return []

        target_dir = self.evidence_root / content_id
        target_dir.mkdir(parents=True, exist_ok=True)
        pattern = target_dir / "frame_%03d.jpg"
        command = [
            tool,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-vf",
            "fps=1/15,scale=320:-1",
            "-frames:v",
            "3",
            str(pattern),
        ]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            notes.append(f"ffmpeg failed: {exc}")
            return []

        if completed.returncode != 0:
            detail = (completed.stderr or "unknown ffmpeg error").strip()
            notes.append(f"ffmpeg could not extract keyframes: {detail}")
            return []

        frames: list[dict[str, Any]] = []
        for index, frame_path in enumerate(sorted(target_dir.glob("frame_*.jpg")), start=1):
            frames.append(
                {
                    "frame_id": f"frame_{index:03d}",
                    "timestamp_ms": (index - 1) * 15000,
                    "thumbnail": "",
                    "thumbnail_path": str(frame_path),
                    "caption": f"Extracted keyframe {index}",
                }
            )

        availability["frame_extraction"]["available"] = bool(frames)
        availability["frame_extraction"]["extracted_count"] = len(frames)
        return frames
