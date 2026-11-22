# DocChat Production Deployment Guide

This guide covers deploying DocChat to various cloud platforms and production environments.

## Table of Contents

- [Pre-Deployment Checklist](#pre-deployment-checklist)
- [Environment Variables](#environment-variables)
- [Deployment Options](#deployment-options)
  - [Docker Deployment](#docker-deployment)
  - [AWS Deployment](#aws-deployment)
  - [Heroku Deployment](#heroku-deployment)
  - [Railway Deployment](#railway-deployment)
  - [Google Cloud Platform](#google-cloud-platform)
  - [Azure Deployment](#azure-deployment)
- [Database Setup](#database-setup)
- [SSL/TLS Configuration](#ssltls-configuration)
- [Monitoring & Logging](#monitoring--logging)
- [Backup Strategies](#backup-strategies)
- [Performance Tuning](#performance-tuning)

## Pre-Deployment Checklist

Before deploying to production, ensure you have:

- [ ] PostgreSQL database provisioned (managed service recommended)
- [ ] OpenAI API key with sufficient credits
- [ ] Domain name and DNS configured (if using custom domain)
- [ ] SSL/TLS certificate (Let's Encrypt or cloud provider)
- [ ] Secure SECRET_KEY generated (32+ bytes, random)
- [ ] Environment variables configured
- [ ] Database migrations tested
- [ ] Frontend production build tested locally
- [ ] Security review completed
- [ ] Backup strategy in place

## Environment Variables

### Backend (.env)

```bash
# Required
DATABASE_URL=postgresql://user:password@host:5432/dbname
SECRET_KEY=your-super-secret-key-min-32-bytes
OPENAI_API_KEY=sk-your-openai-api-key

# Optional - Production Settings
ENVIRONMENT=production
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
JWT_EXPIRATION_DAYS=30
MAX_UPLOAD_SIZE=10485760  # 10MB in bytes

# Database (if using separate config)
DB_HOST=your-db-host.cloud.provider.com
DB_PORT=5432
DB_USER=docchat_user
DB_PASSWORD=secure-db-password
DB_NAME=docchat_prod
```

### Frontend (.env)

```bash
# For single-server deployment (recommended)
VITE_API_BASE_URL=

# For separate frontend/backend deployment
VITE_API_BASE_URL=https://api.yourdomain.com
```

### Generating Secure SECRET_KEY

```bash
# Python method
python -c "import secrets; print(secrets.token_urlsafe(32))"

# OpenSSL method
openssl rand -base64 32
```

## Deployment Options

### Docker Deployment

#### Single Container (Simple)

**backend/Dockerfile**:
```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Build and Run**:
```bash
# Build backend
cd backend
docker build -t docchat-backend .

# Run with environment variables
docker run -d \
  -p 8000:8000 \
  -e DATABASE_URL=postgresql://... \
  -e SECRET_KEY=your-secret-key \
  -e OPENAI_API_KEY=your-openai-key \
  --name docchat \
  docchat-backend
```

#### Docker Compose (Recommended)

**docker-compose.yml**:
```yaml
version: '3.8'

services:
  db:
    image: postgres:14
    environment:
      POSTGRES_DB: docchat
      POSTGRES_USER: docchat
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U docchat"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://docchat:${DB_PASSWORD}@db:5432/docchat
      SECRET_KEY: ${SECRET_KEY}
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      ALLOWED_ORIGINS: ${ALLOWED_ORIGINS}
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./backend/uploads:/app/uploads
    restart: unless-stopped

volumes:
  postgres_data:
```

**Deploy with Docker Compose**:
```bash
# Create .env file
cat > .env << EOF
DB_PASSWORD=secure-db-password
SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
OPENAI_API_KEY=your-openai-key
ALLOWED_ORIGINS=http://localhost:8000
EOF

# Build frontend first
cd frontend
npm install
npm run build

# Start services
cd ..
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### AWS Deployment

#### Option 1: AWS Elastic Beanstalk

1. **Install EB CLI**:
```bash
pip install awsebcli
```

2. **Initialize EB**:
```bash
cd backend
eb init -p python-3.10 docchat-api --region us-east-1
```

3. **Create Environment**:
```bash
eb create docchat-prod --database.engine postgres --database.size 10
```

4. **Configure Environment Variables**:
```bash
eb setenv SECRET_KEY=your-secret-key \
  OPENAI_API_KEY=your-openai-key \
  ENVIRONMENT=production
```

5. **Deploy**:
```bash
# Build frontend
cd ../frontend
npm run build

# Deploy backend
cd ../backend
eb deploy
```

#### Option 2: AWS ECS (Fargate)

1. **Push Docker Image to ECR**:
```bash
# Create ECR repository
aws ecr create-repository --repository-name docchat

# Build and push image
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com
docker build -t docchat .
docker tag docchat:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/docchat:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/docchat:latest
```

2. **Create ECS Task Definition** (use AWS Console or CLI)

3. **Create RDS PostgreSQL Instance**

4. **Deploy to ECS Fargate**

#### Option 3: AWS EC2 (Manual)

```bash
# SSH into EC2 instance
ssh -i your-key.pem ubuntu@your-ec2-ip

# Install dependencies
sudo apt update
sudo apt install python3.10 python3-pip postgresql-client nginx nodejs npm

# Clone repository
git clone <your-repo>
cd DocChat

# Setup backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Edit .env with production values

# Build frontend
cd ../frontend
npm install
npm run build

# Setup systemd service (see below)
```

**Systemd Service** (`/etc/systemd/system/docchat.service`):
```ini
[Unit]
Description=DocChat Application
After=network.target postgresql.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/DocChat/backend
Environment="PATH=/home/ubuntu/DocChat/backend/venv/bin"
ExecStart=/home/ubuntu/DocChat/backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable docchat
sudo systemctl start docchat
sudo systemctl status docchat
```

### Heroku Deployment

1. **Create Heroku App**:
```bash
heroku create docchat-app
```

2. **Add PostgreSQL**:
```bash
heroku addons:create heroku-postgresql:mini
```

3. **Set Environment Variables**:
```bash
heroku config:set SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
heroku config:set OPENAI_API_KEY=your-openai-key
heroku config:set ENVIRONMENT=production
```

4. **Create Procfile**:
```
web: cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

5. **Deploy**:
```bash
# Build frontend
cd frontend
npm install
npm run build

# Commit and push
git add .
git commit -m "Production build"
git push heroku main
```

### Railway Deployment

1. **Install Railway CLI**:
```bash
npm install -g @railway/cli
```

2. **Initialize Project**:
```bash
railway login
railway init
```

3. **Add PostgreSQL**:
```bash
railway add postgresql
```

4. **Configure Build**:
Create `railway.json`:
```json
{
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT",
    "restartPolicyType": "ON_FAILURE"
  }
}
```

5. **Set Environment Variables**:
```bash
railway variables set SECRET_KEY=your-secret-key
railway variables set OPENAI_API_KEY=your-openai-key
```

6. **Deploy**:
```bash
railway up
```

### Google Cloud Platform

#### Option: Cloud Run (Serverless)

1. **Build and Push Container**:
```bash
gcloud builds submit --tag gcr.io/PROJECT_ID/docchat
```

2. **Create Cloud SQL PostgreSQL**:
```bash
gcloud sql instances create docchat-db --database-version=POSTGRES_14 --region=us-central1
```

3. **Deploy to Cloud Run**:
```bash
gcloud run deploy docchat \
  --image gcr.io/PROJECT_ID/docchat \
  --platform managed \
  --region us-central1 \
  --set-env-vars DATABASE_URL=postgresql://...,SECRET_KEY=...,OPENAI_API_KEY=... \
  --allow-unauthenticated
```

### Azure Deployment

#### Option: Azure App Service

1. **Create Resource Group**:
```bash
az group create --name docchat-rg --location eastus
```

2. **Create PostgreSQL**:
```bash
az postgres server create --resource-group docchat-rg --name docchat-db --location eastus --admin-user docchat --admin-password <password> --sku-name B_Gen5_1
```

3. **Create App Service**:
```bash
az webapp create --resource-group docchat-rg --plan docchat-plan --name docchat-app --runtime "PYTHON:3.10"
```

4. **Configure Environment**:
```bash
az webapp config appsettings set --resource-group docchat-rg --name docchat-app --settings SECRET_KEY=... OPENAI_API_KEY=...
```

5. **Deploy**:
```bash
az webapp up --name docchat-app --resource-group docchat-rg
```

## Database Setup

### Managed PostgreSQL Services

**Recommended Providers**:
- **AWS RDS**: High availability, automated backups
- **Heroku Postgres**: Simple setup, good for small apps
- **Railway**: Easy integration, affordable
- **DigitalOcean Managed Database**: Good balance of features/price
- **Google Cloud SQL**: Scalable, integrated with GCP services

### Database Configuration

```sql
-- Create database and user
CREATE DATABASE docchat;
CREATE USER docchat_user WITH PASSWORD 'secure-password';
GRANT ALL PRIVILEGES ON DATABASE docchat TO docchat_user;

-- Enable necessary extensions
\c docchat
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- For text search
```

### Running Migrations

```bash
cd backend

# Check current migration status
alembic current

# Run all pending migrations
alembic upgrade head

# Rollback one migration (if needed)
alembic downgrade -1
```

## SSL/TLS Configuration

### Let's Encrypt (Free SSL)

**Using Certbot with Nginx**:
```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Auto-renewal (already configured)
sudo certbot renew --dry-run
```

### Nginx Configuration

**`/etc/nginx/sites-available/docchat`**:
```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/docchat /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## Monitoring & Logging

### Application Monitoring

**CloudWatch (AWS)**:
```python
# Add to backend
import watchtower
import logging

logger = logging.getLogger()
logger.addHandler(watchtower.CloudWatchLogHandler())
```

**Sentry (Error Tracking)**:
```bash
pip install sentry-sdk
```

```python
# backend/app/main.py
import sentry_sdk

sentry_sdk.init(
    dsn="your-sentry-dsn",
    environment="production",
    traces_sample_rate=1.0
)
```

### Database Monitoring

- **AWS RDS**: Built-in CloudWatch metrics
- **pgAdmin**: Web-based PostgreSQL admin
- **DataDog**: Comprehensive database monitoring

### Log Aggregation

- **CloudWatch Logs** (AWS)
- **Stackdriver** (GCP)
- **Papertrail** (Heroku add-on)
- **Logtail** (Any platform)

## Backup Strategies

### Database Backups

**Automated Backups** (Managed Services):
- Enable daily automated backups
- Retention period: 7-30 days
- Point-in-time recovery enabled

**Manual Backup**:
```bash
# Backup
pg_dump -h host -U user -d docchat > backup_$(date +%Y%m%d).sql

# Restore
psql -h host -U user -d docchat < backup_20241107.sql
```

### File Storage Backups

**Uploaded Documents**:
- Store in S3/Cloud Storage with versioning enabled
- Alternative: Include uploads directory in server backups

**Backup Script**:
```bash
#!/bin/bash
BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# Database backup
pg_dump $DATABASE_URL > $BACKUP_DIR/db_$DATE.sql

# Upload files backup
tar -czf $BACKUP_DIR/uploads_$DATE.tar.gz /app/uploads

# Upload to S3
aws s3 cp $BACKUP_DIR/db_$DATE.sql s3://your-backup-bucket/
aws s3 cp $BACKUP_DIR/uploads_$DATE.tar.gz s3://your-backup-bucket/

# Clean up old local backups (keep last 7 days)
find $BACKUP_DIR -name "*.sql" -mtime +7 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete
```

## Performance Tuning

### Database Optimization

```sql
-- Analyze tables for query optimization
ANALYZE users;
ANALYZE documents;
ANALYZE chunks;
ANALYZE embeddings;

-- Check index usage
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC;

-- Vacuum database (reclaim storage)
VACUUM ANALYZE;
```

### Application Settings

**Uvicorn Workers** (backend):
```bash
# For production, use multiple workers
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

**Gunicorn** (alternative):
```bash
pip install gunicorn
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### CDN for Static Assets

- **CloudFront** (AWS)
- **Cloud CDN** (GCP)
- **Cloudflare** (Any platform)

Configure CDN to cache:
- `/assets/*` (frontend JS/CSS)
- `/vite.svg` and other static files

### Database Connection Pooling

**SQLAlchemy Configuration**:
```python
# backend/app/database.py
engine = create_engine(
    DATABASE_URL,
    pool_size=20,          # Max concurrent connections
    max_overflow=10,       # Allow 10 more if needed
    pool_pre_ping=True,    # Verify connections before use
    pool_recycle=3600      # Recycle connections after 1 hour
)
```

---

## Production Checklist

Before going live:

- [ ] SSL/TLS enabled and tested
- [ ] Environment variables secured (not in code)
- [ ] Database backups automated
- [ ] Error monitoring configured (Sentry)
- [ ] Rate limiting enabled
- [ ] CORS origins restricted to your domain
- [ ] Logs aggregation configured
- [ ] Health check endpoint tested
- [ ] API documentation accessible
- [ ] Load testing completed
- [ ] Disaster recovery plan documented

---

**Last Updated**: November 2024  
**DocChat Version**: 1.0.0

