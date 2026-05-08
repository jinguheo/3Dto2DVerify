from __future__ import annotations

import argparse
import csv
import hmac
import io
import json
import mimetypes
import os
import smtplib
import sqlite3
import ssl
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
OUTPUTS_DIR = ROOT / "outputs"
DB_PATH = OUTPUTS_DIR / "verify.db"

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
        "GET /api/admin/contacts": "관리자 문의 목록",
        "GET /api/admin/inspections": "검증 이력 목록",
        "GET /admin/history": "검증 이력 관리 화면",
        "POST /api/admin/contacts/email": "관리자 문의 CSV 메일 발송",
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

CONTACT_FIELDS = ("id", "timestamp", "name", "email", "company", "message")


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


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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


def clean_header(value: Any, default: str, max_length: int = 160) -> str:
    return " ".join(clean_text(value, default, max_length).splitlines())


def smtp_config() -> dict[str, Any] | None:
    smtp_host = clean_text(os.environ.get("SMTP_HOST"), "", 255)
    if not smtp_host:
        return None

    smtp_ssl = env_bool("SMTP_SSL", False)
    smtp_starttls = env_bool("SMTP_STARTTLS", not smtp_ssl)
    smtp_port = 465 if smtp_ssl else 587
    if os.environ.get("SMTP_PORT"):
        try:
            smtp_port = int(os.environ["SMTP_PORT"])
        except ValueError as exc:
            raise RuntimeError("SMTP_PORT must be an integer") from exc

    return {
        "host": smtp_host,
        "port": smtp_port,
        "ssl": smtp_ssl,
        "starttls": smtp_starttls,
        "user": clean_text(os.environ.get("SMTP_USER"), "", 255),
        "password": os.environ.get("SMTP_PASSWORD", ""),
    }


def send_email_message(message: EmailMessage) -> None:
    config = smtp_config()
    if not config:
        raise RuntimeError("SMTP_HOST is not configured")

    context = ssl.create_default_context()
    if config["ssl"]:
        smtp: smtplib.SMTP = smtplib.SMTP_SSL(config["host"], config["port"], timeout=10, context=context)
    else:
        smtp = smtplib.SMTP(config["host"], config["port"], timeout=10)

    with smtp:
        if config["starttls"] and not config["ssl"]:
            smtp.starttls(context=context)
        if config["user"] and config["password"]:
            smtp.login(config["user"], config["password"])
        smtp.send_message(message)


def init_db() -> None:
    """Initializes the SQLite database with required tables."""
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        # Table for high-level inspection results
        conn.execute("""
            CREATE TABLE IF NOT EXISTS inspections (
                id TEXT PRIMARY KEY,
                part_id TEXT,
                timestamp TEXT,
                overall TEXT,
                total_count INTEGER,
                pass_count INTEGER,
                warning_count INTEGER,
                fail_count INTEGER
            )
        """)
        # Table for individual measurement primitives
        conn.execute("""
            CREATE TABLE IF NOT EXISTS primitives (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inspection_id TEXT,
                feature_id TEXT,
                type TEXT,
                verdict TEXT,
                expected_mm REAL,
                measured_mm REAL,
                error_mm REAL,
                tolerance_mm REAL,
                FOREIGN KEY(inspection_id) REFERENCES inspections(id)
            )
        """)
        # Table for contact inquiries (replacing JSONL)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id TEXT PRIMARY KEY,
                timestamp TEXT,
                name TEXT,
                email TEXT,
                company TEXT,
                message TEXT
            )
        """)


def store_inspection(report: dict[str, Any]) -> None:
    """Persists an inspection report to the database."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO inspections VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                report["inspection_id"], report["part_id"], report["timestamp"],
                report["overall"], report["summary"]["total"], report["summary"]["pass"],
                report["summary"]["warning"], report["summary"]["fail"]
            )
        )
        for p in report["primitives"]:
            conn.execute(
                "INSERT INTO primitives (inspection_id, feature_id, type, verdict, expected_mm, measured_mm, error_mm, tolerance_mm) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    report["inspection_id"], p["id"], p["type"], p["verdict"],
                    p["expected_mm"], p["measured_mm"], p["error_mm"], p["abs_error_mm"], p["tolerance_mm"]
                )
            )


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


