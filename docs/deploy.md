# Deploying to AWS

What this sets up: one EC2 instance running the Docker Compose stack (Caddy, the API,
Postgres, nightly backups), an Elastic IP with a domain pointing at it, HTTPS from Let's
Encrypt, and backups copied to S3.

```
browser ──https──▶ EC2 t4g.small ─┬─ web     Caddy: TLS, frontend, /api proxy
                                  ├─ api     FastAPI (not exposed)
                                  ├─ db      Postgres 16 (volume)
                                  └─ backup  nightly pg_dump ──▶ S3 (14-day expiry)
```

Cost, on demand in ca-central-1: the instance about $13/month, its public IPv4 about
$3.60, 20 GB of gp3 about $1.80, S3 cents. About $18/month in total; new AWS accounts
get starter credits that cover the first months.

Region: the examples use `ca-central-1` (Montreal). Any region works; keep the bucket and
the instance in the same one.

## 1. Account basics

1. Turn on MFA for the root user, then stop using it: create an IAM Identity Center
   user (or an IAM user) with admin rights for yourself and sign in with that.
2. Billing → Budgets → Create budget → Cost budget, monthly, **$20**, email alerts at 80%
   and 100% of actual cost, plus 100% of forecasted. Under advanced options, exclude
   credits, so the alert reflects real usage even while credits pay for it.

## 2. Backups bucket

1. S3 → Create bucket, e.g. `zhiaowei-leetcode-backups`. Keep "Block all public access"
   on.
2. Management → Create lifecycle rule: prefix `coding-tracker/`, expire current
   versions after **14 days**.
3. IAM → Users → Create user `leetcode-backup`, no console access. Add this inline
   policy (it can add backups and nothing else, not even delete them; the lifecycle rule
   does that), then create an access key for it:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Action": "s3:PutObject",
       "Resource": "arn:aws:s3:::zhiaowei-leetcode-backups/coding-tracker/*"
     }]
   }
   ```

## 3. The instance

1. EC2 → Launch instance:
   - Ubuntu Server 24.04 LTS, **64-bit (Arm)**; type **t4g.small**
   - a new key pair (keep the `.pem`); 20 GB gp3
   - security group: SSH (22) from **My IP** only; HTTP (80) and HTTPS (443) from anywhere
   - Advanced details → Metadata version: **V2 only**
2. Elastic IPs → Allocate → Associate with the instance. This address doesn't change when
   the instance restarts.

## 4. Domain

Add an A record `leetcode` → the Elastic IP at your DNS provider (for zhiaowei.dev:
`leetcode.zhiaowei.dev`). Check it before going on, since Caddy needs it to get a
certificate:

```bash
dig +short leetcode.zhiaowei.dev
```

`.dev` domains are HTTPS-only in every browser, so the site won't open until Caddy has its
certificate.

## 5. GitHub sign-in

GitHub → Settings → Developer settings → OAuth Apps → New OAuth App:

- Homepage URL: `https://leetcode.zhiaowei.dev`
- Authorization callback URL: `https://leetcode.zhiaowei.dev/api/auth/callback/github`

Generate a client secret. Keep this app for the server only; for trying sign-in on your
machine, make a second one with the callback `http://localhost:5173/api/auth/callback/github`.

## 6. Server setup

```bash
ssh -i leetcode.pem ubuntu@<elastic-ip>

sudo apt update && sudo apt -y upgrade && sudo apt -y install unattended-upgrades
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu && exit          # log in again for the group to apply

# 1 GB of swap: Postgres, the API and Caddy share 2 GB
sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

sudo git clone https://github.com/capy-zhiao/coding-tracker.git /opt/coding-tracker
sudo chown -R ubuntu: /opt/coding-tracker && cd /opt/coding-tracker
cp .env.example .env && cp backup.env.example backup.env && chmod 600 .env backup.env
```

Edit `.env`:

```bash
SITE_ADDRESS=leetcode.zhiaowei.dev
PUBLIC_BASE_URL=https://leetcode.zhiaowei.dev
POSTGRES_PASSWORD=<python3 -c "import secrets; print(secrets.token_urlsafe(24))">
AUTH_MODE=github
SESSION_SECRET=<python3 -c "import secrets; print(secrets.token_urlsafe(48))">
GITHUB_CLIENT_ID=<from step 5>
GITHUB_CLIENT_SECRET=<from step 5>
OWNER_GITHUB_LOGIN=capy-zhiao
DEMO_ENABLED=true
TIMEZONE=America/Toronto
LLM_PROVIDER=deepseek          # optional: the owner's own AI key
DEEPSEEK_API_KEY=...
```

and `backup.env`: `BACKUP_BUCKET`, `AWS_REGION` and the `leetcode-backup` access key from
step 2. Then start it:

```bash
docker compose up -d --build
docker compose ps                     # all four "running", api "healthy"
docker compose logs -f web            # watch Caddy obtain the certificate
```

## 7. Check it

- `https://leetcode.zhiaowei.dev` opens with a valid certificate
- Sign in with GitHub; "Try the demo" works in a private window
- `docker compose exec backup backup.sh`, then the file shows up in the bucket under
  `coding-tracker/`

## 8. Bring your own history

