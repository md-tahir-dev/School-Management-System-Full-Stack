from app.core.config import settings
from app.core.ratelimit import SlidingWindowLimiter
from tests.conftest import login


def test_limiter_blocks_after_limit_and_reports_retry_time():
    lim = SlidingWindowLimiter()
    assert [lim.hit("k", 3, 60) for _ in range(3)] == [0, 0, 0]
    retry = lim.hit("k", 3, 60)
    assert 1 <= retry <= 60
    assert lim.hit("other", 3, 60) == 0  # keys are independent


async def test_login_endpoint_is_rate_limited_per_ip(client, monkeypatch):
    monkeypatch.setattr(settings, "login_ip_limit", 3)
    statuses = [(await login(client, "nobody", "x")).status_code for _ in range(5)]
    assert statuses == [401, 401, 401, 429, 429]
    resp = await login(client, "nobody", "x")
    assert resp.json()["code"] == "RATE_LIMITED"
    assert "retry-after" in resp.headers
