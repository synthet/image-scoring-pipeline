#!/usr/bin/env bash
# Keep image-scoring-gpu-shell idle and reachable over SSH from the LAN.
# Host keys and authorized_keys live on the gpu_shell_home volume (/root).
set -uo pipefail

start_sshd() {
  export DEBIAN_FRONTEND=noninteractive
  if ! command -v sshd >/dev/null 2>&1; then
    apt-get update
    apt-get install -y --no-install-recommends openssh-server
    rm -rf /var/lib/apt/lists/*
  fi

  mkdir -p /var/run/sshd /root/.ssh/hostkeys
  chmod 700 /root/.ssh /root/.ssh/hostkeys
  touch /root/.ssh/authorized_keys
  chmod 600 /root/.ssh/authorized_keys

  if [[ ! -f /root/.ssh/hostkeys/ssh_host_ed25519_key ]]; then
    ssh-keygen -t ed25519 -f /root/.ssh/hostkeys/ssh_host_ed25519_key -N ""
  fi

  cat > /root/.ssh/sshd_gpu_shell.conf <<'EOF'
Port 22
ListenAddress 0.0.0.0
HostKey /root/.ssh/hostkeys/ssh_host_ed25519_key
PermitRootLogin prohibit-password
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
AuthorizedKeysFile /root/.ssh/authorized_keys
PidFile /var/run/gpu-shell-sshd.pid
Subsystem sftp /usr/lib/openssh/sftp-server
UsePAM no
EOF

  if [[ -f /var/run/gpu-shell-sshd.pid ]] && kill -0 "$(cat /var/run/gpu-shell-sshd.pid)" 2>/dev/null; then
    return 0
  fi
  /usr/sbin/sshd -f /root/.ssh/sshd_gpu_shell.conf
}

if ! start_sshd; then
  echo "gpu-shell: sshd failed to start; container stays up for docker exec" >&2
fi
exec sleep infinity
