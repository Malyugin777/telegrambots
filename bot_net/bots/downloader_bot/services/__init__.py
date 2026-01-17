"""
Services для Downloader Bot
"""
from .downloader import VideoDownloader
from .queue import DownloadQueue
from .platforms import detect_platform, Platform

__all__ = ["VideoDownloader", "DownloadQueue", "detect_platform", "Platform"]
