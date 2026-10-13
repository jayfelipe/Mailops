"""mailops CLI: aggregate SPF/DKIM/DMARC checks for one domain."""

import argparse
import json

from mailops import dkim, dmarc, spf


def run_checks(domain: str, selector: str | None = None) -> dict:
    return {
        "domain": domain,
        "spf": spf.check(domain),
        "dmarc": dmarc.check(domain),
        "dkim": dkim.check(domain, selector),
    }


def print_report(r: dict) -> None:
    print(f"mailops report - {r['domain']}")

    s = r["spf"]
    print(f"\nSPF [{s['status']}] lookups: {s.get('lookups', '-')}")
    for issue in s["issues"]:
        print(f"  ! {issue}")

    d = r["dmarc"]
    print(f"\nDMARC [{d['status']}] policy: {d.get('policy', '-')}")
    for issue in d["issues"]:
        print(f"  ! {issue}")

    k = r["dkim"]
    found = k["selectors"]
    label = "ok" if found else "missing"
    print(f"\nDKIM [{label}] {len(found)} selector(s) found")
    for sel, info in found.items():
        if "bits" in info:
            size = f"{info['bits']}-bit" if info["bits"] else "ed25519"
        else:
            size = "?"
        flags = "; ".join(info["issues"]) or "ok"
        print(f"  {sel:<12} {size:<9} {flags}")
    for issue in k["issues"]:
        print(f"  ! {issue}")


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="mailops", description="Email deliverability checks: SPF, DKIM, DMARC"
    )
    ap.add_argument("domain", help="domain to check, e.g. example.com")
    ap.add_argument("--json", action="store_true", help="full machine-readable output")
    ap.add_argument("--selector", help="check one DKIM selector instead of probing the list")
    args = ap.parse_args()

    report = run_checks(args.domain, args.selector)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)
        