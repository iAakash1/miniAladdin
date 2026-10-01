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
