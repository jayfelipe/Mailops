"""DKIM record discovery and checks (RFC 6376).

DKIM keys live at <selector>._domainkey.<domain> and there is no way to
list the selectors a domain actually uses. Discovery means probing names
that common providers publish under (google for Google Workspace,
selector1/selector2 for Microsoft 365, s1/s2 for SendGrid, ...) and
hoping one matches. Every deliverability tool has this same limitation.
"""

import base64

import dns.exception
import dns.resolver

PROBE_SELECTORS = [
    "google", "selector1", "selector2", "s1", "s2", "s3",
    "k1", "k2", "dkim", "default", "mail", "smtp", "api",
    "zendesk1", "zendesk2", "mailgun", "mandrill",
    "fm1", "fm2", "fm3", "cm1", "cm2", "em1", "em2", "ses",
]


def fetch(domain: str, selector: str) -> str | None:
    """Fetch the DKIM record for one selector, None if nothing is published."""
    try:
        answers = dns.resolver.resolve(f"{selector}._domainkey.{domain}", "TXT", lifetime=3)
    except dns.exception.DNSException:
        # probing expects misses, so any resolver failure here just means "not found"
        return None
    # TXT values over 255 chars are split into several strings that the
    # receiver concatenates; DKIM keys are almost always split
    return b"".join(answers[0].strings).decode("ascii", errors="replace")


def parse_tags(record: str) -> dict:
    # DKIM records are free-form enough that we collect what parses
    # instead of rejecting the whole thing (unlike DMARC, where v= is mandatory)
    tags = {}
    for part in record.split(";"):
        part = part.strip()
        if part and "=" in part:
            k, v = part.split("=", 1)
            tags[k.strip().lower()] = v.strip()
    return tags


def _read_tlv(data: bytes, i: int) -> tuple[int, int, int]:
    """Read one DER tag-length-value at offset i. Returns (tag, value_start, value_end)."""
    tag = data[i]
    i += 1
    n = data[i]
    i += 1
    if n & 0x80:  # long form: this byte's low bits say how many length bytes follow
        extra = n & 0x7F
        n = int.from_bytes(data[i : i + extra], "big")
        i += extra
    return tag, i, i + n


def rsa_modulus_bits(spki: bytes) -> int:
    """Walk a DER-encoded RSA SubjectPublicKeyInfo and return the modulus size.

    Structure: SEQ { SEQ { OID, NULL }, BITSTRING { SEQ { INT modulus, INT exp } } }.
    We only want the modulus length, so no crypto dependency for this.
    """
    _, i, _ = _read_tlv(spki, 0)        # outer SEQUENCE; i = start of its contents
    _, _, end = _read_tlv(spki, i)      # AlgorithmIdentifier
    tag, i, end = _read_tlv(spki, end)  # next sibling starts where the algid ENDS
    if tag != 0x03:
        raise ValueError("not an RSA public key (expected BIT STRING)")
    body = spki[i + 1 : end]            # first byte of a BIT STRING is the unused-bits count
    _, i, _ = _read_tlv(body, 0)        # RSAPublicKey SEQUENCE; modulus is its first child
    tag, i, end = _read_tlv(body, i)    # so entering at i is correct here
    if tag != 0x02:
        raise ValueError("not an RSA public key (expected INTEGER modulus)")
    length = end - i
    if body[i] == 0:                    # INTEGER is signed: positive moduli with the
        length -= 1                     # high bit set carry a leading 0x00
    return length * 8


def check_record(record: str) -> dict:
    tags = parse_tags(record)
    out = {"record": record, "issues": []}

    p = tags.get("p")
    if p is None:
        out["issues"].append("no p= tag: without a public key nothing can be verified")
        return out
    if p == "":
        # a real thing: setting p= empty is how you revoke a key
        out["issues"].append("p= is empty: this key was explicitly revoked")
        return out

    if "v" in tags and tags["v"] != "DKIM1":
        out["issues"].append(f"v={tags['v']} is not DKIM1")

    if tags.get("t") == "y":
        out["issues"].append("t=y: testing mode, receivers won't act on failed signatures")

    if tags.get("k", "rsa") == "rsa":
        try:
            der = base64.b64decode(p, validate=True)
        except ValueError:
            out["issues"].append("p= is not valid base64")
            return out
        try:
            bits = rsa_modulus_bits(der)
        except (ValueError, IndexError):
            out["issues"].append("p= does not parse as an RSA public key")
            return out
        out["bits"] = bits
        if bits < 2048:
            out["issues"].append(
                f"{bits}-bit RSA key: under the 2048 bits now recommended (1024 is deprecated)"
            )
    else:
        # ed25519 keys are 32 raw bytes, not DER; size check doesn't apply
        out["bits"] = None

    return out


def check(domain: str, selector: str | None = None) -> dict:
    selectors = [selector] if selector else PROBE_SELECTORS
    found = {}
    for sel in selectors:
        record = fetch(domain, sel)
        if record is not None:
            found[sel] = check_record(record)

    issues = []
    if not found:
        issues.append(
            f"no DKIM record found across {len(selectors)} common selectors; "
            "the domain either sends no DKIM-signed mail or uses a private selector"
        )
    return {"domain": domain, "selectors": found, "issues": issues}


if __name__ == "__main__":
    import json
    import sys

    domain = sys.argv[1]
    sel = sys.argv[2] if len(sys.argv) > 2 else None
    print(json.dumps(check(domain, sel), indent=2))