from __future__ import annotations

from io import BytesIO
from typing import Iterable

from minio import Minio
from minio.error import S3Error

from app.core.config import settings


class ObjectStorageClient:
    def __init__(self):
        self._client = Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    @property
    def datasets_bucket(self) -> str:
        return settings.minio_bucket_datasets

    @property
    def results_bucket(self) -> str:
        return settings.minio_bucket_results

    @property
    def exports_bucket(self) -> str:
        return settings.minio_bucket_exports

    def ensure_buckets(self) -> None:
        for bucket in (self.datasets_bucket, self.results_bucket, self.exports_bucket):
            if not self._client.bucket_exists(bucket):
                self._client.make_bucket(bucket)

    def put_bytes(self, bucket: str, object_key: str, payload: bytes, content_type: str) -> None:
        bio = BytesIO(payload)
        self._client.put_object(
            bucket_name=bucket,
            object_name=object_key,
            data=bio,
            length=len(payload),
            content_type=content_type,
        )

    def get_bytes(self, bucket: str, object_key: str) -> bytes:
        response = self._client.get_object(bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def object_exists(self, bucket: str, object_key: str) -> bool:
        try:
            self._client.stat_object(bucket, object_key)
            return True
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject"}:
                return False
            raise

    def healthcheck(self) -> None:
        self._client.bucket_exists(self.datasets_bucket)

    def delete_object(self, bucket: str, object_key: str) -> None:
        self._client.remove_object(bucket, object_key)

    def iter_object(self, bucket: str, object_key: str) -> Iterable[bytes]:
        response = self._client.get_object(bucket, object_key)
        try:
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            response.close()
            response.release_conn()


storage_client = ObjectStorageClient()
