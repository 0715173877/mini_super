# MiniSuper — Production Deployment (Ubuntu + Gunicorn + Nginx + PostgreSQL + Let's Encrypt)

This document deploys **MiniSuper** (Django 5.2) to a single Ubuntu server, served on a
subdomain (example: **`minisuper.carlkasa.com`**), behind **nginx** with **TLS from Certbot**.

It is modelled on the existing `tenant_systems` deployment (`tenant.carlkasa.com`) so both apps
follow the same conventions: a **Gunicorn unix socket**, a **static-files alias**, and a
**Certbot-managed HTTPS server block**. Only the names/paths differ.

> **Naming used throughout** — change these once at the top of your notes and keep them consistent:
>
> | Placeholder | Value in this doc | Meaning |
> | --- | --- | --- |
> | `<domain>` | `minisuper.carlkasa.com` | Public hostname |
> | `<app_user>` | `minisuper_app` | Linux account that owns and runs the app |
> | `<app_dir>` | `/home/minisuper_app/mini_super` | Repo checkout (contains `manage.py`) |
> | `<venv>` | `/home/minisuper_app/venv` | Python virtualenv |
> | `<static>` | `/home/minisuper_app/mini_super/staticfiles` | `collectstatic` output (served by nginx) |
> | `<media>` | `/home/minisuper_app/mini_super/media` | User uploads (served by nginx; currently unused) |
> | `<sock>` | `/home/minisuper_app/minisuper.sock` | Gunicorn unix socket nginx proxies to |

---

## 0. Architecture

```
Browser ──HTTPS──► nginx (:443, Certbot TLS)
                     ├── /static/  ─► alias  /home/minisuper_app/mini_super/staticfiles/
                     ├── /media/   ─► alias  /home/minisuper_app/mini_super/media/
                     └── /         ─► proxy_pass http://unix:/home/minisuper_app/minisuper.sock
                                                   │
                                          Gunicorn (systemd, user=minisuper_app)
                                                   │   WSGI: minisuper.wsgi:application
                                                   ▼
                                          PostgreSQL  (DB from .env)
```

* **nginx** terminates TLS, serves static/media directly, and never touches Python.
* **Gunicorn** runs the Django app as a normal systemd service and listens on a **unix socket**
  (not a TCP port), so nothing else on the box can reach it by accident.
* **PostgreSQL** credentials, `SECRET_KEY`, `DEBUG` and `ALLOWED_HOSTS` all come from an
  **`.env`** file via `python-dotenv` (see `minisuper/settings.py`).

---

## 1. Prerequisites (server packages)

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y \
  python3 python3-venv python3-dev \
  build-essential libpq-dev \
  postgresql postgresql-contrib \
  nginx certbot python3-certbot-nginx \
  git
```

Check versions:

```bash
python3 --version            # 3.12+ is fine (dev machine used 3.13)
psql --version
nginx -v
```

---

## 2. Create the app user and directories

Run the app as a dedicated, unprivileged user — **never** as `root` and ideally not as `www-data`.

> On the live box this account **already exists**: `/home/minisuper_app` is its home and the repo is
> checked out at `/home/minisuper_app/mini_super`. The commands below are for a from-scratch host.

```bash
# only if the account does not exist yet
sudo adduser --disabled-password --gecos "" minisuper_app

