#!/bin/bash

# M3U2strm3 Docker Test Script
# This script tests the Docker container build and basic functionality

set -e

echo "🚀 M3U2strm3 Docker Test Script"
echo "=============================="

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed
print_status "Checking Docker installation..."
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi

# Check Docker daemon accessibility
print_status "Checking Docker daemon access..."
if ! docker info &> /dev/null; then
    print_warning "Cannot access Docker daemon. This usually means you need to:"
    print_warning "1. Add your user to the docker group: sudo usermod -aG docker $USER"
    print_warning "2. Log out and back in, or run: newgrp docker"
    print_warning "3. Or use sudo for Docker commands"
    
    # Try with sudo to verify Docker is actually working
    if sudo docker info &> /dev/null; then
        print_status "Docker is working with sudo. Attempting to add user to docker group..."
        if sudo usermod -aG docker $USER 2>/dev/null; then
            print_status "User added to docker group successfully ✓"
            print_warning "IMPORTANT: You need to log out and back in, or run 'newgrp docker' for this to take effect."
            print_warning "For now, the script will continue using sudo for Docker operations."
            USE_SUDO=true
        else
            print_warning "Could not add user to docker group. Will use sudo for Docker operations."
            USE_SUDO=true
        fi
    else
        print_error "Docker daemon is not running or not accessible even with sudo."
        print_error "Please ensure Docker is installed and running: sudo systemctl start docker"
        exit 1
    fi
else
    print_status "Docker daemon accessible ✓"
    USE_SUDO=false
fi

# Check for Docker Compose v2 (preferred) or v1 (legacy)
DOCKER_COMPOSE_CMD=""
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker-compose"
    print_status "Found legacy Docker Compose v1 (docker-compose)"
elif docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
    print_status "Found Docker Compose v2 (docker compose) ✓"
else
    print_error "Docker Compose is not installed. Please install Docker Compose first."
    print_warning "You can install it via: curl -L https://raw.githubusercontent.com/docker/compose-cli/main/scripts/install/install_linux.sh | bash"
    exit 1
fi

print_status "Docker and Docker Compose are installed ✓"

# Check if we're in the right directory
if [ ! -f "Dockerfile" ] || [ ! -f "docker-compose.yml" ]; then
    print_error "Dockerfile or docker-compose.yml not found. Please run this script from the M3U2strm3 root directory."
    exit 1
fi

print_status "Found Docker configuration files ✓"

# Function to run Docker commands with proper sudo handling
run_docker_cmd() {
    local cmd="$1"
    if [ "$USE_SUDO" = true ]; then
        sudo $cmd
    else
        $cmd
    fi
}

# Function to fix permissions with sudo prompt
fix_permissions() {
    print_warning "Attempting to fix volume permissions..."
    if sudo chown -R 1000:1000 web/uploads web/configs web/logs output 2>/dev/null; then
        print_status "Volume permissions fixed successfully ✓"
        return 0
    else
        print_error "Failed to fix permissions. Please run:"
        print_error "sudo chown -R 1000:1000 web/uploads web/configs web/logs output"
        return 1
    fi
}

# Build the Docker image
print_status "Building Docker image..."
if run_docker_cmd "$DOCKER_COMPOSE_CMD build"; then
    print_status "Docker image built successfully ✓"
else
    print_error "Failed to build Docker image"
    exit 1
fi

# Start the container
print_status "Starting Docker container..."
if run_docker_cmd "$DOCKER_COMPOSE_CMD up -d"; then
    print_status "Container started successfully ✓"
else
    print_error "Failed to start container"
    print_warning "This might be due to permission issues with volume directories."
    print_status "Attempting to fix permissions..."
    fix_permissions
    print_status "Retrying container start..."
    if run_docker_cmd "$DOCKER_COMPOSE_CMD up -d"; then
        print_status "Container started successfully after permission fix ✓"
    else
        print_error "Container still failed to start. Please check the logs:"
        run_docker_cmd "$DOCKER_COMPOSE_CMD logs"
        exit 1
    fi
fi

# Wait for container to be ready
print_status "Waiting for container to be ready..."
sleep 10

# Check container health
print_status "Checking container health..."
if run_docker_cmd "$DOCKER_COMPOSE_CMD ps" | grep -q "healthy"; then
    print_status "Container is healthy ✓"
elif run_docker_cmd "$DOCKER_COMPOSE_CMD ps" | grep -q "Up"; then
    print_warning "Container is running but health check not ready yet"
else
    print_error "Container is not running properly"
    run_docker_cmd "$DOCKER_COMPOSE_CMD logs"
    exit 1
fi

# Test web interface
print_status "Testing web interface..."
for i in {1..5}; do
    if curl -s http://localhost:8000 > /dev/null; then
        print_status "Web interface is accessible ✓"
        break
    else
        if [ $i -eq 5 ]; then
            print_error "Web interface is not accessible after 5 attempts"
            run_docker_cmd "$DOCKER_COMPOSE_CMD logs"
            exit 1
        fi
        print_warning "Web interface not ready, waiting 5 more seconds..."
        sleep 5
    fi
done

# Test API endpoint
print_status "Testing API endpoint..."
if curl -s http://localhost:8000/api/status > /dev/null; then
    print_status "API endpoint is working ✓"
else
    print_error "API endpoint is not working"
    run_docker_cmd "$DOCKER_COMPOSE_CMD logs"
    exit 1
fi

# Test FastAPI docs
print_status "Testing FastAPI documentation..."
if curl -s http://localhost:8000/docs > /dev/null; then
    print_status "FastAPI docs are accessible ✓"
else
    print_warning "FastAPI docs are not accessible (this might be normal)"
fi

# Show container information
print_status "Container information:"
run_docker_cmd "$DOCKER_COMPOSE_CMD ps"

# Show logs (last 10 lines)
print_status "Recent logs:"
run_docker_cmd "$DOCKER_COMPOSE_CMD logs --tail=10"

# Cleanup
print_status "Cleaning up test containers..."
run_docker_cmd "$DOCKER_COMPOSE_CMD down"

print_status "Docker test completed successfully! 🎉"

# Provide appropriate next steps based on sudo usage
if [ "$USE_SUDO" = true ]; then
    print_warning "IMPORTANT: You are using sudo for Docker operations."
    print_warning "For a better experience, please:"
    print_warning "1. Log out and back in, or run: newgrp docker"
    print_warning "2. Test without sudo: docker-compose ps"
    print_warning "3. If that works, you can remove sudo from future commands"
    print_status "You can now run 'sudo $DOCKER_COMPOSE_CMD up -d' to start the service permanently."
else
    print_status "You can now run '$DOCKER_COMPOSE_CMD up -d' to start the service permanently."
fi

echo ""
echo "📋 Next Steps:"
echo "1. Edit .env file with your TMDb API key"
if [ "$USE_SUDO" = true ]; then
    echo "2. Run 'sudo $DOCKER_COMPOSE_CMD up -d' to start the service"
else
    echo "2. Run '$DOCKER_COMPOSE_CMD up -d' to start the service"
fi
echo "3. Open http://localhost:8000 in your browser"
echo "4. Upload your M3U file and start processing!"

# Additional troubleshooting info
if [ "$USE_SUDO" = true ]; then
    echo ""
    echo "🔧 Docker Permission Troubleshooting:"
    echo "- If you continue having permission issues, ensure your user is in the docker group"
    echo "- Run: sudo usermod -aG docker $USER"
    echo "- Then: newgrp docker"
    echo "- Or continue using sudo for all Docker commands"
fi
