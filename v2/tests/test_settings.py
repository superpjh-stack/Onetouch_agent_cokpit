import os
import stat
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from onetouch_agent.data_hub import OnetouchRepository
from v2.api import create_app

KEY = 'sk-' + 'test-key_' * 5


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    path = tmp_path / '.env'
    path.write_text('# keep\nOTHER=value\nOPENAI_API_KEY=old\nexport OPENAI_API_KEY=duplicate\n')
    app = create_app(OnetouchRepository(tmp_path / 'db.sqlite'), settings_file=path)
    client = TestClient(app, base_url='http://localhost', client=('127.0.0.1', 1000))
    return client, path


def provider(monkeypatch, status=200, failure=False):
    class FakeHTTP:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url, **kwargs):
            if failure:
                raise httpx.ConnectError('sensitive provider detail')
            return SimpleNamespace(status_code=status, is_error=status >= 400)
    monkeypatch.setattr('v2.api.httpx.AsyncClient', FakeHTTP)


def test_key_persistence_and_no_disclosure(setup, monkeypatch):
    client, path = setup
    provider(monkeypatch)
    result = client.post('/api/settings/openai', json={'api_key': KEY}, headers={'Origin': 'http://localhost'})
    assert result.status_code == 200
    assert KEY not in result.text
    assert KEY not in client.get('/api/workspace').text
    assert client.get('/api/workspace').json()['meta']['ai_configured']
    assert path.read_text() == f"# keep\nOTHER=value\nOPENAI_API_KEY='{KEY}'\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert os.environ['OPENAI_API_KEY'] == KEY


@pytest.mark.parametrize('headers', [{}, {'Origin': 'https://evil.example'}, {'Origin': 'http://localhost', 'Forwarded': ''}, {'Origin': 'http://localhost', 'Forwarded': 'for=127.0.0.1'}, {'Origin': 'http://localhost', 'X-Forwarded-For': '127.0.0.1'}])
def test_settings_origin_and_proxy_boundary(setup, headers):
    client, path = setup
    before = path.read_bytes()
    assert client.post('/api/settings/openai', json={'api_key': KEY}, headers=headers).status_code == 403
    assert path.read_bytes() == before


def test_remote_cannot_save_even_with_access_code(setup, monkeypatch):
    client, path = setup
    monkeypatch.setenv('COCKPIT_ACCESS_TOKEN', 'test-code')
    remote = TestClient(client.app, base_url='http://localhost', client=('203.0.113.1', 1000))
    assert remote.post('/api/settings/openai', json={'api_key': KEY}, headers={'Origin': 'http://localhost', 'Authorization': 'Bearer test-code'}).status_code == 403


@pytest.mark.parametrize('key', ["sk-'injection", 123, '', 'sk-abc\nOTHER=bad'])
def test_invalid_keys_not_echoed(setup, key):
    client, path = setup
    before = path.read_bytes()
    result = client.post('/api/settings/openai', json={'api_key': key}, headers={'Origin': 'http://localhost'})
    assert result.status_code == 422
    assert path.read_bytes() == before


@pytest.mark.parametrize('status,expected', [(401,422),(403,422),(404,422),(429,502),(500,502)])
def test_provider_rejection_preserves_key(setup, monkeypatch, status, expected):
    client, path = setup
    before = path.read_bytes()
    provider(monkeypatch, status)
    result = client.post('/api/settings/openai', json={'api_key': KEY}, headers={'Origin': 'http://localhost'})
    assert result.status_code == expected
    assert path.read_bytes() == before
    assert 'OPENAI_API_KEY' not in os.environ


def test_network_and_disk_failures(setup, monkeypatch):
    client, path = setup
    before = path.read_bytes()
    provider(monkeypatch, failure=True)
    result = client.post('/api/settings/openai', json={'api_key': KEY}, headers={'Origin': 'http://localhost'})
    assert result.status_code == 502
    assert 'sensitive' not in result.text
    provider(monkeypatch)
    def fail(*args): raise OSError('sensitive disk detail')
    monkeypatch.setattr('v2.openai_settings.os.replace', fail)
    result = client.post('/api/settings/openai', json={'api_key': KEY}, headers={'Origin': 'http://localhost'})
    assert result.status_code == 500
    assert path.read_bytes() == before
    assert not list(path.parent.glob('.openai-config-*'))
    assert 'OPENAI_API_KEY' not in os.environ


def test_oversized_settings_body(setup):
    client, _ = setup
    assert client.post('/api/settings/openai', content='x'*4097, headers={'Origin':'http://localhost'}).status_code == 413
