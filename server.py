from __future__ import annotations

import argparse
import json
import mimetypes
import os
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
OUTPUTS_DIR = ROOT / "outputs"

SERVICE_NAME = "3Dto2DVerify"
SERVICE_VERSION = "0.1.0"
MAX_BODY_BYTES = 2 * 1024 * 1024

PUBLIC_ASSETS = {
    "/assets/tech_overview.png": ROOT / "tech_overview.png",
    "/assets/solution.pdf": ROOT / "Autonomous 4K Metrology Solution.pdf",
}

OVERVIEW = {
    "name": SERVICE_NAME,
    "version": SERVICE_VERSION,
    "description": "3D CAD 기준과 2D 카메라 촬영 이미지를 비교해 치수 검증 결과를 제공하는 웹 서비스",
    "capabilities": [
        "STEP/IGES/DXF 기반 검증 기준 관리",
        "2D 카메라 이미지와 CAD 투영 기준 비교",
        "치수 오차 기반 Pass/Warning/Fail 판정",
        "MES/ERP 연동을 위한 JSON API",
        "검증 이력과 문의 로그 저장",
    ],
    "endpoints": {
        "GET /": "웹 콘솔",
        "GET /health": "서비스 상태 확인",
        "GET /api/overview": "서비스 메타데이터",
        "GET /api/sample-report": "샘플 검증 리포트",
        "POST /api/verify": "치수 검증 판정",
        "POST /api/contact": "문의 저장",
    },
}

DEFAULT_PRIMITIVES = [
    {
        "id": "top_hole_01",
        "type": "circle",
        "expected_mm": 5.000,
        "measured_mm": 4.987,
        "tolerance_mm": 0.050,
    },
    {
        "id": "mount_slot_02",
        "type": "slot",
        "expected_mm": 18.500,
        "measured_mm": 18.541,
        "tolerance_mm": 0.050,
    },
    {
        "id": "edge_width_03",
        "type": "line",
        "expected_mm": 42.000,
        "measured_mm": 42.063,
        "tolerance_mm": 0.050,
    },
]


