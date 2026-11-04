from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router
from app.repositories.schemas import ParsedFileRecord
from app.services.file_upload_parser import SensitiveContentError, UploadFileParseError


class FakeFileRepo:
    def __init__(self):
        self.records: list[ParsedFileRecord] = []

    def create(self, record: ParsedFileRecord) -> ParsedFileRecord:
        self.records.append(record)
        return record


def make_client(monkeypatch):
    from app.api import routes

    repo = FakeFileRepo()
    monkeypatch.setattr(routes, "_get_file_repo", lambda: repo)
    monkeypatch.setattr(routes, "_check_user_scope", lambda scope: None)
    monkeypatch.setattr(routes, "check_sensitive_content", lambda text, filename: None)

    app = FastAPI()
    app.include_router(router)
    return TestClient(app), repo


def test_upload_txt_parses_and_persists(monkeypatch):
    client, repo = make_client(monkeypatch)

    response = client.post(
        "/v1/files/upload",
        files={"file": ("claim.txt", b"graphene improves conductivity", "text/plain")},
        headers={"X-User-Scope": "nstl_user_demo"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["fileId"].startswith("file_")
    assert payload["type"] == "txt"
    assert payload["content_size"] > 0
    assert repo.records[0].content == "graphene improves conductivity"
    assert repo.records[0].source == "server_upload"


def test_upload_rejects_unsupported_type(monkeypatch):
    client, _ = make_client(monkeypatch)

    response = client.post(
        "/v1/files/upload",
        files={"file": ("claim.docx", b"binary", "application/octet-stream")},
        headers={"X-User-Scope": "nstl_user_demo"},
    )

    assert response.status_code == 422
    assert "格式不支持" in response.json()["detail"]


def test_upload_rejects_oversized_file(monkeypatch):
    from app.api import routes

    client, _ = make_client(monkeypatch)
    monkeypatch.setattr(routes, "CONSISTENCY_EVALUATION_MAX_UPLOAD_FILE_BYTES", 4)

    response = client.post(
        "/v1/files/upload",
        files={"file": ("claim.txt", b"too large", "text/plain")},
        headers={"X-User-Scope": "nstl_user_demo"},
    )

    assert response.status_code == 413
    assert "文件过大" in response.json()["detail"]


def test_upload_reports_sensitive_content(monkeypatch):
    from app.api import routes

    client, _ = make_client(monkeypatch)

    def fake_sensitive(text, filename):
        raise SensitiveContentError()

    monkeypatch.setattr(routes, "check_sensitive_content", fake_sensitive)
    response = client.post(
        "/v1/files/upload",
        files={"file": ("claim.txt", b"sensitive", "text/plain")},
        headers={"X-User-Scope": "nstl_user_demo"},
    )

    assert response.status_code == 422
    assert "敏感词命中" in response.json()["detail"]


def test_upload_reports_pdf_parse_failure(monkeypatch):
    from app.api import routes

    client, _ = make_client(monkeypatch)

    def fake_parse(content, file_type, filename):
        raise UploadFileParseError("PDF 损坏或无法解析，请确认文件没有损坏、未加密后重新上传。")

    monkeypatch.setattr(routes, "parse_uploaded_file_content", fake_parse)
    response = client.post(
        "/v1/files/upload",
        files={"file": ("broken.pdf", b"%PDF-broken", "application/pdf")},
        headers={"X-User-Scope": "nstl_user_demo"},
    )

    assert response.status_code == 422
    assert "PDF 损坏" in response.json()["detail"]
