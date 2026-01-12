# Bxthre3 Deployment Guide

This guide explains how to deploy the Bxthre3 system and push it to GitHub.

## Prerequisites

### GitHub Setup

1. **Create a GitHub Account**: If you don't have one, create an account at https://github.com
2. **Create the Repository**:
   - Go to https://github.com/new
   - Repository name: `bxthre3`
   - Make it **public** or **private** as desired
   - Do NOT initialize with README, .gitignore, or license (we already have these)
   - Click "Create repository"

3. **Configure Git Credentials**:
   
   Option A: Using Personal Access Token (Recommended)
   ```bash
   # Generate a token at: https://github.com/settings/tokens
   # Scopes needed: repo (for private repos) or public_repo (for public repos)
   
   git config --global user.name "bxthre3"
   git config --global user.email "your-email@example.com"
   ```

   Option B: Using SSH (Recommended for frequent deployments)
   ```bash
   # Generate SSH key if you don't have one
   ssh-keygen -t ed25519 -C "your-email@example.com"
   
   # Add to GitHub: https://github.com/settings/ssh/new
   cat ~/.ssh/id_ed25519.pub
   ```

## Initial Deployment Steps

### 1. Clone or Initialize

If you're starting fresh:
```bash
git clone https://github.com/bxthre3/bxthre3.git
cd bxthre3
```

If you've already created the files (like we did):
```bash
cd bxthre3
git remote set-url origin https://github.com/bxthre3/bxthre3.git
```

### 2. Push to GitHub

Using HTTPS with Personal Access Token:
```bash
# This will prompt for username and password (use token as password)
git push -u origin main
```

Using SSH:
```bash
git remote set-url origin git@github.com:bxthre3/bxthre3.git
git push -u origin main
```

## Production Deployment

### Single-Device Deployment

For testing on a single machine:

```bash
# Terminal 1: Start Controller + Node Manager
./bootstrap.sh
# Select option 2 (Controller + Node Manager)
# Set RAM per node: 128

# Terminal 2: Start UI
./bootstrap.sh
# Select option 1 (UI Node)
# Controller IP: 127.0.0.1
```

### Multi-Device Deployment

For a distributed setup:

#### Device 1: Controller + Node Manager
```bash
./bootstrap.sh
# Select option 2 (Controller + Node Manager)
# Set RAM per node: 128
# Note the Controller IP address
```

#### Device 2-N: Node Managers
```bash
./bootstrap.sh
# Select option 3 (Node Manager only)
# Controller IP: <Device 1 IP>
# Set RAM per node: 128
```

#### Any Device: UI Node
```bash
./bootstrap.sh
# Select option 1 (UI Node)
# Controller IP: <Controller Device IP>
```

## Cloud Deployment

### AWS EC2

```bash
# Launch an EC2 instance (Ubuntu 22.04 recommended)
# SSH into the instance
ssh -i your-key.pem ubuntu@your-instance-ip

# Clone repository
git clone https://github.com/bxthre3/bxthre3.git
cd bxthre3

# Run bootstrap
chmod +x bootstrap.sh
./bootstrap.sh

# For Controller + Node Manager:
# Select option 2
# Configure security group to allow port 5000
```

### DigitalOcean Droplet

```bash
# Create droplet (Ubuntu 22.04)
# SSH into the droplet
ssh root@your-droplet-ip

# Clone and setup
git clone https://github.com/bxthre3/bxthre3.git
cd bxthre3
chmod +x bootstrap.sh
./bootstrap.sh

# Configure firewall
ufw allow 5000/tcp
ufw enable
```

### Google Cloud Platform

```bash
# Create VM instance
gcloud compute instances create bxthre3-controller \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --machine-type=e2-medium \
    --tags=http-server,https-server

# SSH into instance
gcloud compute ssh bxthre3-controller

# Clone and setup
git clone https://github.com/bxthre3/bxthre3.git
cd bxthre3
chmod +x bootstrap.sh
./bootstrap.sh

# Configure firewall
gcloud compute firewall-rules create allow-bxthre3 \
    --allow tcp:5000 \
    --source-ranges 0.0.0.0/0
```

## Android Termux Deployment