# venv and logs live beside the checkout; mini_super/ itself is created by `git clone` in §3
sudo mkdir -p /home/minisuper_app/venv /home/minisuper_app/logs
sudo chown -R minisuper_app:minisuper_app /home/minisuper_app
```

Resulting layout (`staticfiles/` and `media/` live **inside** the checkout, i.e. under `BASE_DIR`):

```
/home/minisuper_app/
├── mini_super/           # git checkout (manage.py, minisuper/, inventory/, sales/, operations/, core/)
│   ├── staticfiles/      # STATIC_ROOT  -> collectstatic output -> nginx /static/
│   └── media/            # MEDIA_ROOT   -> uploads (unused today) -> nginx /media/
├── venv/                 # virtualenv
├── logs/                 # gunicorn access/error logs
└── minisuper.sock        # gunicorn socket (created at runtime)
```

### 2.1 Let nginx read the socket

nginx runs as `www-data`; it must be able to traverse `/home/minisuper_app` and read the socket.

```bash
sudo usermod -aG minisuper_app www-data
```

The service unit in §6 additionally sets `UMask=0007`, and Gunicorn is told `--umask 007`, so the
socket is created group-readable by `minisuper_app` — which `www-data` now belongs to. Log out/in (or
`sudo systemctl restart nginx`) for the group change to apply to nginx.

---

## 3. Get the code and build the virtualenv

The repo is **already cloned on the live server** at `/home/minisuper_app/mini_super`. On a fresh
host, clone it there:

```bash
sudo -u minisuper_app -H git clone https://github.com/0715173877/mini_super.git /home/minisuper_app/mini_super
cd /home/minisuper_app/mini_super
```

> The repo root that contains `manage.py` is `/home/minisuper_app/mini_super`; inside it lives the
> Django package also called `minisuper/` (with `settings.py`, `urls.py`, `wsgi.py`).

Create and populate the virtualenv:

```bash
sudo -u minisuper_app -H python3 -m venv /home/minisuper_app/venv
sudo -u minisuper_app -H /home/minisuper_app/venv/bin/pip install --upgrade pip wheel
sudo -u minisuper_app -H /home/minisuper_app/venv/bin/pip install -r /home/minisuper_app/mini_super/r.txt
```

> **Note:** the dependency file is currently named **`r.txt`**. A future cleanup renames it to
> `requirements.txt`; if/when that happens, swap the filename above. **Gunicorn is not yet listed**,
> so install it explicitly (it is the WSGI server for production):
>
> ```bash
> sudo -u minisuper_app -H /home/minisuper_app/venv/bin/pip install gunicorn
> ```
>
> Add `gunicorn` to whichever requirements file is in use so redeploys stay reproducible.

---

## 4. PostgreSQL database and role

```bash
sudo -u postgres psql
```

Inside `psql`:

```sql
CREATE DATABASE minisuper_db;
CREATE USER minisuper_user WITH ENCRYPTED PASSWORD 'CHANGE_ME_STRONG';
ALTER ROLE minisuper_user SET client_encoding TO 'utf8';
ALTER ROLE minisuper_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE minisuper_user SET timezone TO 'Africa/Dar_es_Salaam';
GRANT ALL PRIVILEGES ON DATABASE minisuper_db TO minisuper_user;

-- Required on PostgreSQL 15+ so the app user can create tables during migrate:
\c minisuper_db
GRANT ALL ON SCHEMA public TO minisuper_user;
\q
```

Verify the app user can connect:

```bash
PGPASSWORD='CHANGE_ME_STRONG' psql -h 127.0.0.1 -U minisuper_user -d minisuper_db -c '\conninfo'
```

> Use `127.0.0.1` (not `localhost`) if you want a TCP connection; `localhost` may go over a unix
> socket and ignore the password. Keep PostgreSQL listening on localhost only — nginx/Gunicorn talk
> to it locally, so there is **no** reason to expose port 5432 publicly.

---

## 5. Environment file, settings and static files

### 5.1 Create the production `.env`

`settings.py` calls `load_dotenv(BASE_DIR / '.env')`, so the file must sit **next to `manage.py`**
in `/home/minisuper_app/mini_super/.env`. It is git-ignored — put it there manually and lock it down.

```bash
sudo -u minisuper_app -H tee /home/minisuper_app/mini_super/.env >/dev/null <<'EOF'
# --- Django core (PRODUCTION) ---
DJANGO_SECRET_KEY=REPLACE_WITH_A_LONG_RANDOM_VALUE
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=minisuper.carlkasa.com,www.minisuper.carlkasa.com

