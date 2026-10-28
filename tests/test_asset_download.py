"""Network-free integrity checks for resumable public asset downloads."""
import hashlib
import importlib.util
import io
from pathlib import Path
import pytest


@pytest.fixture
def downloader():
    path=Path(__file__).resolve().parents[1]/"scripts/download-assets.py"
    spec=importlib.util.spec_from_file_location("asset_downloader",path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_large_download_retains_prefix_and_verifies(monkeypatch,tmp_path,downloader):
    payload=b"a real model payload for integrity testing"
    target=tmp_path/"weights.safetensors"
    target.with_name(target.name+".part").write_bytes(payload[:5])
    def request(req,timeout):
        assert req.headers["Range"]==f"bytes=5-{len(payload)-1}"
        response=io.BytesIO(payload[5:]); response.status=206
        response.headers={"Content-Range":f"bytes 5-{len(payload)-1}/{len(payload)}"}
        return response
    monkeypatch.setattr(downloader.urllib.request,"urlopen",request)
    downloader.fetch_large("https://example.invalid/model",target,hashlib.sha256(payload).hexdigest(),len(payload))
    assert target.read_bytes()==payload


def test_range_server_must_honor_requested_offset(monkeypatch,tmp_path,downloader):
    def request(req,timeout):
        response=io.BytesIO(b"incorrect response"); response.status=200; response.headers={}
        return response
    monkeypatch.setattr(downloader.urllib.request,"urlopen",request)
    target=tmp_path/"weights.safetensors"
    with pytest.raises(ValueError,match="bounded range"):
        downloader.fetch_large("https://example.invalid/model",target,"bad",18)
    assert not target.exists()
