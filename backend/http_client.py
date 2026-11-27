"""
Universal HTTP client providing seamless support across both:
1. Cloudflare Python Worker runtime (Pyodide / WASM using pyodide.http.pyfetch)
2. Local Python / pytest / development environment (using httpx.AsyncClient)
"""
import json
import asyncio
from typing import Any, Dict, Optional, Union
from urllib.parse import urlencode

try:
    import js
    import pyodide.http
    HAS_WORKER_FETCH = hasattr(js, "fetch") or hasattr(pyodide.http, "pyfetch")
except Exception:
    HAS_WORKER_FETCH = False

HAS_PYODIDE = HAS_WORKER_FETCH

if not HAS_PYODIDE:
    import httpx


class WorkerHttpResponse:
    def __init__(
        self,
        status_code: int,
        text: str,
        json_data: Any = None,
        headers: Optional[Dict[str, str]] = None
    ):
        self.status_code = status_code
        self.text = text
        self._json_data = json_data
        self.headers = headers or {}

    @property
    def status(self) -> int:
        return self.status_code

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> Any:
        if self._json_data is not None:
            return self._json_data
        try:
            return json.loads(self.text)
        except Exception:
            return {}


async def async_http_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    data: Optional[Union[Dict[str, Any], str]] = None,
    json_data: Optional[Any] = None,
    timeout: float = 15.0
) -> WorkerHttpResponse:
    """
    Executes an async HTTP request using pyfetch inside Cloudflare Workers
    or httpx in local/test Python environments.
    """
    final_url = url
    if params:
        query_string = urlencode({k: v for k, v in params.items() if v is not None}, doseq=True)
        sep = "&" if "?" in final_url else "?"
        final_url = f"{final_url}{sep}{query_string}"

    req_headers = dict(headers or {})

    if HAS_PYODIDE:
        fetch_kwargs: Dict[str, Any] = {"method": method.upper()}
        if json_data is not None:
            fetch_kwargs["body"] = json.dumps(json_data)
            req_headers["Content-Type"] = "application/json"
        elif data is not None:
            if isinstance(data, dict):
                fetch_kwargs["body"] = urlencode(data)
                req_headers["Content-Type"] = "application/x-www-form-urlencoded"
            else:
                fetch_kwargs["body"] = str(data)

        if req_headers:
            fetch_kwargs["headers"] = req_headers

        py_res = await pyodide.http.pyfetch(final_url, **fetch_kwargs)
        body_text = await py_res.string()

        parsed_json = None
        try:
            parsed_json = json.loads(body_text)
        except Exception:
            pass

        res_headers: Dict[str, str] = {}
        try:
            if hasattr(py_res, "headers"):
                for k in py_res.headers:
                    res_headers[k.lower()] = py_res.headers.get(k)
        except Exception:
            pass

        return WorkerHttpResponse(
            status_code=py_res.status,
            text=body_text,
            json_data=parsed_json,
            headers=res_headers
        )
    else:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(
                method=method.upper(),
                url=final_url,
                headers=req_headers,
                data=data if data is not None and not isinstance(data, dict) else (data or None),
                json=json_data
            )
            parsed_json = None
            try:
                parsed_json = resp.json()
            except Exception:
                pass
            return WorkerHttpResponse(
                status_code=resp.status_code,
                text=resp.text,
                json_data=parsed_json,
                headers=dict(resp.headers)
            )


async def http_get(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: float = 15.0
) -> WorkerHttpResponse:
    return await async_http_request(url, method="GET", headers=headers, params=params, timeout=timeout)


async def http_post(
    url: str,
    data: Optional[Any] = None,
    json_data: Optional[Any] = None,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: float = 15.0
) -> WorkerHttpResponse:
    return await async_http_request(url, method="POST", headers=headers, params=params, data=data, json_data=json_data, timeout=timeout)