# --- PostgreSQL ---
DB_NAME=minisuper_db
DB_USER=minisuper_user
DB_PASSWORD=CHANGE_ME_STRONG
DB_HOST=127.0.0.1
DB_PORT=5432
EOF

sudo chmod 600 /home/minisuper_app/mini_super/.env
sudo chown minisuper_app:minisuper_app /home/minisuper_app/mini_super/.env
```

Generate a fresh secret key (run this **locally** and paste the output in):

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

> **`DEBUG=False` requires `ALLOWED_HOSTS`** to contain the domain, or every request returns
> `400 Bad Request`. The value above is comma-separated; `settings.py` splits on commas.

### 5.2 Required change: add `STATIC_ROOT`

`settings.py` currently defines neither `STATIC_ROOT` nor `STATICFILES_DIRS`, so
`collectstatic` **fails today**. Add these lines next to the existing `STATIC_URL`:

```python
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']      # the currently-empty static/ folder
STATIC_ROOT = BASE_DIR / 'staticfiles'        # -> /home/minisuper_app/mini_super/staticfiles

# Optional: enable only when uploads are introduced.
# MEDIA_URL = '/media/'
# MEDIA_ROOT = BASE_DIR / 'media'             # -> /home/minisuper_app/mini_super/media
```

> `BASE_DIR` is `/home/minisuper_app/mini_super`, so `STATIC_ROOT` resolves to
> **`/home/minisuper_app/mini_super/staticfiles`** — exactly the path the nginx block in §7 `alias`es, and the
> same pattern the `tenant_systems` host uses (there it is `/home/tenant_systems/staticfiles`). If
> you prefer that flatter `/home/minisuper_app/staticfiles` layout, change **both** `STATIC_ROOT` and the
> nginx `alias` together so they still point at the same directory.

### 5.3 Recommended: trusted origins (for future POSTs behind a proxy)

Because nginx terminates TLS and forwards plain HTTP, add the public origin so Django's CSRF check
accepts form posts. Optional today (the app is same-origin), but harmless and future-proof:

```python
CSRF_TRUSTED_ORIGINS = ['https://minisuper.carlkasa.com']
```

### 5.4 Apply, migrate, collectstatic

```bash
cd /home/minisuper_app/mini_super
sudo -u minisuper_app -H /home/minisuper_app/venv/bin/python manage.py migrate
sudo -u minisuper_app -H /home/minisuper_app/venv/bin/python manage.py collectstatic --noinput
```

If you keep `STATIC_ROOT` inside the checkout, make sure nginx can traverse the path
(`/home/minisuper_app/mini_super` is already group-`minisuper_app`). Fixtures/cache writing also needs the app dir
writable by the app user — `chown -R minisuper_app:minisuper_app /home/minisuper_app` in §2 covers it.

---

## 6. Gunicorn as a systemd service

Create `/etc/systemd/system/minisuper.service`:

```ini
[Unit]
Description=MiniSuper Gunicorn daemon
Requires=network.target
After=network.target

[Service]
Type=notify
User=minisuper_app
Group=minisuper_app
# nginx (www-data) must be able to read the socket -> group-rw, world-none.
UMask=0007
WorkingDirectory=/home/minisuper_app/mini_super
# Load SECRET_KEY / DEBUG / DB_* exactly as the app does.
EnvironmentFile=/home/minisuper_app/mini_super/.env
ExecStart=/home/minisuper_app/venv/bin/gunicorn \
    --workers 3 \
    --bind unix:/home/minisuper_app/minisuper.sock \
    --umask 007 \
    --access-logfile /home/minisuper_app/logs/gunicorn-access.log \
    --error-logfile  /home/minisuper_app/logs/gunicorn-error.log \
    --log-level info \
    minisuper.wsgi:application
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Notes:

* `minisuper.wsgi:application` matches `minisuper/wsgi.py`
  (`DJANGO_SETTINGS_MODULE = 'minisuper.settings'`), and `WorkingDirectory` ensures that package is
  importable **and** that `BASE_DIR/.env` is found.
