from pathlib import Path

from src.quant.pit.alfred import download_alfred


def test_missing_key_is_explicitly_blocked(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    result = download_alfred(tmp_path, tmp_path / "manifest.json")
    assert result["status"] == "BLOCKED_EXTERNAL_FRED_KEY"
