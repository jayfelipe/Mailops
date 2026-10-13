import base64

from mailops import dkim

# structurally-valid fake DERs: the modulus is garbage bytes but the
# DER walk only cares about structure, not crypto validity
FAKE_2048 = (
    b"\x30\x82\x01\x22"
    b"\x30\x0d\x06\x09\x2a\x86\x48\x86\xf7\x0d\x01\x01\x01\x05\x00"
    b"\x03\x82\x01\x0f\x00"
    b"\x30\x82\x01\x0a"
    b"\x02\x82\x01\x01\x00" + b"\xff" * 256 +
    b"\x02\x03\x01\x00\x01"
)

FAKE_1024 = (
    b"\x30\x81\x9f"
    b"\x30\x0d\x06\x09\x2a\x86\x48\x86\xf7\x0d\x01\x01\x01\x05\x00"
    b"\x03\x81\x8d\x00"
    b"\x30\x81\x89"
    b"\x02\x81\x81\x00" + b"\xff" * 128 +
    b"\x02\x03\x01\x00\x01"
)


def test_modulus_2048():
    assert dkim.rsa_modulus_bits(FAKE_2048) == 2048


def test_modulus_1024():
    assert dkim.rsa_modulus_bits(FAKE_1024) == 1024


def test_parse_tags():
    tags = dkim.parse_tags("v=DKIM1; h=sha256; k=rsa; p=abc")
    assert tags["h"] == "sha256"
    assert tags["k"] == "rsa"


def test_missing_p():
    out = dkim.check_record("v=DKIM1; k=rsa")
    assert any("no p=" in i for i in out["issues"])


def test_empty_p_is_revoked():
    out = dkim.check_record("v=DKIM1; k=rsa; p=")
    assert any("revoked" in i for i in out["issues"])


def test_weak_key_flagged():
    p = base64.b64encode(FAKE_1024).decode()
    out = dkim.check_record(f"v=DKIM1; k=rsa; p={p}")
    assert out["bits"] == 1024
    assert any("1024" in i for i in out["issues"])


def test_2048_is_clean():
    p = base64.b64encode(FAKE_2048).decode()
    out = dkim.check_record(f"v=DKIM1; k=rsa; p={p}")
    assert out["issues"] == []


def test_testing_mode_flagged():
    p = base64.b64encode(FAKE_2048).decode()
    out = dkim.check_record(f"v=DKIM1; k=rsa; t=y; p={p}")
    assert any("testing" in i for i in out["issues"])


def test_garbage_base64():
    out = dkim.check_record("v=DKIM1; k=rsa; p=!!!notbase64!!!")
    assert any("base64" in i for i in out["issues"])