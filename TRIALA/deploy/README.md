VPS Deployment Guide — TRIALA
=============================

This guide prepares an Ubuntu VPS to run the TRIALA Flask app behind Nginx with Gunicorn and TLS via Certbot.

Prerequisites
- A domain name pointed to your VPS public IP (recommended for TLS).
- An Ubuntu server (20.04/22.04 recommended).
- SSH access to the server.

Quick steps (recommended)
1. On your local machine, push this project to GitHub (or copy the project to the server).
2. On the VPS:
   - Clone the repo into `/opt/triala` (or your chosen path):

```bash
sudo mkdir -p /opt
sudo chown $USER:$USER /opt
cd /opt
git clone https://github.com/USERNAME/TRIALA.git triala
cd triala
```

3. Run the provided setup script (replace `example.com` with your domain):

```bash
chmod +x deploy/ubuntu_setup.sh
./deploy/ubuntu_setup.sh your.domain.example
```

What the script does
- Installs system packages: `git`, `python3-venv`, `python3-pip`, `nginx`, `certbot`, `ufw`.
- Creates a Python virtualenv at `venv/` and installs `requirements.txt`.
- Initializes the SQLite DB with `python guest_house.py init-db`.
- Writes a `systemd` service at `/etc/systemd/system/triala.service` to run Gunicorn bound to `127.0.0.1:8000`.
- Writes an Nginx site config and enables it.
- Restarts Nginx and opens firewall ports.
- Optionally runs `certbot` to obtain TLS certificates for your domain.

Manual steps (if you prefer to do them by hand)
- Create virtualenv and install deps:

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python guest_house.py init-db
```

- Create a `systemd` unit (example in `deploy/triala.service`). Copy it to `/etc/systemd/system/triala.service`, edit paths/user as needed, then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now triala
sudo journalctl -u triala -f
```

- Nginx: copy `deploy/nginx_triala.conf` to `/etc/nginx/sites-available/triala`, replace `server_name`, then enable and restart:

```bash
sudo ln -s /etc/nginx/sites-available/triala /etc/nginx/sites-enabled/triala
sudo nginx -t
sudo systemctl restart nginx
```

- Obtain TLS certs (Certbot):

```bash
sudo certbot --nginx -d your.domain.example
```

Notes
- The script uses `gunicorn` (recommended on Linux). We added `gunicorn` to `requirements.txt`.
- For production, consider using a managed DB (Postgres). SQLite is OK for small deployments but may not be suitable for multiple instances or heavy load.
- Set environment variables (secret key, database credentials) via a systemd `EnvironmentFile` or an env var manager — do NOT commit secrets.

If you want, I can:
- Generate a ready-to-run `systemd` install command that writes the service file with your chosen install path and user.
- Produce an `nginx` config with your real domain (paste the domain) and example `certbot` command.
