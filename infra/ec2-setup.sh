#!/bin/bash
# EC2 Server Setup for BangaBot
# Run this on a fresh Ubuntu EC2 instance, or let the deploy workflow run it automatically.
# Idempotent — safe to run multiple times.

set -e

echo "===== BangaBot EC2 Setup ====="

# --- Docker ---
if ! [ -x "$(command -v docker)" ]; then
  echo "[setup] Installing Docker..."
  sudo apt-get update
  sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
  sudo add-apt-repository -y "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
  sudo apt-get update
  sudo apt-get install -y docker-ce
  sudo systemctl start docker
  sudo systemctl enable docker
  sudo usermod -aG docker "$USER"
else
  echo "[setup] Docker already installed"
fi

# --- Docker Compose ---
if ! [ -x "$(command -v docker-compose)" ]; then
  echo "[setup] Installing docker-compose..."
  sudo curl -L "https://github.com/docker/compose/releases/download/1.29.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
  sudo chmod +x /usr/local/bin/docker-compose
else
  echo "[setup] docker-compose already installed"
fi

# --- Docker daemon config (log rotation) ---
echo "[setup] Configuring Docker daemon (log rotation)..."
sudo mkdir -p /etc/docker
cat <<'DAEMON_JSON' | sudo tee /etc/docker/daemon.json > /dev/null
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
DAEMON_JSON

# --- DNS ---
echo "[setup] Configuring DNS..."
sudo mkdir -p /etc/systemd/resolved.conf.d
cat <<'DNS_CONF' | sudo tee /etc/systemd/resolved.conf.d/dns.conf > /dev/null
[Resolve]
DNS=8.8.8.8 8.8.4.4
FallbackDNS=1.1.1.1
DNS_CONF
sudo systemctl restart systemd-resolved 2>/dev/null || true
sudo ln -sf /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf 2>/dev/null || true

# --- Hostname resolution ---
HOSTNAME=$(hostname)
if ! grep -q "$HOSTNAME" /etc/hosts; then
  echo "[setup] Adding hostname to /etc/hosts..."
  echo "127.0.0.1 $HOSTNAME" | sudo tee -a /etc/hosts > /dev/null
fi

# --- Weekly Docker cleanup cron ---
echo "[setup] Installing weekly Docker cleanup cron..."
cat <<'CRON_SCRIPT' | sudo tee /etc/cron.weekly/docker-cleanup > /dev/null
#!/bin/bash
# Weekly Docker cleanup — remove images/cache older than 72h
docker system prune -af --filter "until=72h" 2>/dev/null
docker volume prune -f 2>/dev/null
echo "$(date) - Docker prune completed, disk: $(df -h / | tail -1 | awk '{print $5}')" >> /var/log/docker-cleanup.log
CRON_SCRIPT
sudo chmod +x /etc/cron.weekly/docker-cleanup

# --- Snap retention (Ubuntu snap eats disk) ---
echo "[setup] Configuring snap retention..."
sudo snap set system refresh.retain=2 2>/dev/null || true
cat <<'SNAP_SCRIPT' | sudo tee /etc/cron.monthly/snap-cleanup > /dev/null
#!/bin/bash
snap list --all | awk '/disabled/{print $1, $3}' | while read snapname revision; do
    snap remove "$snapname" --revision="$revision" 2>/dev/null
done
SNAP_SCRIPT
sudo chmod +x /etc/cron.monthly/snap-cleanup

# --- Restart Docker to pick up daemon.json ---
echo "[setup] Restarting Docker..."
sudo systemctl restart docker

# --- Deployment directory ---
mkdir -p ~/bangabot/src

echo "===== EC2 Setup Complete ====="
echo "Disk: $(df -h / | tail -1)"