* `--workers 3` suits a small/medium box: a common rule is `2 × CPU cores + 1`. For a busy POS you
  may add `--threads 2` (then use `--worker-class gthread`).
* Gunicorn 20.1+ supports `Type=notify` + `--umask`; if your version older, use `Type=simple` and
  drop `Type=notify`.

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now minisuper
sudo systemctl status minisuper --no-pager
ls -l /home/minisuper_app/minisuper.sock        # should exist, mode srwxrwx---
```

Smoke-test the socket without nginx:

```bash
curl --unix-socket /home/minisuper_app/minisuper.sock http://localhost/ -I
```

---

## 7. Nginx site configuration

Create `/etc/nginx/sites-available/minisuper`:

```nginx
server {
    listen 443 ssl;
    server_name minisuper.carlkasa.com;

    # --- Static assets produced by `collectstatic` (nginx serves these directly) ---
    location /static/ {
        alias /home/minisuper_app/mini_super/staticfiles/;   # == STATIC_ROOT (settings.py)
        access_log off;
        expires 30d;
        add_header Cache-Control "public";
    }

    # --- User uploads (currently unused; harmless to keep for parity) ---
    location /media/ {
        alias /home/minisuper_app/mini_super/media/;         # == MEDIA_ROOT (settings.py)
        access_log off;
        expires 7d;
    }

    # --- Everything else goes to Gunicorn over the unix socket ---
    location / {
        include proxy_params;
        proxy_pass http://unix:/home/minisuper_app/minisuper.sock;
    }

    # Let's Encrypt (Certbot rewrites/owns these two lines after running certbot)
    ssl_certificate     /etc/letsencrypt/live/minisuper.carlkasa.com/fullchain.pem; # managed by Certbot
    ssl_certificate_key /etc/letsencrypt/live/minisuper.carlkasa.com/privkey.pem;   # managed by Certbot
    include /etc/letsencrypt/options-ssl-nginx.conf;                                 # managed by Certbot
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;                                   # managed by Certbot
}

# HTTP: redirect everything to HTTPS.
server {
    listen 80;
    server_name minisuper.carlkasa.com;

    if ($host = minisuper.carlkasa.com) {
        return 301 https://$host$request_uri;
    }

    return 301 https://$host$request_uri;
}
```

Enable it and reload:

```bash
sudo ln -s /etc/nginx/sites-available/minisuper /etc/nginx/sites-enabled/minisuper
sudo nginx -t
sudo systemctl reload nginx
```

> **Two server blocks, one shared `proxy_params`.** `proxy_params` (from the `nginx` package) sets
> `Host`, `X-Real-IP`, `X-Forwarded-For` and `X-Forwarded-Proto` — the last of which is what tells
> Django the request was HTTPS. Keep `include proxy_params;` even if you later edit the block.
>
> **Guarantee the block order doesn't collide with the other app.** `tenant.carlkasa.com` and
> `minisuper.carlkasa.com` are separate `server_name`s, so both files can live in
> `sites-enabled/`; nginx picks the matching block by SNI/Host. Just make sure neither uses a bare
> `server_name _;` or `default_server` that would swallow the other.

### 7.1 TLS certificate (Certbot)

Run this **first** with a temporary HTTP-only block if DNS is not yet resolving, or directly if the
A record already points at this server:

```bash
sudo certbot --nginx \
  -d minisuper.carlkasa.com \
  --redirect --agree-tos -m you@example.com --no-eff-email
