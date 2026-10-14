create table leads (
    id bigint generated always as identity primary key,
    email text not null unique,
    name text,
    status text not null default 'new' check (status in ('new', 'active', 'unsubscribed')),
    created_at timestamptz not null default now()
);

-- transactional + lifecycle mail. Decoupled from leads on purpose:
-- system mail (alerts, admin notices) flows through here too
create table email_jobs (
    id bigint generated always as identity primary key,
    to_email text not null,
    subject text not null,
    body text not null,
    status text not null default 'queued' check (status in ('queued', 'sent', 'failed')),
    attempts int not null default 0,
    last_error text,
    created_at timestamptz not null default now(),
    sent_at timestamptz
);

-- the worker polls on status; without this every poll is a seq scan
create index email_jobs_status_idx on email_jobs (status);