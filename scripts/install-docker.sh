#!/bin/sh
# Explicit opt-in installation using Docker's official Ubuntu/Debian apt repository.
set -eu
if [ "$(id -u)" != 0 ]; then
    echo 'Run with root privileges: sudo sh start.sh --install-docker' >&2
    exit 1
fi
. /etc/os-release
case "$ID" in ubuntu|debian) ;;*) echo 'Automatic installation supports Ubuntu/Debian only. Install Docker Engine and Compose v2 using the official instructions.' >&2;exit 1;;esac
apt-get update
apt-get install -y ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL "https://download.docker.com/linux/$ID/gpg" -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/%s %s stable\n' \
    "$(dpkg --print-architecture)" "$ID" "${UBUNTU_CODENAME:-$VERSION_CODENAME}" > /etc/apt/sources.list.d/ai07-docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
