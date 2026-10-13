"""Email worker: claims queued jobs and sends them over SMTP.

The queue is a plain table and the claim is SELECT ... FOR UPDATE SKIP
LOCKED: if two workers poll at the same time, the second skips the row the
first locked, so no job goes out twice and there is no coordination
beyond the database. A crash mid-send rolls the transaction back, the job
stays queued and goes out later — at-least-once by design, which is the
honest guarantee for mail.
"""

import os
import smtplib
import time
from email.message import EmailMessage

import psycopg

DSN = os.environ.get("MAILOPS_DSN", "postgresql://mailops:mailops@localhost:5433/mailops")
SMTP_HOST = os.environ.get("MAILOPS_SMTP_HOST", "localhost")
SMTP_PORT = int(os.environ.get("MAILOPS_SMTP_PORT", "1025"))
FROM_ADDR = os.environ.get("MAILOPS_FROM_ADDR", "hola@mailops.tech")
POLL_SECONDS = float(os.environ.get("MAILOPS_POLL_SECONDS", "2"))
MAX_ATTEMPTS = int(os.environ.get("MAILOPS_MAX_ATTEMPTS", "3"))

CLAIM_SQL = """
    select id, to_email, subject, body, attempts
    from email_jobs
    where status = 'queued'
    order by id
    limit 1
    for update skip locked
"""


def build_message(to_email: str, subject: str, body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = FROM_ADDR
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def send_mail(msg: EmailMessage) -> None:
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
        smtp.send_message(msg)


def next_status(attempts: int, max_attempts: int = MAX_ATTEMPTS) -> str:
    # attempts is the pre-increment value from the row
    return "failed" if attempts + 1 >= max_attempts else "queued"


def process_one(conn: psycopg.Connection) -> bool:
    # lock held during send: fine for a local sink. With a slow remote
    # relay the upgrade is claim -> 'sending' -> send -> finalize, plus
    # a reaper for stale claims
    with conn.transaction():
        job = conn.execute(CLAIM_SQL).fetchone()
        if job is None:
            return False
        job_id, to_email, subject, body, attempts = job

        try:
            send_mail(build_message(to_email, subject, body))
        except (smtplib.SMTPException, OSError) as e:
            conn.execute(
                "update email_jobs set attempts = attempts + 1, last_error = %s, "
                "status = %s where id = %s",
                (str(e), next_status(attempts), job_id),
            )
            print(f"[{job_id}] error: {e}")
        else:
            conn.execute(
                "update email_jobs set status = 'sent', sent_at = now(), "
                "attempts = attempts + 1 where id = %s",
                (job_id,),
            )
            print(f"[{job_id}] sent to {to_email}")
    return True


def main() -> None:
    with psycopg.connect(DSN) as conn:
        print(f"worker up: smtp={SMTP_HOST}:{SMTP_PORT}, poll={POLL_SECONDS}s")
        while True:
            if not process_one(conn):
                time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nworker stopped")