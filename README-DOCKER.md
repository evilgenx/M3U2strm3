# M3U2strm3 Web Interface - Docker Deployment

This document provides instructions for deploying M3U2strm3 as a Docker container with a web interface.

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose installed
- TMDb API key (free registration required)

### Docker Compose Version Compatibility

This project supports both Docker Compose v1 and v2:

**Docker Compose v2 (Recommended)**
- Modern, integrated with Docker CLI
- Better performance and features
- Command: `docker compose` (without hyphen)
- Available in Docker Desktop 3.4.0+ and Docker Engine 20.10.0+

**Docker Compose v1 (Legacy)**
- Standalone tool, separate installation
- Command: `docker-compose` (with hyphen)
- Still supported for backward compatibility

**Check your version:**
```bash
# Check Docker Compose v2
docker compose version

# Check Docker Compose v1
docker-compose --version
```

### 1. Clone and Setup

```bash
# Clone the repository
git clone https://github.com/your-username/M3U2strm3.git
cd M3U2strm3

# Copy environment file
cp .env.example .env
```

### 2. Configure Environment

Edit the `.env` file with your settings:

```bash
# .env file
TMDB_API_KEY=your_tmdb_api_key_here
EMBY_API_URL=https://your-emby-server.com
EMBY_API_KEY=your_emby_api_key
LOG_LEVEL=info
```

### 3. Build and Run

**Docker Compose v2 (Recommended):**
```bash
# Build and start the container
docker compose up -d

# Check container status
docker compose ps
```

**Docker Compose v1 (Legacy):**
```bash
# Build and start the container
docker-compose up -d

# Check container status
docker-compose ps
```

### 4. Access Web Interface

Open your browser and navigate to:
- **Web Interface**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs (FastAPI auto-generated docs)

## 📁 Directory Structure

```
M3U2strm3/
├── web/                    # Web interface files
│   ├── app.py             # FastAPI application
│   ├── templates/         # HTML templates
│   └── static/            # CSS, JS, images
├── api/                   # API models and schemas
├── utils/                 # Utility modules
├── output/                # Generated STRM files (mounted)
├── web/uploads/           # Uploaded M3U files (persistent)
├── web/configs/           # Configuration files (persistent)
├── web/logs/              # Application logs (persistent)
├── Dockerfile            # Multi-stage build
├── docker-compose.yml    # Docker Compose configuration
└── .env                  # Environment variables
```

## 🐳 Docker Commands

### Basic Operations

**Docker Compose v2 (Recommended):**
```bash
# Start the service
docker compose up -d

# Stop the service
docker compose down

# View logs
docker compose logs -f

# Restart the service
docker compose restart

# View container status
docker compose ps
```

**Docker Compose v1 (Legacy):**
```bash
# Start the service
docker-compose up -d

# Stop the service
docker-compose down

# View logs
docker-compose logs -f

# Restart the service
docker-compose restart

# View container status
docker-compose ps
```

### Advanced Operations

**Docker Compose v2 (Recommended):**
```bash
# Build with cache disabled
docker compose build --no-cache

# Scale the service (for load balancing)
docker compose up -d --scale m3u2strm3=3

# Execute commands in container
docker compose exec m3u2strm3 bash

# View resource usage
docker stats

# Clean up unused images and volumes
docker system prune -a
```

**Docker Compose v1 (Legacy):**
```bash
# Build with cache disabled
docker-compose build --no-cache

# Scale the service (for load balancing)
docker-compose up -d --scale m3u2strm3=3

# Execute commands in container
docker-compose exec m3u2strm3 bash

# View resource usage
docker stats

# Clean up unused images and volumes
docker system prune -a
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TMDB_API_KEY` | TMDb API key for content filtering | Required |
| `EMBY_API_URL` | Emby server URL for library refresh | Optional |
| `EMBY_API_KEY` | Emby API key | Optional |
| `LOG_LEVEL` | Logging level (debug, info, warning, error) | `info` |

### Volume Mounts

The following directories are mounted as Docker volumes for persistence:

- `/app/web/uploads` - Uploaded M3U files
- `/app/web/configs` - Configuration files
- `/app/web/logs` - Application logs
- `/app/output` - Generated STRM files

### Port Configuration

