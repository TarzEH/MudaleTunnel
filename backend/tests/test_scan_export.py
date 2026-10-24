"""Tests for exporting stored scan results (``mudale scan export``)."""

from __future__ import annotations

import csv
import io
import json

import pytest

from mudale_cli.main import EXIT_ERROR, EXIT_OK, main
from mudale_core.export import CSV_COLUMNS, ExportError, export_scan
from mudale_core.state import StateDB


@pytest.fixture
def db(tmp_path, monkeypatch):
    db = StateDB(tmp_path / "mudale.db")
    ws = db.ensure_default_workspace()
    rec = db.create_scan(ws.id, "10.0.0.0/24", "quick")
    db.add_service(rec.id, host="10.0.0.5", hostname="web.local", port=80,
                   service_name="http", product="nginx", version="1.25")
    db.add_service(rec.id, host="10.0.0.5", hostname="web.local", port=22,
                   service_name="ssh", product="OpenSSH", version="9.6")
    # A value with a comma and a double quote exercises CSV escaping.
    db.add_service(rec.id, host="10.0.0.9", port=8080, service_name="http-proxy",
                   product='Acme "Proxy", Inc', extra_info="protocol 2,0")
    monkeypatch.setattr("mudale_core.state.DEFAULT_DB_PATH", db.db_path)
    return db, rec


def test_json_structure(db):
    d, rec = db
    data = json.loads(export_scan(d, rec.id, "json"))
    assert data["schema_version"] == 1
    assert data["scan"]["id"] == rec.id
    assert data["scan"]["target"] == "10.0.0.0/24"
    assert data["scan"]["profile"] == "quick"
    assert data["scan"]["queued_at"].endswith("+00:00")
    assert data["scan"]["started_at"] is None
    hosts = {h["host"]: h for h in data["hosts"]}
    assert set(hosts) == {"10.0.0.5", "10.0.0.9"}
    assert hosts["10.0.0.5"]["hostname"] == "web.local"
    assert [p["port"] for p in hosts["10.0.0.5"]["ports"]] == [22, 80]
    assert hosts["10.0.0.5"]["ports"][1]["product"] == "nginx"


def test_csv_header_rows_and_escaping(db):
    d, rec = db
    text = export_scan(d, rec.id, "csv")
    rows = list(csv.reader(io.StringIO(text, newline="")))
    assert tuple(rows[0]) == CSV_COLUMNS
    assert len(rows) == 4  # header + one row per host/port
    proxy = next(r for r in rows[1:] if r[3] == "8080")
    assert proxy[CSV_COLUMNS.index("product")] == 'Acme "Proxy", Inc'
    assert proxy[CSV_COLUMNS.index("extra_info")] == "protocol 2,0"
    assert '"Acme ""Proxy"", Inc"' in text


def test_unknown_scan_raises(db):
    d, _ = db
    with pytest.raises(ExportError, match="not found"):
        export_scan(d, 999, "json")


def test_bad_format_raises(db):
    d, rec = db
    with pytest.raises(ExportError, match="Unsupported format"):
        export_scan(d, rec.id, "xml")


def test_cli_stdout_json(db, capsys):
    _, rec = db
    assert main(["scan", "export", str(rec.id)]) == EXIT_OK
    assert json.loads(capsys.readouterr().out)["scan"]["id"] == rec.id


def test_cli_output_file_csv(db, tmp_path):
    _, rec = db
    out = tmp_path / "scan.csv"
    assert main(["scan", "export", str(rec.id), "-f", "csv", "-o", str(out)]) == EXIT_OK
    with open(out, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert tuple(rows[0]) == CSV_COLUMNS and len(rows) == 4


def test_cli_unknown_scan_id(db, capsys):
    assert main(["scan", "export", "999"]) == EXIT_ERROR
    assert "not found" in capsys.readouterr().err


def test_cli_bad_format(db, capsys):
    _, rec = db
    with pytest.raises(SystemExit) as exc:
        main(["scan", "export", str(rec.id), "--format", "xml"])
    assert exc.value.code != 0
    assert "invalid choice" in capsys.readouterr().err
