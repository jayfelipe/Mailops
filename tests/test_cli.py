from mailops import cli


def test_run_checks_aggregates(monkeypatch):
    seen = {}

    monkeypatch.setattr("mailops.spf.check", lambda d: {"status": "ok", "issues": []})
    monkeypatch.setattr("mailops.dmarc.check", lambda d: {"status": "ok", "issues": []})
    monkeypatch.setattr(
        "mailops.dkim.check",
        lambda d, s=None: seen.update(domain=d, selector=s) or {"selectors": {}, "issues": []},
    )

    r = cli.run_checks("example.com", selector="google")
    assert r["domain"] == "example.com"
    assert set(r) == {"domain", "spf", "dmarc", "dkim"}
    assert seen == {"domain": "example.com", "selector": "google"}