class ServiceError(Exception):
    def __init__(self, status: int, message: str, details: Any | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.details = details


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def env_port(default: int = 8000) -> int:
    value = os.environ.get("PORT")
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def as_float(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ServiceError(400, f"{field} must be a number") from exc
    if number != number or number in (float("inf"), float("-inf")):
        raise ServiceError(400, f"{field} must be a finite number")
    return number


def as_positive_float(value: Any, field: str) -> float:
    number = as_float(value, field)
    if number <= 0:
        raise ServiceError(400, f"{field} must be greater than zero")
    return number


def clean_text(value: Any, default: str, max_length: int = 160) -> str:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    return text[:max_length]


def evaluate_report(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    if not isinstance(payload, dict):
        raise ServiceError(400, "request body must be a JSON object")

    part_id = clean_text(payload.get("part_id"), "PART-DEMO-001")
    default_tolerance = as_positive_float(payload.get("tolerance_mm", 0.05), "tolerance_mm")
    warning_ratio = as_positive_float(payload.get("warning_ratio", 0.8), "warning_ratio")
    warning_ratio = min(warning_ratio, 1.0)

    primitives = payload.get("primitives") or DEFAULT_PRIMITIVES
    if not isinstance(primitives, list) or not primitives:
        raise ServiceError(400, "primitives must be a non-empty array")

    rows: list[dict[str, Any]] = []
    summary = {"total": 0, "pass": 0, "warning": 0, "fail": 0}

    for index, primitive in enumerate(primitives, start=1):
        if not isinstance(primitive, dict):
            raise ServiceError(400, f"primitives[{index - 1}] must be an object")

        expected = as_float(primitive.get("expected_mm"), f"primitives[{index - 1}].expected_mm")
        measured = as_float(primitive.get("measured_mm"), f"primitives[{index - 1}].measured_mm")
        tolerance = as_positive_float(
            primitive.get("tolerance_mm", default_tolerance),
            f"primitives[{index - 1}].tolerance_mm",
        )

        error = measured - expected
        abs_error = abs(error)
        if abs_error > tolerance:
            verdict = "FAIL"
            summary["fail"] += 1
        elif abs_error >= tolerance * warning_ratio:
            verdict = "WARNING"
            summary["warning"] += 1
        else:
            verdict = "PASS"
            summary["pass"] += 1

        summary["total"] += 1
        rows.append(
            {
                "id": clean_text(primitive.get("id"), f"feature_{index}", 80),
                "type": clean_text(primitive.get("type"), "dimension", 40),
                "verdict": verdict,
                "expected_mm": round(expected, 4),
                "measured_mm": round(measured, 4),
                "error_mm": round(error, 4),
                "abs_error_mm": round(abs_error, 4),
                "tolerance_mm": round(tolerance, 4),
            }
        )

    overall = "FAIL" if summary["fail"] else "WARNING" if summary["warning"] else "PASS"

    return {
        "inspection_id": f"INSP-{uuid.uuid4().hex[:10].upper()}",
        "part_id": part_id,
        "timestamp": utc_now(),
        "overall": overall,
        "summary": summary,
        "primitives": rows,
    }


def store_contact(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ServiceError(400, "request body must be a JSON object")

    name = clean_text(payload.get("name"), "", 80)
    email = clean_text(payload.get("email"), "", 120)
    company = clean_text(payload.get("company"), "", 120)
    message = clean_text(payload.get("message"), "", 2000)

    if not name:
        raise ServiceError(400, "name is required")
    if "@" not in email:
        raise ServiceError(400, "valid email is required")
    if len(message) < 5:
        raise ServiceError(400, "message must be at least 5 characters")

    contact = {
        "id": f"MSG-{uuid.uuid4().hex[:8].upper()}",
        "timestamp": utc_now(),
        "name": name,
        "email": email,
        "company": company,
        "message": message,
    }

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    with (OUTPUTS_DIR / "contact_messages.jsonl").open("a", encoding="utf-8") as file:
        file.write(json.dumps(contact, ensure_ascii=False) + "\n")

    return {"accepted": True, "message_id": contact["id"]}


class RequestHandler(BaseHTTPRequestHandler):
    server_version = f"{SERVICE_NAME}/{SERVICE_VERSION}"

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        path = urlsplit(self.path).path

        if path in ("", "/", "/index.html"):
            self.serve_file(WEB_ROOT / "index.html")
            return

        if path == "/health":
            self.send_json(
                200,
                {
                    "status": "ok",
                    "service": SERVICE_NAME,
                    "version": SERVICE_VERSION,
                    "timestamp": utc_now(),
                },
            )
            return

        if path == "/api/overview":
            self.send_json(200, OVERVIEW)
            return

        if path == "/api/sample-report":
            self.send_json(200, evaluate_report({"part_id": "PART-DEMO-001"}))
            return

        if path in PUBLIC_ASSETS:
            self.serve_file(PUBLIC_ASSETS[path])
            return

        if path.startswith("/static/"):
            self.serve_file(WEB_ROOT / path.removeprefix("/static/"))
            return

        self.send_json(404, {"error": "not_found", "message": f"No route for {path}"})

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        try:
            payload = self.read_json()
            if path == "/api/verify":
                self.send_json(200, evaluate_report(payload))
                return
            if path == "/api/contact":
                self.send_json(202, store_contact(payload))
                return
            self.send_json(404, {"error": "not_found", "message": f"No route for {path}"})
        except ServiceError as exc:
            body: dict[str, Any] = {"error": "bad_request", "message": exc.message}
            if exc.details is not None:
                body["details"] = exc.details
            self.send_json(exc.status, body)
        except Exception as exc:  # pragma: no cover - keeps the service responsive in production.
            self.send_json(500, {"error": "internal_error", "message": str(exc)})

    def read_json(self) -> dict[str, Any]:
        length_header = self.headers.get("Content-Length")
        if not length_header:
            raise ServiceError(400, "Content-Length is required")

        try:
            length = int(length_header)
        except ValueError as exc:
            raise ServiceError(400, "Content-Length must be an integer") from exc

        if length < 0 or length > MAX_BODY_BYTES:
            raise ServiceError(413, "request body is too large")

        raw = self.rfile.read(length)
        if not raw:
            raise ServiceError(400, "request body is empty")

        try:
            payload = json.loads(raw.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise ServiceError(400, "request body must be UTF-8") from exc
        except json.JSONDecodeError as exc:
            raise ServiceError(400, "request body must be valid JSON", {"line": exc.lineno, "column": exc.colno}) from exc

        if not isinstance(payload, dict):
            raise ServiceError(400, "request body must be a JSON object")
        return payload

    def serve_file(self, file_path: Path) -> None:
        try:
            resolved = file_path.resolve(strict=True)
        except FileNotFoundError:
            self.send_json(404, {"error": "not_found", "message": "file not found"})
            return

        web_root = WEB_ROOT.resolve()
        root = ROOT.resolve()
        public_asset_paths = {path.resolve() for path in PUBLIC_ASSETS.values()}
        allowed = resolved in public_asset_paths or resolved == web_root / "index.html" or web_root in resolved.parents
        if not allowed or not resolved.is_file() or (root not in resolved.parents and resolved != root):
            self.send_json(403, {"error": "forbidden", "message": "file is outside the public web root"})
            return

        content_type, _ = mimetypes.guess_type(str(resolved))
        if content_type is None:
            content_type = "application/octet-stream"
        if content_type.startswith("text/") or resolved.suffix in {".js", ".css", ".html"}:
            content_type += "; charset=utf-8"

        data = resolved.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{utc_now()}] {self.address_string()} {fmt % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the 3Dto2DVerify web service.")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"), help="Bind host. Use 0.0.0.0 for LAN access.")
    parser.add_argument("--port", default=env_port(), type=int, help="Bind port. Defaults to the PORT environment variable.")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), RequestHandler)
    host, port = server.server_address
    print(f"{SERVICE_NAME} is running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
