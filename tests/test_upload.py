import io
from pathlib import Path
from fastapi.testclient import TestClient


def test_upload_valid_pdf(client: TestClient):
    """Test uploading a valid PDF document through the API."""
    file_content = b"%PDF-1.4 sample pdf content for invoice test"
    files = {"file": ("test_invoice.pdf", io.BytesIO(file_content), "application/pdf")}

    response = client.post("/api/v1/invoices/upload", files=files)
    assert response.status_code == 201
    data = response.json()

    assert data["id"] is not None
    assert data["original_filename"] == "test_invoice.pdf"
    assert data["status"] == "UPLOADED"
    assert data["file_size_bytes"] == len(file_content)
    assert "stored_filename" in data
    assert Path(data["file_path"]).exists()


def test_upload_valid_image(client: TestClient):
    """Test uploading a valid PNG image file through the API."""
    file_content = b"\x89PNG\r\n\x1a\nfake png header and content"
    files = {"file": ("receipt_scan.png", io.BytesIO(file_content), "image/png")}

    response = client.post("/api/v1/invoices/upload", files=files)
    assert response.status_code == 201
    data = response.json()

    assert data["id"] is not None
    assert data["original_filename"] == "receipt_scan.png"
    assert data["status"] == "UPLOADED"
    assert Path(data["file_path"]).exists()


def test_upload_invalid_file_extension(client: TestClient):
    """Test that unsupported file extensions are rejected with 400 Bad Request."""
    file_content = b"Plain text file content"
    files = {"file": ("notes.txt", io.BytesIO(file_content), "text/plain")}

    response = client.post("/api/v1/invoices/upload", files=files)
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "Unsupported file extension" in detail


def test_upload_empty_file(client: TestClient):
    """Test that 0-byte uploaded files are rejected with 400 Bad Request."""
    files = {"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")}

    response = client.post("/api/v1/invoices/upload", files=files)
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "empty" in detail.lower()


def test_list_and_get_uploaded_invoices(client: TestClient):
    """Test retrieving invoices list and single invoice by ID."""
    # Upload two invoices
    client.post(
        "/api/v1/invoices/upload",
        files={"file": ("inv1.pdf", io.BytesIO(b"file 1 content"), "application/pdf")},
    )
    client.post(
        "/api/v1/invoices/upload",
        files={"file": ("inv2.jpg", io.BytesIO(b"file 2 content"), "image/jpeg")},
    )

    # List all
    list_resp = client.get("/api/v1/invoices")
    assert list_resp.status_code == 200
    invoices = list_resp.json()
    assert len(invoices) >= 2

    first_id = invoices[0]["id"]
    get_resp = client.get(f"/api/v1/invoices/{first_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == first_id

    # 404 for non-existent invoice
    not_found_resp = client.get("/api/v1/invoices/999999")
    assert not_found_resp.status_code == 404