- **8000**: Web interface and API
- **80/443**: Optional reverse proxy (nginx)

## 🌐 Web Interface Features

### Dashboard
- Real-time processing progress
- System status monitoring
- Job queue management
- Statistics and metrics

### Configuration
- Form-based configuration editor
- File path management
- API key configuration
- Content filtering settings

### Processing
- File upload interface
- Real-time progress tracking
- Processing controls (start/stop)
- Results and statistics

### Logs
- Real-time log streaming
- Log level filtering
- Search functionality
- Download logs

## 🔒 Security

### Best Practices

1. **Use Environment Variables**: Store sensitive data like API keys in environment variables
2. **Non-Root User**: Container runs as non-root user for security
3. **Volume Permissions**: Ensure proper permissions on mounted volumes
4. **Network Security**: Use reverse proxy with SSL/TLS for production

### SSL/TLS Configuration

For production deployments, add nginx reverse proxy:

```yaml
# In docker-compose.yml
nginx:
  image: nginx:alpine
  ports:
    - "443:443"
  volumes:
    - ./nginx.conf:/etc/nginx/nginx.conf:ro
    - ./ssl:/etc/nginx/ssl:ro
  depends_on:
    - m3u2strm3
```

## 🚨 Troubleshooting

### Docker Permission Issues

**Permission denied accessing Docker daemon:**
This is the most common issue when starting with Docker. You have two options:

**Option 1: Add user to docker group (Recommended)**
```bash
# Add your user to the docker group
sudo usermod -aG docker $USER

# Apply the new group membership
newgrp docker

# Test that it works
docker info
```

**Option 2: Use sudo for Docker commands**
```bash
# Use sudo for all Docker operations
sudo docker-compose up -d
sudo docker-compose logs
```

**Note:** The test script (`test-docker.sh`) will automatically detect permission issues and:
- Attempt to add your user to the docker group
- Fall back to using sudo if needed
- Provide clear guidance on how to fix permissions permanently

### Common Issues

**Container won't start:**
```bash
# Check logs for errors
docker-compose logs m3u2strm3

# Check if port 8000 is in use
netstat -an | grep 8000
```

**Permission denied on volumes:**
```bash
# Fix permissions (will prompt for sudo password)
sudo chown -R 1000:1000 web/uploads web/configs web/logs output
```

**TMDb API errors:**
- Verify API key is correct
- Check API rate limits
- Ensure network connectivity

**File upload issues:**
- Check volume mounts are correct
- Verify directory permissions
- Check available disk space

**Docker daemon not running:**
```bash
# Start Docker daemon
sudo systemctl start docker

# Enable Docker to start on boot
sudo systemctl enable docker

# Check Docker status
sudo systemctl status docker
```

### Health Checks

The container includes health checks that verify:
- Web server is responding
- API endpoints are accessible
- Database connections (if applicable)

```bash
# Check health status
docker-compose ps
```

### Debug Mode

Enable debug logging:

```bash
# Set log level to debug
export LOG_LEVEL=debug
docker-compose up -d
```

## 📊 Monitoring

### Docker Metrics

```bash
# View container resource usage
docker stats m3u2strm3

# View logs with timestamps
docker-compose logs -t m3u2strm3
```

### Application Metrics

The web interface provides:
- Processing progress
- Job queue status
- System resource usage
- Error tracking

### Log Analysis

```bash
# View recent logs
docker-compose logs --tail=100 m3u2strm3

# Follow logs in real-time
docker-compose logs -f m3u2strm3

# Filter logs by level
docker-compose logs m3u2strm3 | grep ERROR
```

## 🔄 Updates and Maintenance

### Updating the Application

```bash
# Pull latest changes
git pull

# Rebuild and restart
docker-compose up -d --build
```

### Backup and Restore

```bash
# Backup configuration and data
tar -czf backup-$(date +%Y%m%d).tar.gz web/configs web/uploads web/logs output

# Restore from backup
tar -xzf backup-YYYYMMDD.tar.gz
```

### Database Maintenance

If using SQLite (default):
- Database file is in `web/configs/cache.db`
- Backup this file regularly
- Can be mounted as volume for persistence

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test with Docker
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- FastAPI for the excellent web framework
- Docker for containerization
- Bootstrap for responsive UI
- Chart.js for data visualization
