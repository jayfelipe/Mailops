from mailops import dmarc


def test_parse_basic():
    tags = dmarc.parse("v=DMARC1; p=quarantine; rua=mailto:d@example.com")
    assert tags["p"] == "quarantine"
    assert tags["rua"] == "mailto:d@example.com"


def test_parse_missing_semicolon_is_malformed():
    assert dmarc.parse("v=DMARC1 p=reject") is None


def test_wrong_version_is_ignored():
    assert dmarc.parse("v=DMARC2; p=reject") is None


def test_missing_p_flags():
    found = dmarc.issues({"v": "DMARC1", "rua": "mailto:x@y.com"})
    assert any("p= missing" in i for i in found)


def test_invalid_p_flags():
    found = dmarc.issues({"v": "DMARC1", "p": "block"})
    assert any("not a valid policy" in i for i in found)


def test_none_policy_flags():
    found = dmarc.issues({"v": "DMARC1", "p": "none"})
    assert any("monitor-only" in i for i in found)


def test_strict_policy_with_reports_is_clean():
    assert dmarc.issues({"v": "DMARC1", "p": "reject", "rua": "mailto:x@y.com"}) == []


def test_partial_pct_flags():
    found = dmarc.issues({"v": "DMARC1", "p": "reject", "rua": "mailto:x@y.com", "pct": "50"})
    assert any("pct=50" in i for i in found)


def test_missing_rua_flags():
    found = dmarc.issues({"v": "DMARC1", "p": "reject"})
    assert any("rua" in i for i in found)


def test_typo_tag_flags():
    found = dmarc.issues({"v": "DMARC1", "p": "reject", "rua": "mailto:x@y.com", "polciy": "x"})
    assert any("polciy" in i for i in found)