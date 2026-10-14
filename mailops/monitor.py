"""Periodic queue health checks. Alerts to stdout and, if configured,
to a Discord webhook. Cooldown prevents re-alerting the same condition
every cycle; resolution is reported when a condition clears."""

import json
import os
import time
import urllib.request

import psycopg

DSN = os.environ.get("MAILOPS_DSN", "postgresql://mailops:mailops@db:5432/mailops")
WEBHOOK = os.environ.get("MAILOPS_DISCORD_WEBHOOK")
INTERVAL = float(os.environ.get("MAILOPS_MONITOR_INTERVAL", "30"))
FAILED_THRESHOLD = int(os.environ.get("MAILOPS_FAILED_THRESHOLD", "1"))
STUCK_MINUTES = float(os.environ.get("MAILOPS_STUCK_MINUTES", "5"))
COOLDOWN = float(os.environ.get("MAILOPS_ALERT_COOLDOWN", "600"))

SNAPSHOT_SQL = """
    select
        count(*) filter (where status = 'queued'),
        count(*) filter (where status = 'failed'),
        coalesce(extract(epoch from max(now() - created_at) filter (where status = 'queued')), 0)
    from email_jobs
"""


def conditions(queued: int, failed: int, oldest_queued_s: float) -> list[str]:
    # one dead-lettered mail is already user-visible impact: someone's
    # welcome email never went out. hence threshold 1
    out = []
    if failed >= FAILED_THRESHOLD:
        out.append("dead_letter")
    if queued > 0 and oldest_queued_s > STUCK_MINUTES * 60:
        out.append("queue_stuck")
    return out


def send_discord(text: str) -> None:
    if not WEBHOOK:
        return
    req = urllib.request.Request(
        WEBHOOK,
        data=json.dumps({"content": text}).encode(),
        headers={
            "Content-Type": "application/json",
            # urllib's default UA ("Python-urllib/x.y") gets 403-blocked by
            # Discord's edge (Cloudflare); a named UA goes through
            "User-Agent": "mailops-monitor/0.1",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except OSError as e:
        # never let alerting take down the alerter
        print(f"webhook error: {e}")


def cycle(conn: psycopg.Connection, active: dict) -> None:
    queued, failed, oldest = conn.execute(SNAPSHOT_SQL).fetchone()
    oldest = float(oldest)
    now = time.monotonic()
    found = conditions(queued, failed, oldest)

    for cond in found:
        if cond not in active or now - active[cond] > COOLDOWN:
            msg = f"[mailops] {cond}: queued={queued} failed={failed} oldest_queued={oldest:.0f}s"
            print(msg)
            send_discord(msg)
            active[cond] = now

    for cond in [c for c in active if c not in found]:
        print(f"[mailops] resolved: {cond}")
        send_discord(f"[mailops] resolved: {cond}")
        del active[cond]


def main() -> None:
    with psycopg.connect(DSN) as conn:
        print(f"monitor up: interval={INTERVAL}s, webhook={'yes' if WEBHOOK else 'stdout only'}")
        active: dict = {}
        while True:
            cycle(conn, active)
            time.sleep(INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nmonitor stopped")