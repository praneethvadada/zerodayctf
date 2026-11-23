# ZeroDayCTF production runbook (AWS EC2 + RDS)

```
 players ──HTTPS──▶  EC2 (Ubuntu)                                  AWS RDS
                     ├─ nginx   (TLS, redirects, gzip)  ───────▶  MariaDB 10.11
                     ├─ app     (gunicorn + gevent)       3306     (private, encrypted, auto-backups)
                     ├─ redis   (cache + sessions, local)
                     └─ EBS disk: uploaded files, logs
```

* The database lives in **RDS**. Nothing about the database is stored on the server.
* Uploaded files (writeup screenshots, challenge files) live on the server disk in `.data/CTFd/uploads`
  and are backed up by `deploy/backup.sh`.
* Everything is started with `./deploy/compose.sh`, which picks the right Docker Compose files for you.

Everything below was tested locally (HTTPS, redirects, backups, restore, seed, load) except the steps that
need your AWS account: RDS creation, DNS and the real Let's Encrypt certificate.

---

## 0. Sizing (starting point, measured locally)

| Players | EC2 | RDS | Notes |
| --- | --- | --- | --- |
| up to ~300 | `t3.medium` (2 vCPU, 4 GB) | `db.t4g.small` | 30 GB gp3 disk |
| 300 - 800 | `t3.large` (2 vCPU, 8 GB) | `db.t4g.medium` | turn on "unlimited" CPU credits |

Local load test (2 app workers): home page ~450 requests/s, challenges list ~580/s, scoreboard ~1600/s, challenges page
~250/s with zero errors. A 500-player event peaks far below that. Use the same AWS region for EC2 and RDS.

---

## 1. Create the RDS database (AWS console)

RDS > **Create database** > **Standard create**

| Setting | Value |
| --- | --- |
| Engine | **MariaDB**, version **10.11.x** |
| Template | Production (or Dev/Test to save cost) |
| DB instance identifier | `zerodayctf-db` |
| Master username / password | `admin` / a long password (save it in a password manager) |
| Instance class | see sizing above |
| Storage | gp3, 20 GB, **enable storage autoscaling** (max 100 GB) |
| Multi-AZ | optional (about double the cost). Good for event day, can be switched off later |
| VPC | **the same VPC as your EC2 server** |
| Public access | **No** |
| VPC security group | create new: `zerodayctf-rds-sg` |
| Initial database name | `ctfd` |
| Backup retention | **7 days** (use 14+ around the event) |
| Encryption | **Enabled** |
| Deletion protection | **Enabled** |

**Parameter group** (create a custom one, family `mariadb10.11`, and attach it):
`character_set_server`, `character_set_database`, `character_set_client`, `character_set_connection`, `character_set_results`
= `utf8mb4`; `collation_server`, `collation_connection` = `utf8mb4_unicode_ci`. Optionally `require_secure_transport` = `1`.

**Security group rule** (RDS > the database > Connectivity > security group > Inbound rules):
Type `MySQL/Aurora` (3306), **Source = your EC2 instance's security group** (not "0.0.0.0/0").

Copy the **endpoint** (looks like `zerodayctf-db.xxxxxxxx.ap-south-1.rds.amazonaws.com`).

---

## 2. Prepare the EC2 server

1. **Security group of the EC2 instance:** inbound `80` and `443` from anywhere; `22` only from **My IP**.
2. **Elastic IP:** allocate one and attach it to the instance so the address never changes.
3. Keep your `.pem` key private: `chmod 400 yourkey.pem`.
4. SSH in, then:

```bash
cd ~/zerodayctf
git pull
bash deploy/server-setup.sh      # installs Docker, firewall, fail2ban, auto security updates
exit                             # log out and back in once so the docker group applies
```

Check `docker compose version` shows **2.24 or newer**.

---

## 3. Configure secrets and connect to RDS

```bash
cd ~/zerodayctf
cp deploy/.env.production.example .env
chmod 600 .env
nano .env                        # fill SECRET_KEY, REDIS_PASSWORD (openssl rand -hex 32) and DATABASE_URL
./deploy/fetch-rds-ca.sh         # downloads the AWS certificate bundle
```

Create the **app database user** (the master user is only for setup). Replace `ENDPOINT` and the password:

```bash
docker run --rm -it -v "$PWD/.data/rds/global-bundle.pem:/ca.pem:ro" mariadb:10.11 \
  mariadb --ssl-ca=/ca.pem --ssl-verify-server-cert -h ENDPOINT -u admin -p
```
```sql
CREATE USER 'ctfd'@'%' IDENTIFIED BY 'A_LONG_RANDOM_PASSWORD_LETTERS_AND_DIGITS';
GRANT ALL PRIVILEGES ON ctfd.* TO 'ctfd'@'%';
FLUSH PRIVILEGES;
EXIT;
```

