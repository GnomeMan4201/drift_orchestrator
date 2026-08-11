from gateway_adapter import RouteRequest, health, route


def test_gateway_route_contract(monkeypatch):
    monkeypatch.setattr("gateway_adapter.call_ollama", lambda prompt, model: "model-output")

    result = route(RouteRequest(prompt="probe", drift_score=0.25, tier="fast"))

    assert result.response == "model-output"
    assert result.tier == "fast"
    assert result.drift_score == 0.25
    assert result.model
    assert result.request_id
    assert result.latency_ms >= 0


def test_gateway_health_contract():
    result = health()
    assert result["status"] == "ok"
    assert result["ollama"].startswith("http")
    assert result["model"]
