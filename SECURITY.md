# Security notes

Short list. Every claim here is exercised by tests/test_api.py.

Passwords are hashed with PBKDF2 HMAC SHA256, 120,000 rounds, per user
random salt. The plain password is never stored and never logged. The
test opens the database file and reads the row to prove it.

Login returns a random bearer token with an 8 hour life, held in server
memory. Every api route except login returns 401 without one. A wrong
password returns 401. A username of admin' OR '1'='1 returns 401,
because the query is parameterised and that string is just a username
that does not exist.

Roles are enforced on the server, not hidden in the page. A viewer
account gets 403 on any write. A follow-up agent is scoped to his office
in the data itself: office lists, office pages and alerts are filtered
before they leave the server, and the audit trail is admin only.

Every change to a daily record and every leave, follow-up and dispute
action writes an audit row with the user, the time, the field, the old
value and the new value.

Input is cast, length limited and range checked. Request bodies are
capped at 20 KB. Dates must be real ISO dates and a range may not run
backwards or past a year.

Responses carry X-Content-Type-Options nosniff.

What this does not do, honestly: there is no HTTPS here because there is
no deployment yet. Tokens die with the process. Rate limiting on login
is not implemented, and on a public deployment that would be the first
job, before any feature.
