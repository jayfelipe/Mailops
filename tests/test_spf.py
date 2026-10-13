from mailops import spf


def test_counts_include_and_mx():
    assert spf.count_lookups("v=spf1 include:_spf.google.com mx -all") == 2


def test_qualifier_still_counts():
    assert spf.count_lookups("v=spf1 ~include:_spf.example.com -all") == 1


def test_redirect_counts():
    assert spf.count_lookups("v=spf1 redirect=_spf.google.com") == 1


def test_ip_mechanisms_are_free():
    assert spf.count_lookups("v=spf1 ip4:192.0.2.0/24 ip6:2001:db8::/32 -all") == 0


def test_cidr_syntax_counts():
    assert spf.count_lookups("v=spf1 a/24 mx -all") == 2


def test_over_limit_flags():
    rec = "v=spf1 " + " ".join(f"include:spf{i}.example.com" for i in range(11)) + " -all"
    assert any("lookups" in i for i in spf.issues(rec))


def test_plus_all_flags():
    assert any("+all" in i for i in spf.issues("v=spf1 ip4:192.0.2.1 +all"))


def test_missing_all_flags():
    assert any("'all'" in i for i in spf.issues("v=spf1 ip4:192.0.2.1"))


def test_redirect_does_not_need_all():
    assert spf.issues("v=spf1 redirect=_spf.google.com") == []