def send_contact_email(contact: dict[str, str]) -> dict[str, bool]:
    recipient = clean_header(os.environ.get("CONTACT_EMAIL_TO"), "", 255)
    if not smtp_config() or not recipient:
        return {"email_configured": False, "email_sent": False}

    smtp_user = clean_text(os.environ.get("SMTP_USER"), "", 255)
    sender = (
        clean_header(os.environ.get("CONTACT_EMAIL_FROM"), "", 255)
        or clean_header(smtp_user, "", 255)
        or recipient
    )
    subject_prefix = clean_header(os.environ.get("CONTACT_EMAIL_SUBJECT_PREFIX"), "3Dto2DVerify inquiry", 80)

    message = EmailMessage()
    message["Subject"] = f"{subject_prefix}: {clean_header(contact['name'], 'New contact', 80)}"
    message["From"] = sender
    message["To"] = recipient
    message["Reply-To"] = formataddr(
        (clean_header(contact["name"], "", 80), clean_header(contact["email"], "", 120))
    )
    message.set_content(
        "\n".join(
            [
                "A new 3Dto2DVerify contact request was submitted.",
                "",
                f"Message ID: {contact['id']}",
                f"Timestamp: {contact['timestamp']}",
                f"Name: {contact['name']}",
                f"Email: {contact['email']}",
                f"Company: {contact['company'] or '-'}",
                "",
                "Message:",
                contact["message"],
            ]
        )
    )

    send_email_message(message)

    return {"email_configured": True, "email_sent": True}


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

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO contacts (id, timestamp, name, email, company, message) VALUES (?, ?, ?, ?, ?, ?)",
            (contact["id"], contact["timestamp"], contact["name"], 
             contact["email"], contact["company"], contact["message"])
        )

    try:
        email_status = send_contact_email(contact)
    except Exception as exc:
        print(f"[{utc_now()}] contact email failed for {contact['id']}: {exc}")
        email_status = {"email_configured": True, "email_sent": False}

    return {"accepted": True, "message_id": contact["id"], **email_status}


def load_contacts() -> list[dict[str, str]]:
    if not DB_PATH.exists():
        return []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM contacts ORDER BY timestamp DESC")
        return [dict(row) for row in cursor.fetchall()]


