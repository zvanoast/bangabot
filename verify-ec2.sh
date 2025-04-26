#!/bin/bash

# Verify EC2 setup for BangaBot deployment
echo "Verifying EC2 configuration for BangaBot deployment..."

# Check Docker installation
if command -v docker &> /dev/null; then
    echo "✅ Docker is installed: $(docker --version)"
else
    echo "❌ Docker is not installed"
fi

# Check Docker Compose installation
if command -v docker-compose &> /dev/null; then
    echo "✅ Docker Compose is installed: $(docker-compose --version)"
else
    echo "❌ Docker Compose is not installed"
fi

# Check BangaBot directory structure
if [ -d ~/bangabot ]; then
    echo "✅ BangaBot directory exists"
else
    echo "❌ BangaBot directory does not exist"
fi

# Check if Docker is running
if systemctl is-active --quiet docker; then
    echo "✅ Docker service is running"
else
    echo "❌ Docker service is not running"
fi

# Check Docker permissions for current user
if groups | grep -q docker; then
    echo "✅ Current user has Docker permissions"
else
    echo "❌ Current user does not have Docker permissions"
fi

# Check running containers
echo "Current Docker containers:"
docker ps -a

# Check volumes
echo "Docker volumes:"
docker volume ls

# Check disk space
echo "Disk space:"
df -h

echo "Verification complete!"