Sign in on the server once, so your account exists. Then, from your machine:

```bash
cd backend && ./.venv/bin/python -m app.tools export --login local > history.json
ssh -i leetcode.pem ubuntu@<elastic-ip> 'cd /opt/coding-tracker &&
  docker compose exec -T api python -m app.tools import --login capy-zhiao /dev/stdin' < history.json
```

The file goes in on standard input rather than through `docker compose cp`, which keeps
the copy's owner and mode, so the API's own user couldn't read it.

## 9. Updating

By hand, building on the server:

```bash
cd /opt/coding-tracker && git pull && docker compose up -d --build
```

The API runs any new migrations as it starts. Once automatic deploys are set up (next
section), pushing to main is enough.

## 10. Automatic deploys

`.github/workflows/deploy.yml` runs after CI passes on main. It builds the three images
on an ARM runner and pushes them to GHCR as `sha-<commit>` and `latest`. Then it has the
server check out that commit and run `deploy/update.sh`, which pulls exactly those images
and restarts what changed.

It reaches the server through AWS Systems Manager rather than SSH, so no port is opened
for GitHub's runners and GitHub stores no AWS keys. Each run signs in to AWS with GitHub's
OIDC token as a role that can only send commands to this one instance.

1. **The packages.** After the first run of the workflow, open each package on GitHub
   (profile → Packages → `coding-tracker-api`, `-web`, `-backup`) → Package settings →
   Change visibility → Public, so the server can pull without a token. The code is
   public anyway.
2. **Let SSM manage the instance.** IAM → Roles → Create role → AWS service, EC2 → attach
   `AmazonSSMManagedInstanceCore` → name it `leetcode-ec2`. EC2 → the instance → Actions →
   Security → Modify IAM role → `leetcode-ec2`. Ubuntu AMIs already run the SSM agent;
   after a few minutes the instance shows up under Systems Manager → Fleet Manager.
3. **Trust GitHub.** IAM → Identity providers → Add provider → OpenID Connect, provider
   URL `https://token.actions.githubusercontent.com`, audience `sts.amazonaws.com`.
4. **The deploy role.** IAM → Roles → Create role → Custom trust policy, with this one,
   which only lets main of this repository assume it. GitHub's token names the
   repository as `owner@<owner-id>/repo@<repo-id>`, so a renamed repository, or someone
   else's taking the old name, doesn't match. Look the two ids up with:

   ```bash
   curl -s https://api.github.com/repos/capy-zhiao/coding-tracker | jq '.owner.id, .id'
   ```

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Principal": {"Federated": "arn:aws:iam::<account-id>:oidc-provider/token.actions.githubusercontent.com"},
       "Action": "sts:AssumeRoleWithWebIdentity",
       "Condition": {
         "StringEquals": {
           "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
           "token.actions.githubusercontent.com:sub": "repo:capy-zhiao@<owner-id>/coding-tracker@<repo-id>:ref:refs/heads/main"
         }
       }
     }]
   }
   ```

   and give it this inline policy:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": "ssm:SendCommand",
         "Resource": [
           "arn:aws:ec2:ca-central-1:<account-id>:instance/<instance-id>",
           "arn:aws:ssm:ca-central-1::document/AWS-RunShellScript"
         ]
       },
       {"Effect": "Allow", "Action": "ssm:GetCommandInvocation", "Resource": "*"}
     ]
   }
   ```

5. **Tell the workflow.** GitHub → the repository → Settings → Secrets and variables →
   Actions → Variables: `AWS_DEPLOY_ROLE_ARN` (the role's ARN), `AWS_REGION`
   (`ca-central-1`), `EC2_INSTANCE_ID` (`i-...`), `DEPLOY_DOMAIN`
   (`leetcode.zhiaowei.dev`). Variables, not secrets: none of these grant anything on
   their own.

Run it once from the Actions tab (Deploy → Run workflow) to check. `DEPLOY_DOMAIN` also
turns on `uptime.yml`, which requests `/api/health` every 30 minutes and fails, emailing
you, when the site doesn't answer.

## 11. Restoring a backup

```bash
docker compose exec backup ls /backups                       # the last three
# or fetch an older one from S3 into the volume:
aws s3 cp s3://<bucket>/coding-tracker/<file> . && docker compose cp <file> backup:/backups/

docker compose stop api
docker compose exec backup sh -c \
  'pg_restore --clean --if-exists --no-owner -d "$PGDATABASE" /backups/<file>'
docker compose start api
```

## When something's wrong

| Symptom | Look at |
|---|---|
| Browser says the certificate is invalid, or nothing loads | `docker compose logs web`: DNS not pointing here yet, or 80/443 closed in the security group |
| Page loads, every request fails with 502 | `docker compose logs api`: a missing setting stops it at startup |
| Sign-in comes back to "didn't complete" | `docker compose logs api` for the reason; the callback URL in the OAuth app must match `PUBLIC_BASE_URL` exactly |
| Out of memory | `free -h`; the swap from step 6 |
| Deploy fails with "Not authorized to perform sts:AssumeRoleWithWebIdentity" | CloudTrail → Event history → `AssumeRoleWithWebIdentity`: the event's `userName` is the `sub` GitHub sent; the trust policy must match it exactly |
