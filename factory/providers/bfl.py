from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from pathlib import Path
from typing import Callable

from ..io import sha256_file


class BFLProviderError(RuntimeError):
    pass


JsonTransport = Callable[[str, str, dict, dict | None], dict]
DownloadTransport = Callable[[str, Path], None]


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _default_http_json(
    method: str,
    url: str,
    headers: dict,
    payload: dict | None,
) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def _default_download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "BlenderAssetFactory/1"})
    with urllib.request.urlopen(request, timeout=180) as response:
        destination.write_bytes(response.read())


class BFLClient:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "flux-2-pro",
        base_url: str = "https://api.bfl.ai/v1",
        http_json: JsonTransport = _default_http_json,
        download: DownloadTransport = _default_download,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise BFLProviderError("BFL API key is required")
        self._api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._http_json = http_json
        self._download = download
        self._sleep = sleep

    def generate(
        self,
        *,
        prompt: str,
        reference_urls: list[str],
        output_path: Path,
        seed: int,
        width: int = 1536,
        height: int = 1024,
        timeout_seconds: int = 300,
    ) -> dict:
        if not prompt.strip():
            raise BFLProviderError("prompt is required")
        if not reference_urls:
            raise BFLProviderError("at least one reference image is required")
        if len(reference_urls) > 8:
            raise BFLProviderError("BFL API supports at most eight reference images")
        if width <= 0 or height <= 0:
            raise BFLProviderError("output dimensions must be positive")

        payload: dict = {
            "prompt": prompt,
            "width": width,
            "height": height,
            "seed": seed,
            "output_format": "png",
        }
        for index, url in enumerate(reference_urls, start=1):
            field = "input_image" if index == 1 else f"input_image_{index}"
            payload[field] = url

        headers = {
            "accept": "application/json",
            "x-key": self._api_key,
            "Content-Type": "application/json",
        }
        submission = self._http_json(
            "POST", f"{self.base_url}/{self.model}", headers, payload
        )
        request_id = submission.get("id")
        polling_url = submission.get("polling_url")
        if not request_id or not polling_url:
            raise BFLProviderError(f"BFL submission did not return a job: {submission}")

        deadline = time.monotonic() + timeout_seconds
        result: dict | None = None
        while time.monotonic() < deadline:
            result = self._http_json("GET", polling_url, headers, None)
            status = result.get("status")
            if status == "Ready":
                break
            if status in {"Error", "Failed"}:
                raise BFLProviderError(f"BFL generation failed: {result}")
            self._sleep(0.5)
        else:
            raise BFLProviderError(f"BFL generation timed out: {request_id}")

        sample_url = (result or {}).get("result", {}).get("sample")
        if not sample_url:
            raise BFLProviderError(f"BFL result did not include an image: {result}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._download(sample_url, output_path)
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise BFLProviderError("BFL output download is empty")

        workflow = {
            "provider": "black-forest-labs",
            "model": self.model,
            "width": width,
            "height": height,
            "reference_urls": reference_urls,
            "output_format": "png",
        }
        workflow_json = json.dumps(workflow, sort_keys=True, separators=(",", ":"))
        return {
            "provider": "black-forest-labs",
            "model": self.model,
            "request_id": request_id,
            "seed": seed,
            "prompt_sha256": _sha256_text(prompt),
            "workflow_sha256": _sha256_text(workflow_json),
            "output": str(output_path),
            "output_sha256": sha256_file(output_path),
        }
