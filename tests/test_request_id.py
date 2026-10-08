"""Request ids: adopted from the proxy when well-formed, never written raw."""

from fastapi.testclient import TestClient

import api.index as api


def test_the_proxy_request_id_is_adopted_and_echoed():
    response = TestClient(api.app).get("/api/health", headers={"X-Request-Id": "proxy-request-0001"})
    assert response.headers["X-Request-Id"] == "proxy-request-0001"


def test_a_malformed_request_id_is_replaced_not_logged():
    response = TestClient(api.app).get("/api/health", headers={"X-Request-Id": "x\r\nlevel=CRITICAL forged"})
    echoed = response.headers["X-Request-Id"]
    assert echoed != "x\r\nlevel=CRITICAL forged"
    assert len(echoed) == 12 and echoed.isalnum()


def test_health_names_the_cloud_run_revision_without_leaking_configuration(monkeypatch):
    """A revision deployed without GIT_COMMIT must still be identifiable.

    Production ran for weeks on a revision that reported commit "unknown", so
    nothing on the service could be matched to a build. Cloud Run injects the
    revision name itself; health repeats it, and nothing else from the
    environment.
    """
    from fastapi.testclient import TestClient
    import api.index as api

    monkeypatch.setenv("K_REVISION", "omnisignal-api-poc-00001-wql")
    monkeypatch.setenv("SOME_SECRET_TOKEN", "must-not-appear")
    body = TestClient(api.app).get("/api/health").json()

    assert body["revision"] == "omnisignal-api-poc-00001-wql"
    assert "must-not-appear" not in str(body)


def test_health_revision_is_null_off_cloud_run(monkeypatch):
    from fastapi.testclient import TestClient
    import api.index as api

    monkeypatch.delenv("K_REVISION", raising=False)
    assert TestClient(api.app).get("/api/health").json()["revision"] is None


def test_every_response_names_the_build_that_answered(monkeypatch):
    """Read through the website, this is how an operator sees which backend it calls."""
    monkeypatch.setattr(api, "_BUILD_COMMIT", "0123456789ab")
    monkeypatch.setenv("K_REVISION", "omnisignal-api-poc-release-0123456")
    client = TestClient(api.app)
    for path in ("/api/health", "/api/no-such-route"):
        response = client.get(path)
        assert response.headers["X-Backend-Commit"] == "0123456789ab", path
        assert response.headers["X-Backend-Revision"] == "omnisignal-api-poc-release-0123456", path


def test_the_revision_header_is_absent_off_cloud_run(monkeypatch):
    monkeypatch.delenv("K_REVISION", raising=False)
    response = TestClient(api.app).get("/api/health")
    assert "X-Backend-Revision" not in response.headers
    assert response.headers["X-Backend-Commit"]


def test_the_build_headers_carry_no_configuration(monkeypatch):
    monkeypatch.setenv("SOME_SECRET_TOKEN", "must-not-appear")
    response = TestClient(api.app).get("/api/health")
    assert "must-not-appear" not in str(dict(response.headers))
