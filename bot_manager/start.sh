#!/bin/bash
# Update yt-dlp to latest version on every start
echo "Updating yt-dlp..."
pip install --upgrade yt-dlp --quiet

echo "Starting bot manager..."
python -m bot_manager.main