Put that same password in `DATABASE_URL` in `.env`, then test the connection (should say TLS encrypted, utf8mb4):

```bash
./deploy/compose.sh build
./deploy/compose.sh run --rm --no-deps ctfd python scripts/db_check.py
```

---

## 4. DNS and HTTPS

At your domain registrar / DNS provider create two **A records** to the Elastic IP:
`zerodayctf.com` and `www.zerodayctf.com` (TTL 300). Check: `dig +short www.zerodayctf.com`.

```bash
./deploy/init-certs.sh you@example.com --staging    # optional dry run
./deploy/init-certs.sh you@example.com              # real certificate + starts the site
```

Renewal is automatic (every 12 hours). Open **https://www.zerodayctf.com**.

---

## 5. First-time site setup

1. Open `https://www.zerodayctf.com/setup`: event name `ZeroDayCTF`, create the **admin account (strong, unique password)**.
2. Apply the ZeroDayCTF content and settings (home page, Rules, visibility, schedule, robots.txt):

```bash
./deploy/compose.sh exec -T -e PYTHONPATH=/opt/CTFd ctfd python scripts/seed_site.py
```

3. Log in at `/admin`, add your real challenges (Admin > Challenges), and test with a throwaway account.
   The 16 sample challenges and demo players exist only on your laptop; they are **not** copied to production.

---

## 6. Backups

```bash
sudo mkdir -p /var/backups/zerodayctf && sudo chown ubuntu: /var/backups/zerodayctf
./deploy/backup.sh                                   # test it once
sudo cp deploy/zerodayctf.cron /etc/cron.d/zerodayctf   # nightly + hourly on 29 Nov
```

* RDS also keeps its own automatic snapshots (point-in-time recovery). Before the event, take a **manual snapshot**
  (RDS > Actions > Take snapshot).
* Optional off-server copy: attach an IAM role with write access to one S3 bucket, install `awscli`
  (`sudo apt-get install -y awscli`) and set `BACKUP_S3_URI=s3://your-bucket/zerodayctf` in the cron environment.
* **Test a restore** (into a scratch database, never the live one):

```bash
./deploy/restore.sh --db /var/backups/zerodayctf/db-XXXX.sql.gz --into ctfd_restore_test
```

---

## 7. Updating the site

On your laptop: commit, `git push`. On the server:

```bash
cd ~/zerodayctf && ./deploy/deploy.sh          # pull, rebuild, restart, wait until healthy
./deploy/deploy.sh rollback                     # if something is wrong: go back one deploy
```

Health report any time: `./deploy/check.sh`.

---

## 8. Event checklist

**One week before**
- [ ] Real challenges loaded and solved by a test account; all flags and hints verified
- [ ] Throwaway test accounts and their submissions deleted
- [ ] Schedule correct in Admin > Config > Time (11:00, 16:00; writeup window to 18:00 IST)
- [ ] Admin password changed, admin account email correct
- [ ] Backup + restore tested; manual RDS snapshot taken
- [ ] CloudWatch alarms: RDS CPU > 80%, RDS free storage, EC2 status check failed, EC2 CPU credit balance
- [ ] Rate limits: if many players share one network, `RATELIMIT_LOGIN`/`RATELIMIT_REGISTER` in `.env` are raised (default 30,5)
- [ ] Rules page and the "how to submit the writeup" text reviewed

**Day before**
- [ ] `./deploy/check.sh` is green; certificate valid for 30+ days
- [ ] Disk has plenty of free space (`df -h /`)
- [ ] Optional: Multi-AZ on for RDS; EC2 "unlimited" CPU credits on

**During the event**
- [ ] Keep `./deploy/compose.sh logs -f ctfd` and `./deploy/check.sh` handy
- [ ] Hourly backups run automatically on 29 Nov (check `/var/log/zerodayctf-backup.log`)

**After the event**
- [ ] Final backup + manual snapshot, export results from Admin > Config > Backup
- [ ] Scale RDS/EC2 down or stop them to save cost

---

## Troubleshooting

| Symptom | Likely cause and fix |
| --- | --- |
| `502 Bad Gateway` | App not healthy yet: `./deploy/compose.sh logs --tail 100 ctfd` |
| App cannot reach the database | RDS security group must allow 3306 from the EC2 security group; wrong endpoint/password in `DATABASE_URL`; run `scripts/db_check.py` |
| Certificate request fails | DNS not pointing at the Elastic IP yet, or port 80 blocked in the EC2 security group |
| Everyone logged out after a restart | `SECRET_KEY` changed. Keep the same value in `.env` |
| Players see "Too many requests" | Raise `RATELIMIT_LOGIN` / `RATELIMIT_REGISTER` in `.env`, then `./deploy/compose.sh up -d` |
| Site shows old design after an update | Browsers cache; hard refresh (Cmd+Shift+R) |

Never expose RDS publicly, never commit `.env`, and never paste passwords into chats or tickets.