```

Certbot normally edits the block in place. In this design the `ssl_*`/`include` lines are already
present as placeholders, so the **first** run on a brand-new file is best done like this to avoid
"duplicate certificate" errors:

1. Deploy the file **without** the four `ssl_*` / `include options-ssl` / `ssl_dhparam` lines and
   without `listen 443` (i.e. a plain `listen 80` block).
2. Run `certbot --nginx -d minisuper.carlkasa.com`.
3. Let Certbot add the HTTPS block; then re-add the `/static/`, `/media/`, `/` locations if needed.

Auto-renewal:

```bash
sudo systemctl list-timers | grep certbot     # certbot.timer should be active
sudo certbot renew --dry-run                  # rehearse the renewal
```

---

## 8. Import your local data (optional)

A dump of the local database is committed at
`backups/minisuper_data_20261003.json` (105 objects: catalogue, purchasing, sales, daily
summaries, site settings, users, groups and role links).

**Order matters — migrate first, then load:**

```bash
cd /home/minisuper_app/mini_super

# 1) Schema + the auto-created contenttypes/permissions (groups reference permissions by name)
sudo -u minisuper_app -H /home/minisuper_app/venv/bin/python manage.py migrate

# 2) Business data + logins (run once, on a FRESH database)
sudo -u minisuper_app -H /home/minisuper_app/venv/bin/python manage.py loaddata backups/minisuper_data_20261003.json
```

* The fixture **excludes** `contenttypes`, `auth.permission`, `admin.logentry` and `sessions`
  because `migrate` recreates them. It **includes** `auth.user` (with password hashes) and
  `auth.group`, so existing logins keep working.
* `loaddata` preserves primary keys. It is designed for a **fresh** database; loading it into a
  database that already has overlapping IDs will raise `IntegrityError`. Start clean if in doubt.

If you would rather not carry over the demo users, create fresh ones instead:

```bash
sudo -u minisuper_app -H /home/minisuper_app/venv/bin/python manage.py createsuperuser
```

…and re-dump locally without accounts:

```bash
python manage.py dumpdata --natural-foreign --indent 2 \
  --exclude contenttypes --exclude auth.permission \
  --exclude admin.logentry --exclude sessions \
  --exclude auth.user --exclude auth.group \
  --output backups/minisuper_data_no_users.json
```

> ⚠️ **Rotate the imported passwords.** `backups/` is committed to a **public** GitHub repo, so the
> password **hashes** in the fixture (including the `admin` superuser) are public. After import,
> change them (admin → *Users & Roles*, or `manage.py changepassword <user>`) and treat the dumped
> hashes as compromised.

---

## 9. Firewall and permissions

```bash
# Allow SSH before enabling, or you will lock yourself out.
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
sudo ufw status

# Ownership sanity
sudo chown -R minisuper_app:minisuper_app /home/minisuper_app
sudo chmod 600 /home/minisuper_app/mini_super/.env
```

**Never** expose Gunicorn — it listens on a unix socket only, and PostgreSQL stays bound to localhost.

---

## 10. Redeploy / update workflow

```bash
cd /home/minisuper_app/mini_super
sudo -u minisuper_app -H git pull --ff-only origin main
sudo -u minisuper_app -H /home/minisuper_app/venv/bin/pip install -r r.txt      # + gunicorn
sudo -u minisuper_app -H /home/minisuper_app/venv/bin/python manage.py migrate
sudo -u minisuper_app -H /home/minisuper_app/venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart minisuper
sudo systemctl reload nginx
```

Tail the logs while testing:

```bash
sudo journalctl -u minisuper -f
sudo tail -f /home/minisuper_app/logs/gunicorn-error.log
sudo tail -f /var/log/nginx/error.log
```

---

## 11. Verification checklist

Run top to bottom; every step should pass before exposing the site.

| # | Command | Expected |
| --- | --- | --- |
| 1 | `sudo systemctl is-active minisuper` | `active` |
| 2 | `ls -l /home/minisuper_app/minisuper.sock` | socket exists, mode `srwxrwx---` |
| 3 | `curl --unix-socket /home/minisuper_app/minisuper.sock http://localhost/ -I` | `302` (to `/accounts/login/`) |
| 4 | `sudo nginx -t` | `syntax is ok` / `test is successful` |
| 5 | `curl -I https://minisuper.carlkasa.com/` | `HTTP/2 302` via TLS |
| 6 | `curl -I http://minisuper.carlkasa.com/` | `301` to `https://…` |
| 7 | `curl -I https://minisuper.carlkasa.com/static/<collected-file>` | `200` served by nginx |
| 8 | Log in via the browser | dashboard loads, styling intact |