def load_inspections(limit: int = 100) -> list[dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM inspections ORDER BY timestamp DESC LIMIT ?", (limit,))
        return [dict(row) for row in cursor.fetchall()]


def contacts_to_csv(contacts: list[dict[str, str]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CONTACT_FIELDS)
    writer.writeheader()
    for contact in contacts:
        writer.writerow({field: contact.get(field, "") for field in CONTACT_FIELDS})
    return output.getvalue()


def send_contacts_export_email(recipient: str | None = None) -> dict[str, Any]:
    if not smtp_config():
        raise ServiceError(503, "SMTP_HOST is not configured")

    recipient = clean_header(
        recipient,
        "",
        255,
    ) or clean_header(os.environ.get("CONTACT_EXPORT_EMAIL_TO"), "", 255) or clean_header(
        os.environ.get("CONTACT_EMAIL_TO"), "", 255
    )
    if not recipient:
        raise ServiceError(400, "export recipient email is required")

    contacts = load_contacts()
    csv_data = contacts_to_csv(contacts)
    timestamp = utc_now().replace(":", "").replace("-", "")
    filename = f"3dto2dverify-contacts-{timestamp}.csv"
    smtp_user = clean_text(os.environ.get("SMTP_USER"), "", 255)
    sender = (
        clean_header(os.environ.get("CONTACT_EMAIL_FROM"), "", 255)
        or clean_header(smtp_user, "", 255)
        or recipient
    )

    message = EmailMessage()
    message["Subject"] = f"3Dto2DVerify contact export ({len(contacts)} messages)"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(
        "\n".join(
            [
                "Attached is the current 3Dto2DVerify contact export.",
                "",
                f"Generated at: {utc_now()}",
                f"Message count: {len(contacts)}",
            ]
        )
    )
    message.add_attachment(csv_data.encode("utf-8-sig"), maintype="text", subtype="csv", filename=filename)
    send_email_message(message)
    return {"email_sent": True, "recipient": recipient, "count": len(contacts), "filename": filename}


class RequestHandler(BaseHTTPRequestHandler):
    server_version = f"{SERVICE_NAME}/{SERVICE_VERSION}"

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Admin-Token, Authorization")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        request_url = urlsplit(self.path)
        path = request_url.path

        if path in ("", "/", "/index.html"):
            self.serve_file(WEB_ROOT / "index.html")
            return

        if path == "/admin/contacts":
            self.serve_file(WEB_ROOT / "contacts.html")
            return

        if path == "/admin/history":
            self.serve_file(WEB_ROOT / "history.html")
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

        if path == "/api/admin/contacts":
            try:
                self.require_admin()
                query = parse_qs(request_url.query)
                contacts = list(reversed(load_contacts()))
                limit = self.parse_limit(query.get("limit", ["200"])[0])
                visible_contacts = contacts[:limit]
                if query.get("format", ["json"])[0].lower() == "csv":
                    data = contacts_to_csv(visible_contacts).encode("utf-8-sig")
                    self.send_data(
                        200,
                        data,
                        "text/csv; charset=utf-8",
                        {
                            "Content-Disposition": 'attachment; filename="3dto2dverify-contacts.csv"',
                        },
                    )
                    return
                self.send_json(
                    200,
                    {
                        "count": len(contacts),
                        "returned": len(visible_contacts),
                        "contacts": visible_contacts,
                    },
                )
            except ServiceError as exc:
                self.send_service_error(exc)
            return

        if path == "/api/admin/inspections":
            try:
                self.require_admin()
                query = parse_qs(request_url.query)
                limit = self.parse_limit(query.get("limit", ["100"])[0])
                inspections = load_inspections(limit)
                self.send_json(200, {"count": len(inspections), "inspections": inspections})
            except ServiceError as exc:
                self.send_service_error(exc)
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
                report = evaluate_report(payload)
                store_inspection(report)
                self.send_json(200, report)
                return
            if path == "/api/contact":
                self.send_json(202, store_contact(payload))
                return
            if path == "/api/admin/contacts/email":
                self.require_admin()
                self.send_json(202, send_contacts_export_email(payload.get("recipient")))
                return
            self.send_json(404, {"error": "not_found", "message": f"No route for {path}"})
        except ServiceError as exc:
            self.send_service_error(exc)
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

    def require_admin(self) -> None:
        expected = os.environ.get("ADMIN_TOKEN", "")
        if not expected:
            raise ServiceError(503, "ADMIN_TOKEN is not configured")

        provided = self.headers.get("X-Admin-Token", "")
        authorization = self.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            provided = authorization.removeprefix("Bearer ").strip()

        if not provided or not hmac.compare_digest(provided, expected):
            raise ServiceError(401, "admin token is invalid")

    def parse_limit(self, value: str) -> int:
        try:
            limit = int(value)
        except ValueError as exc:
            raise ServiceError(400, "limit must be an integer") from exc
        return max(1, min(limit, 1000))

    def send_service_error(self, exc: ServiceError) -> None:
        body: dict[str, Any] = {"error": "request_failed", "message": exc.message}
        if exc.details is not None:
            body["details"] = exc.details
        self.send_json(exc.status, body)

    def send_data(
        self,
        status: int,
        data: bytes,
        content_type: str,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def serve_file(self, file_path: Path) -> None:
        try:
            resolved = file_path.resolve(strict=True)
        except FileNotFoundError:
            self.send_json(404, {"error": "not_found", "message": "file not found"})
            return

        web_root = WEB_ROOT.resolve()
        root = ROOT.resolve()
        public_asset_paths = {path.resolve() for path in PUBLIC_ASSETS.values()}
        allowed = resolved in public_asset_paths or web_root == resolved or web_root in resolved.parents
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
    init_db()
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
