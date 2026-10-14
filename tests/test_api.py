from mailops import api


def test_valid_email():
    assert api.valid_email("lead@example.com")
    assert not api.valid_email("nope")
    assert not api.valid_email("a b@c.com")
    assert not api.valid_email("sin@tld")


def test_welcome_job_defaults():
    subject, body = api.welcome_job(None)
    assert "there" in subject
    assert "worker" in body


def test_welcome_job_with_name():
    subject, _ = api.welcome_job("Ana")
    assert "Ana" in subject