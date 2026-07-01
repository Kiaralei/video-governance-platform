from __future__ import annotations

import hashlib
import mimetypes
import shutil
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlparse
from urllib.request import url2pathname
from uuid import uuid4

from .config import ROOT_DIR, settings


class MediaAssetStore:
    """Local object-store substitute for video assets.

    The interface is intentionally storage-shaped so the backend can later swap
    the local filesystem paths for S3/MinIO object keys without changing the
    evidence package contract.
    """

    def __init__(self, media_root: Path | None = None):
        self.media_root = media_root or settings.media_dir

    def prepare(self, source: str, content_id: str) -> dict:
        source = (source or "").strip()
        asset = self._base_asset(source=source, content_id=content_id)
        if not source:
            asset.update({"status": "missing", "error": "No video source was provided."})
            return asset

        if self._is_remote_url(source):
            return self._prepare_remote(source, asset)

        return self._prepare_local(self._local_path_from_source(source), asset)

    def _base_asset(self, source: str, content_id: str) -> dict:
        return {
            "asset_id": f"asset_{uuid4().hex[:12]}",
            "content_id": content_id,
            "source": source,
            "source_type": "missing",
            "status": "pending",
            "storage_backend": "local_fs",
            "storage_uri": None,
            "local_path": None,
            "sha256": None,
            "file_size_bytes": None,
            "mime_type": None,
            "extension": None,
            "error": None,
            "max_media_bytes": settings.max_media_bytes,
        }

    def _prepare_remote(self, source: str, asset: dict) -> dict:
        asset.update({"source_type": "remote_url"})
        if not settings.enable_remote_download:
            asset.update(
                {
                    "status": "remote_reference",
                    "storage_uri": source,
                    "error": "Remote download is disabled. Set VGP_ENABLE_REMOTE_DOWNLOAD=true to fetch remote videos.",
                }
            )
            return asset

        try:
            request = urllib.request.Request(source, headers={"User-Agent": "video-governance-platform/1.0"})
            with urllib.request.urlopen(request, timeout=settings.remote_download_timeout_seconds) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > settings.max_media_bytes:
                    asset.update(
                        {
                            "status": "rejected_size",
                            "error": f"Remote file exceeds VGP_MAX_MEDIA_BYTES ({settings.max_media_bytes}).",
                        }
                    )
                    return asset
                suffix = self._suffix_from_url(source, response.headers.get("Content-Type"))
                return self._store_stream(response, asset, suffix)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            asset.update({"status": "failed", "error": f"Remote download failed: {exc}"})
            return asset

    def _prepare_local(self, path: Path, asset: dict) -> dict:
        asset.update({"source_type": "local_file", "source": str(path)})
        if not path.exists() or not path.is_file():
            asset.update({"status": "missing", "error": f"Local video file was not found: {path}"})
            return asset

        size = path.stat().st_size
        if size > settings.max_media_bytes:
            asset.update(
                {
                    "status": "rejected_size",
                    "file_size_bytes": size,
                    "error": f"Local file exceeds VGP_MAX_MEDIA_BYTES ({settings.max_media_bytes}).",
                }
            )
            return asset

        sha256 = self._sha256(path)
        mime_type = mimetypes.guess_type(path.name)[0]
        extension = path.suffix.lower()
        if settings.copy_local_media:
            stored_path = self._stored_path(sha256, extension)
            stored_path.parent.mkdir(parents=True, exist_ok=True)
            if not stored_path.exists():
                shutil.copy2(path, stored_path)
        else:
            stored_path = path

        asset.update(
            {
                "status": "stored",
                "storage_uri": self._storage_uri(stored_path),
                "local_path": str(stored_path),
                "sha256": sha256,
                "file_size_bytes": size,
                "mime_type": mime_type,
                "extension": extension,
            }
        )
        return asset

    def _store_stream(self, stream: BinaryIO, asset: dict, suffix: str) -> dict:
        self.media_root.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        total = 0
        with tempfile.NamedTemporaryFile(delete=False, dir=self.media_root, suffix=".download") as temp:
            temp_path = Path(temp.name)
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > settings.max_media_bytes:
                    temp.close()
                    temp_path.unlink(missing_ok=True)
                    asset.update(
                        {
                            "status": "rejected_size",
                            "file_size_bytes": total,
                            "error": f"Downloaded file exceeds VGP_MAX_MEDIA_BYTES ({settings.max_media_bytes}).",
                        }
                    )
                    return asset
                digest.update(chunk)
                temp.write(chunk)

        sha256 = digest.hexdigest()
        stored_path = self._stored_path(sha256, suffix)
        stored_path.parent.mkdir(parents=True, exist_ok=True)
        if stored_path.exists():
            temp_path.unlink(missing_ok=True)
        else:
            temp_path.replace(stored_path)

        asset.update(
            {
                "status": "stored",
                "storage_uri": self._storage_uri(stored_path),
                "local_path": str(stored_path),
                "sha256": sha256,
                "file_size_bytes": total,
                "mime_type": mimetypes.guess_type(stored_path.name)[0],
                "extension": suffix,
            }
        )
        return asset

    def _stored_path(self, sha256: str, extension: str | None) -> Path:
        suffix = extension if extension and extension.startswith(".") else ".bin"
        return self.media_root / sha256[:2] / f"{sha256}{suffix}"

    def _storage_uri(self, path: Path) -> str:
        try:
            relative = path.resolve().relative_to(self.media_root.resolve())
        except ValueError:
            relative = path.resolve()
        return f"local://media-assets/{relative.as_posix()}"

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _is_remote_url(self, source: str) -> bool:
        return urlparse(source).scheme in {"http", "https"}

    def _local_path_from_source(self, source: str) -> Path:
        if source.startswith("file://"):
            parsed = urlparse(source)
            raw_path = url2pathname(parsed.path)
            if len(raw_path) >= 4 and raw_path[0] == "/" and raw_path[2] == ":":
                raw_path = raw_path[1:]
            return Path(raw_path).expanduser().resolve()

        path = Path(source).expanduser()
        if not path.is_absolute():
            path = ROOT_DIR / path
        return path.resolve()

    def _suffix_from_url(self, source: str, content_type: str | None) -> str:
        suffix = Path(urlparse(source).path).suffix.lower()
        if suffix:
            return suffix
        if content_type:
            guessed = mimetypes.guess_extension(content_type.split(";", 1)[0].strip())
            if guessed:
                return guessed
        return ".bin"
