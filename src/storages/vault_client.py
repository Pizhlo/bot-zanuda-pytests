from typing import Any, cast

import httpx


class VaultClient:
    """HTTP-клиент для чтения секретов из HashiCorp Vault (KV v2)."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        mount_point: str = "secret",
        timeout: int = 10,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.mount_point = mount_point.strip("/")
        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"X-Vault-Token": token},
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "VaultClient":
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()

    def read_secret(self, path: str) -> dict[str, Any]:
        """Читает секрет из KV v2 по пути внутри mount_point."""
        normalized_path = path.strip("/")
        response = self.client.get(f"/v1/{self.mount_point}/data/{normalized_path}")
        response.raise_for_status()
        payload = cast(dict[str, Any], response.json())
        data_wrapper = cast(dict[str, Any], payload["data"])
        return cast(dict[str, Any], data_wrapper["data"])

    def get_client_secret(self, client_id: str, secrets_path: str = "auth/clients") -> str:
        """Возвращает client_secret из секрета по пути <secrets_path>/<client_id>."""
        secret = self.read_secret(f"{secrets_path.rstrip('/')}/{client_id}")
        client_secret = secret.get("api_key")
        if not isinstance(client_secret, str) or not client_secret:
            raise KeyError(f"api_key for client_id='{client_id}' not found in Vault")
        return client_secret

    def write_secret(self, path: str, body: dict[str, Any]) -> None:
        """Записывает KV v2 по логическому пути (без префикса data/)."""
        normalized_path = path.strip("/")
        response = self.client.post(
            f"/v1/{self.mount_point}/data/{normalized_path}",
            json={"data": body},
        )
        response.raise_for_status()

    def delete_secret_metadata(self, path: str) -> None:
        """Удаляет метаданные и все версии секрета KV v2 (для сервера путь «пустой»)."""
        normalized_path = path.strip("/")
        response = self.client.delete(
            f"/v1/{self.mount_point}/metadata/{normalized_path}",
        )
        if response.status_code not in (200, 204):
            response.raise_for_status()