```bash
# Install Termux from F-Droid (recommended) or Google Play
apt update && apt upgrade

# Install dependencies
pkg install git python cmake clang curl

# Clone repository
git clone https://github.com/bxthre3/bxthre3.git
cd bxthre3

# Run bootstrap
chmod +x bootstrap.sh
./bootstrap.sh

# Select Node Manager only
# Controller IP: <your controller device IP>
```

## Docker Deployment (Optional)

Create a `Dockerfile`:

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    git \
    cmake \
    clang \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

RUN pip install -r requirements.txt

EXPOSE 5000

# Default to running all components
CMD ["python3", "bxthre3_controller.py"]
```

Build and run:
```bash
docker build -t bxthre3 .
docker run -p 5000:5000 bxthre3
```

## Systemd Service (Linux)

Create `/etc/systemd/system/bxthre3-controller.service`:

```ini
[Unit]
Description=Bxthre3 Controller Node
After=network.target

[Service]
Type=simple
User=bxthre3
WorkingDirectory=/opt/bxthre3
ExecStart=/usr/bin/python3 /opt/bxthre3/bxthre3_controller.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable bxthre3-controller
sudo systemctl start bxthre3-controller
sudo systemctl status bxthre3-controller
```

## Monitoring

### View Logs

```bash
# Controller logs
tail -f logs/controller.log

# Node Manager logs
tail -f logs/node_manager.log

# Host Node logs
tail -f logs/host_*.log
```

### Check Node Status

Use the UI Node to view:
- Connected nodes
- Task execution status
- RAM usage per node
- DAG progress

## Updates

### Update from GitHub

```bash
cd bxthre3
git pull origin main

# If Python scripts changed, restart services
sudo systemctl restart bxthre3-controller
```

### Update WASM Modules

```bash
# Place new .wasm files in wasm_modules/
# They will be automatically detected by Host Nodes
```

## Troubleshooting

### Cannot Connect to Controller

1. Check Controller is running:
   ```bash
   ps aux | grep bxthre3_controller
   ```

2. Check port is open:
   ```bash
   netstat -tlnp | grep 5000
   ```

3. Check firewall:
   ```bash
   sudo ufw status
   sudo ufw allow 5000/tcp
   ```

### Git Push Fails

If you see "Authentication failed":

1. Generate a Personal Access Token: https://github.com/settings/tokens
2. Use token as password when prompted
3. Or switch to SSH:
   ```bash
   git remote set-url origin git@github.com:bxthre3/bxthre3.git
   ```

### WASM Runtime Missing

```bash
cd bxthre3
chmod +x bootstrap.sh
./bootstrap.sh --force-download
```

## Security Considerations

1. **Controller Access**: In production, use authentication for Controller access
2. **Network Security**: Use VPN or SSH tunneling for Controller connections
3. **Input Validation**: Validate all WASM modules before deployment
4. **Resource Limits**: Set appropriate RAM limits to prevent abuse
5. **Firewall**: Only expose necessary ports

## Backup and Recovery

### Backup Configuration

```bash
# Backup DAGs
tar -czf dags-backup.tar.gz dags/

# Backup WASM modules
tar -czf wasm-backup.tar.gz wasm_modules/
```

### Recovery

```bash
# Restore from backup
tar -xzf dags-backup.tar.gz
tar -xzf wasm-backup.tar.gz
```

## Performance Tuning

### Optimize Node Count

Adjust RAM per node based on workload:
- CPU-intensive: 64-128 MB per node
- Memory-intensive: 256-512 MB per node
- I/O-intensive: 128-256 MB per node

### Network Optimization

- Use local network when possible
- Minimize network latency between Controller and Nodes
- Consider using Redis for task queue in large deployments

## Scaling

### Horizontal Scaling

Add more devices running Node Manager:
```bash
./bootstrap.sh
# Select option 3 (Node Manager only)
# Controller IP: <controller-ip>
```

### Vertical Scaling

Increase RAM per node:
```bash
python3 bxthre3_node_manager.py --ram-per-node 256
```

## Support

For issues and questions:
- GitHub Issues: https://github.com/bxthre3/bxthre3/issues
- Documentation: https://github.com/bxthre3/bxthre3/blob/main/README.md