# 👶 Baby Steps: Deploy to Ubuntu Server

## 🎯 Super Simple Step-by-Step Guide

---

## Step 1: Connect to Your Server

**On your local computer, open terminal/PowerShell:**

```bash
ssh ubuntu@YOUR_SERVER_IP
```

**Replace `YOUR_SERVER_IP` with your actual server IP address.**

**Example:**
```bash
ssh ubuntu@192.168.1.100
```

**If asked for password, enter your server password.**

---

## Step 2: Install Docker (Copy & Paste These Commands)

**On the server, run these commands one by one:**

```bash
# Update system
sudo apt update
sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add your user to docker group
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

**Then log out and back in:**
```bash
exit
```

**Then SSH back in:**
```bash
ssh ubuntu@YOUR_SERVER_IP
```

**Verify Docker works:**
```bash
docker --version
docker-compose --version
```

---

## Step 3: Upload Your Project Files

### Option A: Using Git (If you have a repository)

```bash
# On the server
cd /opt
sudo mkdir -p Project_Up
sudo chown $USER:$USER Project_Up
cd Project_Up
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git .
```

### Option B: Using SCP (Upload from your computer)

**On your LOCAL computer (not server), run:**

```bash
# Navigate to your project folder
cd /path/to/Project_Up

# Upload entire project (excluding venv, node_modules)
# Note: run_refactored.py is now in backend/ directory
scp -r backend frontend app docker-compose.yml docker-compose.prod.yml requirements.txt .env.prod ubuntu@YOUR_SERVER_IP:/opt/Project_Up/
```

**Or create a zip and upload:**

**On your LOCAL computer:**
```bash
# Create zip (excluding unnecessary files)
zip -r project.zip . -x "venv/*" "node_modules/*" "__pycache__/*" "*.db" "*.log" "reports/*" "instance/*" "logs/*"

# Upload zip
scp project.zip ubuntu@YOUR_SERVER_IP:/opt/

# On server, extract
ssh ubuntu@YOUR_SERVER_IP
cd /opt
unzip project.zip -d Project_Up
cd Project_Up
```

---

## Step 4: Upload Credentials File (IMPORTANT!)

**On your LOCAL computer, run:**

```bash
scp service-account-creds.json ubuntu@YOUR_SERVER_IP:/opt/Project_Up/
```

**This uploads your Google credentials file to the server.**

---

## Step 5: Create .env File on Server

**On the server, run:**

```bash
cd /opt/Project_Up
nano .env
```

**Press `Ctrl+Shift+V` to paste, or type this:**

```bash
# Database Passwords (CHANGE THESE!)
MYSQL_ROOT_PASSWORD=MySecureRootPassword123!
MYSQL_PASSWORD=MySecureDBPassword123!
MYSQL_USER=scheduling_user
MYSQL_DATABASE=scheduling_system

# Flask Secrets (CHANGE THESE! Generate random strings)
SECRET_KEY=change_this_to_a_random_32_character_string
JWT_SECRET_KEY=change_this_to_another_random_32_character_string
FLASK_ENV=production

# Google Sheets (path inside Docker)
GOOGLE_APPLICATION_CREDENTIALS=/app/service-account-creds.json

# Celery/Redis
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
```

**To save:**
1. Press `Ctrl+X`
2. Press `Y`
3. Press `Enter`

**Generate random secrets (optional but recommended):**
```bash
openssl rand -hex 32
```
**Copy the output and use it for SECRET_KEY and JWT_SECRET_KEY**

---

## Step 6: Start Everything!

**On the server, run:**

```bash
cd /opt/Project_Up

# Start all services
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

**Wait 1-2 minutes for everything to start.**

---

## Step 7: Run Database Setup

**On the server, wait 30 seconds, then run:**

```bash
# Wait for MySQL
sleep 30

# Run migrations
docker-compose -f docker-compose.yml -f docker-compose.prod.yml exec backend alembic upgrade head
```

---

## Step 8: Check if It's Working

**On the server, run:**

```bash
# Check all services are running
docker-compose -f docker-compose.yml -f docker-compose.prod.yml ps

# Test backend
curl http://localhost:8000/api/v1/health
```

**You should see: `{"status": "healthy"}` or similar**

---

## Step 9: Access Your App!

**Open your web browser and go to:**

```
http://YOUR_SERVER_IP
```

**Or if you set up a domain:**

```
http://your-domain.com
```

**Backend API:**
```
http://YOUR_SERVER_IP:8000/api/v1/health
```

---

## Step 10: Trigger Initial Sync (Optional)

**On the server, run:**

```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml exec backend python trigger_sync.py
```

---

## ✅ Done! Your App is Live!

---

## 🔧 Common Commands You'll Need

### View Logs
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml logs -f
```

### Restart Services
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml restart
```

### Stop Everything
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml down
```

### Start Everything
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## 🆘 Troubleshooting

### "Permission denied" error
```bash
sudo chown -R $USER:$USER /opt/Project_Up
```

### "Port already in use"
```bash
# Find what's using the port
sudo lsof -i :80
sudo lsof -i :8000

# Stop it or change ports in docker-compose.yml
```

### "Cannot connect to Docker"
```bash
# Make sure you're in docker group
sudo usermod -aG docker $USER
# Log out and back in
exit
```

### "Credentials file not found"
```bash
# Check if file exists
ls -la /opt/Project_Up/service-account-creds.json

# If not, upload it again (from your local computer):
# scp service-account-creds.json ubuntu@YOUR_SERVER_IP:/opt/Project_Up/
```

---

## 📝 Quick Checklist

- [ ] Connected to server via SSH
- [ ] Docker installed
- [ ] Project files uploaded
- [ ] `service-account-creds.json` uploaded
- [ ] `.env` file created with passwords
- [ ] Services started with `docker-compose up -d`
- [ ] Migrations run
- [ ] Can access `http://YOUR_SERVER_IP`

---

**That's it! Your app should be running! 🎉**

