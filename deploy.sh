#!/bin/bash

# Configuration - Update these with your Pi's details
PI_USER="teffin"
PI_IP="10.46.123.142" # Replace with your Pi's actual IP address
DEST_DIR="~/reception_bot"

echo "🚀 Deploying to $PI_USER@$PI_IP..."

# Use rsync to sync files, excluding unnecessary ones
rsync -avz --exclude '.venv' \
      --exclude '__pycache__' \
      --exclude '.git' \
      --exclude 'reception_robot/build' \
      --exclude 'reception_robot/install' \
      --exclude 'reception_robot/log' \
      ./ $PI_USER@$PI_IP:$DEST_DIR

if [ $? -eq 0 ]; then
    echo "✅ Deployment successful!"
    echo "Next steps on the Pi:"
    echo "  1. ssh $PI_USER@$PI_IP"
    echo "  2. cd $DEST_DIR"
    echo "  3. pip install -r requirements.txt"
    echo "  4. python3 main.py"
else
    echo "❌ Deployment failed. Please check your SSH connection and Pi IP."
fi
