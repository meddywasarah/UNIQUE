#!/usr/bin/env bash
set -euo pipefail

# Run this on a fresh Ubuntu server AFTER cloning the repo into /opt/triala
# Example flow on the server:
# sudo mkdir -p /opt
# sudo chown $USER:$USER /opt
# cd /opt
# git clone https://github.com/USERNAME/TRIALA.git triala
# cd triala
# ./deploy/ubuntu_setup.sh example.com

DOMAIN=${1:-"example.com"}
PROJECT_DIR=$(pwd)
VENV_DIR="$PROJECT_DIR/venv"
SERVICE_NAME=triala

echo "Updating packages and installing prerequisites..."
sudo apt update
sudo apt install -y git python3-venv python3-pip nginx certbot python3-certbot-nginx ufw

echo "Creating virtual environment..."
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

echo "Initializing database (SQLite)..."
python guest_house.py init-db || true

echo "Writing systemd service to /etc/systemd/system/${SERVICE_NAME}.service"
sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null <<'EOF'
[Unit]
Description=TRIALA Flask app
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/triala
Environment=PATH=/opt/triala/venv/bin
ExecStart=/opt/triala/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 web_app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now ${SERVICE_NAME}

echo "Configuring Nginx..."
sudo tee /etc/nginx/sites-available/${SERVICE_NAME} > /dev/null <<EOF
server {
    listen 80;
    server_name ${DOMAIN};

    location / {
        proxy_pass http://127.0.0.1:8000;
        include proxy_params;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    client_max_body_size 10M;
}
EOF

sudo ln -sf /etc/nginx/sites-available/${SERVICE_NAME} /etc/nginx/sites-enabled/${SERVICE_NAME}
sudo nginx -t
sudo systemctl restart nginx

echo "Opening firewall for Nginx and SSH..."
sudo ufw allow 'OpenSSH'
sudo ufw allow 'Nginx Full'
sudo ufw --force enable

if [ "$DOMAIN" != "example.com" ]; then
  echo "Obtaining TLS certificate via Certbot for ${DOMAIN}..."
  sudo certbot --nginx -d ${DOMAIN} --non-interactive --agree-tos -m admin@${DOMAIN} || true
  sudo systemctl reload nginx
else
  echo "Reminder: replace example.com with your real domain and re-run certbot to obtain TLS certs."
fi

echo "Deployment finished. Service: ${SERVICE_NAME} should be running and proxied by Nginx."
