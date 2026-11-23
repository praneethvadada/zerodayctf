#!/usr/bin/env bash
# One-time preparation of a fresh Ubuntu 22.04 / 24.04 EC2 server.
# Run as the normal "ubuntu" user:   bash deploy/server-setup.sh
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then echo "Run this as the ubuntu user (it uses sudo), not as root."; exit 1; fi

echo "==> System updates"
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y

echo "==> Base packages"
sudo apt-get install -y ca-certificates curl gnupg ufw fail2ban unattended-upgrades python3 dnsutils jq

echo "==> Docker Engine + Compose plugin (official Docker repository)"
if ! command -v docker >/dev/null 2>&1; then
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
sudo usermod -aG docker "$USER"

echo "==> Firewall (SSH, HTTP, HTTPS only)"
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

echo "==> Brute-force protection for SSH and automatic security updates"
sudo systemctl enable --now fail2ban
echo 'APT::Periodic::Update-Package-Lists "1"; APT::Periodic::Unattended-Upgrade "1";' | sudo tee /etc/apt/apt.conf.d/20auto-upgrades >/dev/null

echo "==> Swap file (safety net on small instances)"
if [ "$(swapon --show | wc -l)" -eq 0 ] && [ "$(free -m | awk '/Mem:/ {print $2}')" -lt 6000 ]; then
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "==> Kernel limits for many simultaneous connections"
printf 'net.core.somaxconn=4096\nnet.ipv4.tcp_max_syn_backlog=4096\nfs.file-max=200000\n' | sudo tee /etc/sysctl.d/99-zerodayctf.conf >/dev/null
sudo sysctl --system >/dev/null

echo
echo "Done. Log out and back in once so the 'docker' group applies, then continue with deploy/README.md."
