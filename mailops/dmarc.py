"""DMARC record checks (RFC 7489)."""

import dns.resolver

POLICIES = ("none", "quarantine", "reject")

# tags definidos por el RFC; cualquier otra cosa es un typo que los
# receptores ignoran silenciosamente
KNOWN_TAGS = {"v", "p", "sp", "adkim", "aspf", "pct", "rua", "ruf", "fo", "rf", "ri"}


def fetch_dmarc(domain: str) -> str | None:
    """Return the DMARC record published at _dmarc.<domain>, or None."""
    # NXDOMAIN aqui es la respuesta normal de un dominio sin DMARC,
    # no un error como si lo seria en el nombre del dominio mismo
    try:
        answers = dns.resolver.resolve(f"_dmarc.{domain}", "TXT", lifetime=5)
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        return None

    records = []
    for a in answers:
        txt = b"".join(a.strings).decode("ascii", errors="replace")
        if txt.startswith("v=DMARC1"):
            records.append(txt)

    # misma regla que SPF: publicar dos es un error de configuracion,
    # no significa que "se aplican ambos"
    if len(records) > 1:
        raise ValueError(f"_dmarc.{domain} publishes {len(records)} DMARC records, max is 1")

    return records[0] if records else None


def parse(record: str) -> dict | None:
    """Split tag=value pairs; None if it can't be a valid DMARC record."""
    tags = {}
    for part in record.split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            return None
        key, value = part.split("=", 1)
        tags[key.strip().lower()] = value.strip()

    # RFC 7489: un record cuya version no es exactamente DMARC1 se ignora
    if tags.get("v") != "DMARC1":
        return None
    return tags


def issues(tags: dict) -> list[str]:
    found = []

    if "p" not in tags:
        found.append("p= missing: without a policy the record does nothing")
    elif tags["p"] not in POLICIES:
        found.append(f"p={tags['p']} is not a valid policy (none/quarantine/reject)")
    elif tags["p"] == "none":
        found.append("p=none is monitor-only: spoofed mail still reaches inboxes")

    pct = tags.get("pct", "")
    if pct.isdigit() and int(pct) < 100:
        found.append(f"pct={pct}: only {pct}% of mail is covered, policy is mid-rollout")

    if "rua" not in tags:
        found.append("no rua= tag: aggregate reports go nowhere, you're troubleshooting blind")

    typos = set(tags) - KNOWN_TAGS
    if typos:
        found.append(f"unknown tag(s) {sorted(typos)}: receivers ignore them silently")

    return found


def check(domain: str) -> dict:
    record = fetch_dmarc(domain)
    if record is None:
        # TODO: los receptores hacen fallback al dominio organizacional
        # para subdominios (_dmarc.<org>); nosotros solo miramos el nombre exacto
        return {"domain": domain, "status": "missing", "issues": ["no DMARC record published"]}

    tags = parse(record)
    if tags is None:
        return {
            "domain": domain,
            "status": "invalid",
            "record": record,
            "issues": ["record does not parse as DMARC"],
        }

    problems = issues(tags)
    return {
        "domain": domain,
        "status": "ok" if not problems else "issues",
        "record": record,
        "policy": tags.get("p"),
        "reports_to": tags.get("rua"),
        "issues": problems,
    }


if __name__ == "__main__":
    import json
    import sys

    print(json.dumps(check(sys.argv[1]), indent=2))