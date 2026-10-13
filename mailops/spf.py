"""SPF record checks (RFC 7208)."""

import dns.resolver

# SPF evaluation is capped at 10 DNS lookups. Going over is a permerror,
# and it's the classic way a working SPF record silently breaks after
# someone adds one more vendor include.
LOOKUP_LIMIT = 10

LOOKUP_MECHANISMS = ("include", "a", "mx", "ptr", "exists")


def fetch_spf(domain: str) -> str | None:
    """Return the SPF record for a domain, or None if it doesn't publish one."""
    try:
        answers = dns.resolver.resolve(domain, "TXT", lifetime=5)
    except dns.resolver.NoAnswer:
        return None
    except dns.resolver.NXDOMAIN as e:
        raise ValueError(f"{domain} does not exist") from e

    records = []
    for a in answers:
        txt = b"".join(a.strings).decode("ascii", errors="replace")
        if txt.startswith("v=spf1"):
            records.append(txt)

    # two SPF records is a permerror per RFC 7208 3.2. Tools that grab
    # only the first match miss this.
    if len(records) > 1:
        raise ValueError(f"{domain} publishes {len(records)} SPF records, max is 1")

    return records[0] if records else None


def count_lookups(record: str) -> int:
    """Count DNS-consuming terms against the 10-lookup budget."""
    n = 0
    for term in record.split()[1:]:  # skip v=spf1
        if term.startswith("redirect="):
            n += 1
            continue
        # strip qualifier and prefix syntax: ~mx, a/24, include:dom all cost one
        mech = term.lstrip("+-~?").split(":")[0].split("/")[0].lower()
        if mech in LOOKUP_MECHANISMS:
            n += 1
    # TODO: an mx pointing at a name with many A records burns extra
    # lookups per RFC 7208 4.6.4; we approximate 1 for now
    return n


def issues(record: str) -> list[str]:
    """Return human-readable problems found in an SPF record."""
    found = []
    terms = record.split()

    lookups = count_lookups(record)
    if lookups > LOOKUP_LIMIT:
        found.append(f"{lookups} DNS lookups, limit is {LOOKUP_LIMIT} (permerror territory)")

    if "+all" in terms:
        found.append("'+all' lets the entire internet send as this domain")

    # with a redirect the final result is decided elsewhere, so 'all'
    # is not required (gmail.com does exactly this)
    has_redirect = any(t.startswith("redirect=") for t in terms)
    if not has_redirect and terms[-1].lstrip("+-~?") != "all":
        found.append("no 'all' mechanism, result is undefined for unmatched senders")

    return found


def check(domain: str) -> dict:
    record = fetch_spf(domain)
    if record is None:
        return {"domain": domain, "status": "missing", "issues": ["no SPF record published"]}

    problems = issues(record)
    return {
        "domain": domain,
        "status": "ok" if not problems else "issues",
        "record": record,
        "lookups": count_lookups(record),
        "issues": problems,
    }


if __name__ == "__main__":
    import json
    import sys

    print(json.dumps(check(sys.argv[1]), indent=2))