If step 7 shows the *Django* login page instead of a `200`, nginx is not matching `/static/` — check
the `alias` path and that `collectstatic` actually wrote files.

---

## 12. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `502 Bad Gateway` | Gunicorn down, or socket missing/unreadable | `systemctl status minisuper`; confirm `www-data` is in group `minisuper_app`; re-check `UMask`/`--umask` |
| `400 Bad Request` | `DEBUG=False` and host not in `ALLOWED_HOSTS` | add the domain to `DJANGO_ALLOWED_HOSTS` in `.env`, restart `minisuper` |
| `403 CSRF verification failed` on login/POST | origin not trusted behind proxy | add `CSRF_TRUSTED_ORIGINS = ['https://minisuper.carlkasa.com']` |
| CSS/JS missing, page unstyled | `collectstatic` not run, or `alias` path wrong | run `collectstatic --noinput`; ensure nginx `alias` == `STATIC_ROOT` |
| `could not connect to server` / DB error | wrong `DB_*` in `.env`, or PG rejecting the user | test `psql -h 127.0.0.1 -U <user> -d <db>`; re-check grants in §4 |
| `permission denied` writing files | files owned by `root` | `sudo chown -R minisuper_app:minisuper_app /home/minisuper_app` |
| `duplicate certificate` from Certbot | `ssl_certificate` lines present on first run | follow the two-pass Certbot flow in §7.1 |
| `relation "…" does not exist` | forgot `migrate` | `manage.py migrate` |
| Socket mode `srwxr-xr-x` (no group write) | `UMask` not applied | set `UMask=0007` in the unit **and** `--umask 007` in `ExecStart`; `daemon-reload` + restart |

---

## 13. Security / production checklist

- [ ] `DJANGO_DEBUG=False` in `.env`.
- [ ] Fresh `DJANGO_SECRET_KEY` (never the hard-coded fallback in `settings.py`).
- [ ] `DJANGO_ALLOWED_HOSTS` lists the real domain(s) only — replace the dev default `*`.
- [ ] `.env` is `chmod 600`, owned by the app user, and **never** committed.
- [ ] HTTPS enforced; HTTP 301s to HTTPS; `certbot.timer` active.
- [ ] PostgreSQL reachable from localhost only.
- [ ] App runs as the unprivileged `minisuper_app` user (not `root`, not `www-data`).
- [ ] `STATIC_ROOT` set and `collectstatic` run on every deploy.
- [ ] Leaked/imported password hashes rotated (see §8).
- [ ] Nightly DB backup:
      `sudo -u postgres pg_dump minisuper_db | gzip > /home/minisuper_app/logs/db-$(date +%F).sql.gz`.

---

## 14. Quick reference — files created by this guide

| Where | What |
| --- | --- |
| `/etc/systemd/system/minisuper.service` | Gunicorn service (§6) |
| `/etc/nginx/sites-available/minisuper` | nginx site (§7), symlinked into `sites-enabled/` |
| `/home/minisuper_app/mini_super/.env` | Production config (§5.1) |
| `/home/minisuper_app/mini_super/minisuper/settings.py` | add `STATIC_ROOT` / `STATICFILES_DIRS` (§5.2) |
| `/home/minisuper_app/mini_super/{staticfiles,media}` | nginx-served assets (`collectstatic` output) and uploads |
| `/home/minisuper_app/logs` | Gunicorn access/error logs |
| `/home/minisuper_app/minisuper.sock` | runtime unix socket |

**Placeholders to find-and-replace across this doc before use:** `minisuper.carlkasa.com`,
`/home/minisuper_app`, `minisuper_app` (the Unix user), `minisuper_db`, `minisuper_user`,
`CHANGE_ME_STRONG`, `you@example.com`.



