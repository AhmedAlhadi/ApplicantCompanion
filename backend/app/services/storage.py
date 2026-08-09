"""Object storage abstraction: MinIO in production, local filesystem in dev (§3)."""
from __future__ import annotations

from pathlib import Path

from ..config import get_settings


class ObjectStore:
    def put(self, key: str, data: bytes, content_type: str = "") -> str:  # pragma: no cover
        raise NotImplementedError

    def get(self, key: str) -> bytes:  # pragma: no cover
        raise NotImplementedError


class LocalObjectStore(ObjectStore):
    def __init__(self):
        self.root = Path(get_settings().local_storage_path)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = Path(key)
        if safe.is_absolute() or ".." in safe.parts:
            raise ValueError("Invalid object key")
        return self.root / key

    def put(self, key: str, data: bytes, content_type: str = "") -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()


class MinioObjectStore(ObjectStore):
    def __init__(self):
        from minio import Minio

        settings = get_settings()
        self._bucket = settings.minio_bucket
        self._client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)

    def put(self, key: str, data: bytes, content_type: str = "") -> str:
        import io

        self._client.put_object(
            self._bucket, key, io.BytesIO(data), len(data), content_type=content_type or None
        )
        return key

    def get(self, key: str) -> bytes:
        response = self._client.get_object(self._bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()


_store: ObjectStore | None = None


def get_object_store() -> ObjectStore:
    global _store
    if _store is None:
        settings = get_settings()
        if settings.object_store == "minio":
            try:
                _store = MinioObjectStore()
            except Exception:
                _store = LocalObjectStore()
        else:
            _store = LocalObjectStore()
    return _store


def reset_object_store() -> None:
    global _store
    _store = None
