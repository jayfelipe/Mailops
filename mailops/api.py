"""HTTP API: leads intake, queue visibility, health probe."""

import os
import re

import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="mailops")

DSN = os.environ.get("MAILOPS_DSN", "postgresql://mailops:mailops@localhost:5433/mailops")

# strict enough for intake: something@something.tld, no spaces. Full RFC
# compliance is a rabbit hole (quoted local parts, IDN...) that adds
# nothing here; the real validation is the SMTP handshake downstream
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class LeadIn(BaseModel):
    email: str
    name: str | None = None


def valid_email(email: str) -> bool:
    return EMAIL_RE.match(email) is not None


def welcome_job(name: str | None) -> tuple[str, str]:
    # FIX 1 (ISC004): copy en inglés + la concatenación implícita ahora
    # vive entre paréntesis en una asignación con nombre, no suelta en la tupla
    who = name or "there"
    subject = f"welcome, {who}"
    body = (
        "thanks for signing up. this mail was delivered by the mailops "
        "worker through the job queue."
    )
    return subject, body


def connect() -> psycopg.Connection:
    # one connection per request: wrong at scale, right for demo scale.
    # upgrade path is psycopg_pool when it actually hurts
    return psycopg.connect(DSN)


@app.post("/leads", status_code=201)
def create_lead(lead: LeadIn):
    if not valid_email(lead.email):
        raise HTTPException(422, detail="invalid email")

    subject, body = welcome_job(lead.name)
    try:
        # FIX 2 (SIM117): los dos `with` anidados se vuelven uno solo.
        # Antes era:
        #     with connect() as conn:
        #         with conn.transaction():
        #             ...código con doble indentación...
        # Ahora: misma apertura de conexión + transacción, una sola indentación
        with connect() as conn, conn.transaction():
            # lead + welcome job in ONE transaction: either both exist
            # or neither. A lead with no welcome mail is a bug
            row = conn.execute(
                "insert into leads (email, name) values (%s, %s) returning id",
                (lead.email, lead.name),
            ).fetchone()
            conn.execute(
                "insert into email_jobs (to_email, subject, body) values (%s, %s, %s)",
                (lead.email, subject, body),
            )
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, detail="email already registered")

    return {"id": row[0], "email": lead.email, "welcome_email": "queued"}


@app.get("/leads")
def list_leads():
    with connect() as conn:
        rows = conn.execute(
            "select id, email, name, status, created_at from leads order by id"
        ).fetchall()
    return [
        {
            "id": r[0],
            "email": r[1],
            "name": r[2],
            "status": r[3],
            "created_at": r[4].isoformat(),
        }
        for r in rows
    ]


@app.get("/healthz")
def healthz():
    try:
        with connect() as conn:
            conn.execute("select 1")
    except psycopg.Error:
        raise HTTPException(503, detail="db unreachable")
    return {"status": "ok"}