#!/usr/bin/env python3
"""
Anime CLI - A command line tool for streaming and downloading anime

Features:
- Multi-provider support (Wixmp, SharePoint, YouTube, HiAnime)
- Working quality/provider change functionality
- Intelligent player selection (MPV/VLC) with auto-detection
- Advanced download system with progress tracking
- JSON-based data storage for history and downloads
- Resume watching functionality
- Configuration management
- Cross-platform compatibility
"""

import requests
import urllib.parse
import json
import re
import sys
import subprocess
import argparse
import os
import time
import glob
import configparser
import threading
import queue
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from colorama import init, Fore, Style, Back

# Third-party imports with fallbacks
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    print("tqdm not available - progress bars disabled")

try:
    import requests_cache
    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False

# Initialize colorama for cross-platform color support
init(autoreset=True)

# Application Constants
APP_NAME = "Animine"
APP_VERSION = "2.1.0"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0"
ALLANIME_REFR = "https://allmanga.to"
ALLANIME_BASE = "allanime.day"
ALLANIME_API = f"https://api.{ALLANIME_BASE}"

# Directory Configuration
CURRENT_DIR = Path.cwd()
APP_DIR = CURRENT_DIR / "anime_cli"
DOWNLOAD_DIR = CURRENT_DIR / "downloads"
CACHE_DIR = APP_DIR / "cache"
CONFIG_FILE = APP_DIR / "config.ini"
LOG_FILE = APP_DIR / "app.log"

# JSON Data Files for History, Downloads, Provider Stats
HISTORY_FILE = APP_DIR / "history.json"
DOWNLOADS_FILE = APP_DIR / "downloads.json"
PROVIDER_STATS_FILE = APP_DIR / "provider_stats.json"

# Create necessary directories
for directory in [APP_DIR, DOWNLOAD_DIR, CACHE_DIR]:
    directory.mkdir(exist_ok=True)

# Global configuration and state
config = configparser.ConfigParser()

class AnimeColor:
    """Enhanced color schemes for the CLI interface"""
    HEADER = Fore.CYAN + Style.BRIGHT
    SUCCESS = Fore.GREEN + Style.BRIGHT
    WARNING = Fore.YELLOW + Style.BRIGHT
    ERROR = Fore.RED + Style.BRIGHT
    INFO = Fore.BLUE + Style.BRIGHT
    HIGHLIGHT = Fore.MAGENTA + Style.BRIGHT
    SECONDARY = Fore.WHITE + Style.DIM
    PROGRESS = Fore.GREEN
    DEBUG = Fore.CYAN + Style.DIM
    RESET = Style.RESET_ALL
    
    # Background colors for special emphasis
    BG_ERROR = Back.RED + Fore.WHITE + Style.BRIGHT
    BG_SUCCESS = Back.GREEN + Fore.BLACK + Style.BRIGHT
    BG_WARNING = Back.YELLOW + Fore.BLACK + Style.BRIGHT

class Logger:
    """Simple logging system for debugging and error tracking"""
    
    def __init__(self, log_file: Path):
        self.log_file = log_file
        self.debug_mode = False
    
    def log(self, level: str, message: str):
        """Write log entry to file"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {level.upper()}: {message}\n"
        
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)
        except Exception:
            pass  # Fail silently to avoid log errors
    
    def debug(self, message: str):
        if self.debug_mode:
            print(f"{AnimeColor.DEBUG}DEBUG: {message}{AnimeColor.RESET}")
        self.log("DEBUG", message)
    
    def info(self, message: str):
        self.log("INFO", message)
    
    def warning(self, message: str):
        self.log("WARNING", message)
    
    def error(self, message: str):
        self.log("ERROR", message)

# Initialize logger
logger = Logger(LOG_FILE)

def clear_terminal():
    """Clear terminal screen with cross-platform compatibility"""
    try:
        if os.name == 'nt':
            os.system('cls')
        else:
            os.system('clear')
    except Exception:
        # Fallback method
        print('\n' * 50)

def print_banner():
    """Display the application banner with version info"""
    banner = f"""

 █████╗ ███╗   ██╗██╗███╗   ███╗██╗███╗   ██╗███████╗
██╔══██╗████╗  ██║██║████╗ ████║██║████╗  ██║██╔════╝
███████║██╔██╗ ██║██║██╔████╔██║██║██╔██╗ ██║█████╗  
██╔══██║██║╚██╗██║██║██║╚██╔╝██║██║██║╚██╗██║██╔══╝  
██║  ██║██║ ╚████║██║██║ ╚═╝ ██║██║██║ ╚████║███████╗
╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚══════╝

Version: {APP_VERSION}
Author: Mr Sachchidanand                                                                
"""
    print(banner)

def print_section(title: str, icon: str = ""):
    """Print a styled section header"""
    icon_str = f"{icon} " if icon else ""
    print(f"\n{AnimeColor.HEADER}{'─' * 20} {icon_str}{title} {'─' * 20}{AnimeColor.RESET}")

def loading_animation(text: str, duration: float = 2.0):
    """Display loading animation with spinner"""
    chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    end_time = time.time() + duration
    i = 0
    
    while time.time() < end_time:
        print(f"\r{AnimeColor.INFO}{chars[i % len(chars)]} {text}...{AnimeColor.RESET}", end="")
        time.sleep(0.1)
        i += 1
    
    print(f"\r{AnimeColor.SUCCESS}✓ {text} complete{AnimeColor.RESET}")

def sanitize_filename(filename: str) -> str:
    """Sanitize filename for cross-platform compatibility"""
    # Remove invalid characters
    invalid_chars = r'<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Remove control characters
    filename = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', filename)
    
    # Normalize whitespace
    filename = re.sub(r'\s+', ' ', filename)
    filename = re.sub(r'_+', '_', filename)
    
    # Trim and limit length
    filename = filename.strip('_').strip()
    if len(filename) > 200:
        filename = filename[:200].rsplit('_', 1)[0]
    
    return filename or "unnamed"

def find_executable(executable_name: str) -> Optional[str]:
    """Enhanced Windows executable finder with registry support"""
    logger.debug(f"Searching for executable: {executable_name}")
    
    # Strategy 1: Check system PATH first
    path_result = shutil.which(executable_name)
    if path_result:
        return path_result
    
    # Strategy 2: Windows-specific paths
    if os.name == 'nt':
        # VLC locations
        if 'vlc' in executable_name.lower():
            vlc_paths = [
                r"C:\Program Files\VideoLAN\VLC\vlc.exe",
                r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
                os.path.expanduser(r"~\scoop\apps\vlc\current\vlc.exe"),
                os.path.expanduser(r"~\AppData\Local\Programs\VLC\vlc.exe"),
                r"C:\ProgramData\chocolatey\lib\vlc\tools\vlc.exe",
            ]
            
            for path in vlc_paths:
                if Path(path).is_file():
                    return path
            
            # Registry check for VLC
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\VideoLAN\VLC") as key:
                    install_dir, _ = winreg.QueryValueEx(key, "InstallDir")
                    vlc_path = Path(install_dir) / "vlc.exe"
                    if vlc_path.is_file():
                        return str(vlc_path)
            except (ImportError, WindowsError, FileNotFoundError):
                pass
        
        # MPV locations
        if 'mpv' in executable_name.lower():
            mpv_paths = [
                r"C:\Program Files\mpv\mpv.exe",
                r"C:\Program Files (x86)\mpv\mpv.exe",
                os.path.expanduser(r"~\scoop\apps\mpv\current\mpv.exe"),
                r"C:\ProgramData\chocolatey\bin\mpv.exe",
            ]
            
            for path in mpv_paths:
                if Path(path).is_file():
                    return path
    
    return None

class ConfigManager:
    """Advanced configuration management with validation and defaults"""
    
    def __init__(self, config_file: Path):
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        self.load_config()
    
    def create_default_config(self):
        """Create comprehensive default configuration"""
        self.config['PLAYER'] = {
            'vlc_path': '',
            'mpv_path': '',
            'preferred_player': 'mpv',
            'auto_detect': 'true',
            'player_args_vlc': '--play-and-exit --no-video-deco --vout directx --avcodec-hw none',
            'player_args_mpv': '--keep-open=no --vo=gpu --hwdec=no'
        }
        
        self.config['PREFERENCES'] = {
            'default_mode': 'sub',
            'default_quality': 'best',
            'auto_continue': 'true',
            'clear_terminal': 'true',
            'show_progress': 'true',
            'max_search_results': '20',
            'episode_grid_cols': '8'
        }
        
        self.config['DOWNLOAD'] = {
            'download_directory': str(DOWNLOAD_DIR),
            'use_curl': 'true',
            'concurrent_downloads': '3',
            'retry_attempts': '3',
            'chunk_size': '8192',
            'timeout': '30'
        }
        
        self.config['CACHE'] = {
            'enable_cache': 'true',
            'cache_duration_hours': '24',
            'cache_directory': str(CACHE_DIR),
            'max_cache_size_mb': '100',
            'auto_cleanup': 'true'
        }
        
        self.config['NETWORK'] = {
            'timeout': '15',
            'retry_attempts': '3',
            'rate_limit_delay': '1.0',
            'user_agent': USER_AGENT,
            'referer': ALLANIME_REFR
        }
        
        self.config['LOGGING'] = {
            'enable_logging': 'true',
            'log_level': 'INFO',
            'debug_mode': 'false',
            'max_log_size_mb': '10'
        }
        
        self.save_config()
        logger.info("Created default configuration")
    
    def load_config(self):
        """Load configuration with validation"""
        if not self.config_file.exists():
            self.create_default_config()
            return
        
        try:
            self.config.read(self.config_file)
            self.validate_config()
            self.auto_detect_players()
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            print(f"{AnimeColor.ERROR}Config error, creating default...{AnimeColor.RESET}")
            self.create_default_config()
    
    def validate_config(self):
        """Validate configuration values and fix if necessary"""
        # Ensure all required sections exist
        required_sections = ['PLAYER', 'PREFERENCES', 'DOWNLOAD', 'CACHE', 'NETWORK', 'LOGGING']
        for section in required_sections:
            if not self.config.has_section(section):
                self.config.add_section(section)
        
        # Validate and fix numeric values
        numeric_settings = [
            ('PREFERENCES', 'max_search_results', 20),
            ('PREFERENCES', 'episode_grid_cols', 8),
            ('DOWNLOAD', 'concurrent_downloads', 3),
            ('DOWNLOAD', 'retry_attempts', 3),
            ('DOWNLOAD', 'timeout', 30),
            ('CACHE', 'cache_duration_hours', 24),
            ('CACHE', 'max_cache_size_mb', 100),
            ('NETWORK', 'timeout', 15),
            ('NETWORK', 'retry_attempts', 3),
            ('LOGGING', 'max_log_size_mb', 10)
        ]
        
        for section, key, default in numeric_settings:
            try:
                value = self.config.getint(section, key)
                if value <= 0:
                    raise ValueError("Must be positive")
            except (ValueError, configparser.NoOptionError):
                self.config.set(section, key, str(default))
        
        # Validate boolean settings
        boolean_settings = [
            ('PLAYER', 'auto_detect', True),
            ('PREFERENCES', 'auto_continue', True),
            ('PREFERENCES', 'clear_terminal', True),
            ('PREFERENCES', 'show_progress', True),
            ('DOWNLOAD', 'use_curl', True),
            ('CACHE', 'enable_cache', True),
            ('CACHE', 'auto_cleanup', True),
            ('LOGGING', 'enable_logging', True),
            ('LOGGING', 'debug_mode', False)
        ]
        
        for section, key, default in boolean_settings:
            try:
                self.config.getboolean(section, key)
            except (ValueError, configparser.NoOptionError):
                self.config.set(section, key, str(default).lower())
        
        # Validate choice settings
        if self.config.get('PREFERENCES', 'default_mode', fallback='sub') not in ['sub', 'dub']:
            self.config.set('PREFERENCES', 'default_mode', 'sub')
        
        if self.config.get('PLAYER', 'preferred_player', fallback='mpv') not in ['vlc', 'mpv']:
            self.config.set('PLAYER', 'preferred_player', 'mpv')
    
    def auto_detect_players(self):
        """Auto-detect media players and update configuration"""
        if not self.config.getboolean('PLAYER', 'auto_detect'):
            return
        
        vlc_path = find_executable("vlc.exe" if os.name == 'nt' else "vlc")
        mpv_path = find_executable("mpv.exe" if os.name == 'nt' else "mpv")
        
        if vlc_path:
            self.config.set('PLAYER', 'vlc_path', vlc_path)
            logger.info(f"Auto-detected VLC: {vlc_path}")
        
        if mpv_path:
            self.config.set('PLAYER', 'mpv_path', mpv_path)
            logger.info(f"Auto-detected MPV: {mpv_path}")
        
        self.save_config()
    
    def save_config(self):
        """Save configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                self.config.write(f)
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
    
    def get_player_path(self, force_player: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
        """Get preferred player path and name"""
        if force_player:
            if force_player.lower() == 'vlc':
                vlc_path = self.config.get('PLAYER', 'vlc_path')
                if vlc_path and Path(vlc_path).exists():
                    return vlc_path, 'VLC'
            elif force_player.lower() == 'mpv':
                mpv_path = self.config.get('PLAYER', 'mpv_path')
                if mpv_path and Path(mpv_path).exists():
                    return mpv_path, 'MPV'
        
        # Use preferred player (MPV first by default)
        preferred = self.config.get('PLAYER', 'preferred_player', fallback='mpv').lower()
        
        if preferred == 'mpv':
            mpv_path = self.config.get('PLAYER', 'mpv_path')
            if mpv_path and Path(mpv_path).exists():
                return mpv_path, 'MPV'
            # Fallback to VLC
            vlc_path = self.config.get('PLAYER', 'vlc_path')
            if vlc_path and Path(vlc_path).exists():
                return vlc_path, 'VLC'
        else:
            vlc_path = self.config.get('PLAYER', 'vlc_path')
            if vlc_path and Path(vlc_path).exists():
                return vlc_path, 'VLC'
            # Fallback to MPV
            mpv_path = self.config.get('PLAYER', 'mpv_path')
            if mpv_path and Path(mpv_path).exists():
                return mpv_path, 'MPV'
        
        return None, None

class JSONDataManager:
    """Advanced JSON-based data management for history and downloads"""
    
    def __init__(self):
        # Initialize JSON files
        self.init_json_files()
    
    def init_json_files(self):
        """Initialize JSON files with proper structure"""
        default_files = {
            HISTORY_FILE: {
                "history": [],
                "last_updated": datetime.now().isoformat()
            },
            DOWNLOADS_FILE: {
                "downloads": [],
                "last_updated": datetime.now().isoformat()
            },
            PROVIDER_STATS_FILE: {
                "providers": {},
                "last_updated": datetime.now().isoformat()
            }
        }
        
        for file_path, default_data in default_files.items():
            if not file_path.exists():
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(default_data, f, indent=2, ensure_ascii=False)
                    logger.info(f"Created {file_path.name}")
                except Exception as e:
                    logger.error(f"Failed to create {file_path.name}: {e}")
    
    def _load_json(self, file_path: Path) -> Dict[str, Any]:
        """Safely load JSON data"""
        try:
            if not file_path.exists():
                return {}
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load {file_path.name}: {e}")
            return {}
    
    def _save_json(self, file_path: Path, data: Dict[str, Any]) -> bool:
        """Safely save JSON data with detailed error reporting"""
        try:
            # Ensure directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Add timestamp
            data["last_updated"] = datetime.now().isoformat()
            
            # Write to temporary file first
            temp_file = file_path.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Move temp file to actual file (atomic operation)
            temp_file.replace(file_path)
            
            # Verify the file was written correctly
            if file_path.exists() and file_path.stat().st_size > 0:
                logger.info(f"Successfully saved {file_path.name} ({file_path.stat().st_size} bytes)")
                return True
            else:
                logger.error(f"File {file_path.name} was not saved correctly")
                return False
                
        except Exception as e:
            logger.error(f"Failed to save {file_path.name}: {e}")
            print(f"Save error: {e}")
            return False

    def add_history(self, anime_id: str, anime_name: str, episode: str, mode: str, 
                   total_episodes: int, quality: str = None, provider: str = None):
        """Add or update viewing history with enhanced data"""
        try:
            data = self._load_json(HISTORY_FILE)
            if "history" not in data:
                data["history"] = []
            
            # Debug logging
            logger.info(f"Adding history: {anime_name} EP{episode} - {quality} from {provider}")
            print(f"DEBUG: Adding to history: {anime_name} EP{episode}")
            
            # Validate input
            if not anime_id or not anime_name or not episode:
                logger.warning("Invalid history data provided")
                print("Invalid history data - missing required fields")
                return False
            
            # Convert episode to string for consistency
            episode = str(episode)
            
            # Find existing entry with same anime_id and mode
            existing_entry = None
            for i, entry in enumerate(data["history"]):
                if entry.get("anime_id") == str(anime_id) and entry.get("mode") == str(mode):
                    existing_entry = i
                    break
            
            # Create history entry
            history_entry = {
                "anime_id": str(anime_id),
                "anime_name": str(anime_name),
                "episode": str(episode),
                "mode": str(mode),
                "quality": str(quality) if quality else "Unknown",
                "provider": str(provider) if provider else "Unknown",
                "duration_watched": 0,
                "total_duration": 0,
                "completion_percentage": 0.0,
                "last_watched": datetime.now().isoformat(),
                "total_episodes": int(total_episodes) if total_episodes else 0,
                "rating": 0,
                "notes": ""
            }
            
            if existing_entry is not None:
                # Update existing entry (keep some fields from old entry)
                old_entry = data["history"][existing_entry]
                history_entry["duration_watched"] = old_entry.get("duration_watched", 0)
                history_entry["total_duration"] = old_entry.get("total_duration", 0)
                history_entry["completion_percentage"] = old_entry.get("completion_percentage", 0.0)
                history_entry["rating"] = old_entry.get("rating", 0)
                history_entry["notes"] = old_entry.get("notes", "")
                
                # Replace the existing entry
                data["history"][existing_entry] = history_entry
                logger.info(f"Updated existing history entry for {anime_name}")
            else:
                # Add new entry at the beginning
                data["history"].insert(0, history_entry)
                logger.info(f"Added new history entry for {anime_name}")
            
            # Sort by last_watched (most recent first)
            data["history"].sort(key=lambda x: x.get("last_watched", ""), reverse=True)
            
            # Keep only last 100 entries
            data["history"] = data["history"][:100]
            
            # Save the data
            success = self._save_json(HISTORY_FILE, data)
            if success:
                logger.info(f"History successfully saved for {anime_name} episode {episode}")
                print(f"✓ History updated: {anime_name} EP{episode}")
                return True
            else:
                logger.error("Failed to save history data to JSON file")
                print("✗ Failed to save history")
                return False
            
        except Exception as e:
            logger.error(f"Failed to add history: {e}")
            print(f"Error adding history: {e}")
            return False

    def get_history(self, limit: int = 20) -> List[Tuple]:
        """Get viewing history with detailed information"""
        try:
            data = self._load_json(HISTORY_FILE)
            history_list = []
            
            for entry in data.get("history", [])[:limit]:
                history_tuple = (
                    entry.get("anime_name", ""),
                    entry.get("episode", ""),
                    entry.get("mode", ""),
                    entry.get("quality", ""),
                    entry.get("provider", ""),
                    entry.get("last_watched", ""),
                    entry.get("total_episodes", 0),
                    entry.get("rating", 0)
                )
                history_list.append(history_tuple)
            
            return history_list
            
        except Exception as e:
            logger.error(f"Failed to get history: {e}")
            return []

    def get_continue_options(self, limit: int = 10) -> List[Tuple]:
        """Get anime that can be continued"""
        try:
            data = self._load_json(HISTORY_FILE)
            continue_list = []
            
            for entry in data.get("history", []):
                try:
                    current_ep = int(entry.get("episode", "0"))
                    total_eps = int(entry.get("total_episodes", "0"))
                    
                    # Only include if current episode is less than total episodes
                    if current_ep < total_eps and total_eps > 0:
                        continue_tuple = (
                            entry.get("anime_id", ""),
                            entry.get("anime_name", ""),
                            entry.get("episode", ""),
                            entry.get("mode", ""),
                            entry.get("total_episodes", 0),
                            entry.get("quality", ""),
                            entry.get("provider", "")
                        )
                        continue_list.append(continue_tuple)
                        
                        if len(continue_list) >= limit:
                            break
                            
                except (ValueError, TypeError):
                    continue
            
            return continue_list
            
        except Exception as e:
            logger.error(f"Failed to get continue options: {e}")
            return []
    
    def add_download(self, anime_name: str, episode: str, quality: str, provider: str,
                    file_path: str, file_size: int = 0, download_speed: float = 0.0):
        """Add download record with performance metrics"""
        try:
            data = self._load_json(DOWNLOADS_FILE)
            if "downloads" not in data:
                data["downloads"] = []
            
            # Validate input
            if not anime_name or not episode:
                logger.warning("Invalid download data provided")
                return
            
            # Create download entry
            download_entry = {
                "anime_name": str(anime_name),
                "episode": str(episode),
                "quality": quality or "Unknown",
                "provider": provider or "Unknown",
                "file_path": str(file_path),
                "file_size": int(file_size) if file_size else 0,
                "download_speed": float(download_speed) if download_speed else 0.0,
                "download_duration": 0.0,
                "status": "completed",
                "download_date": datetime.now().isoformat(),
                "checksum": ""
            }
            
            # Add to beginning of list
            data["downloads"].insert(0, download_entry)
            
            # Sort by download_date (most recent first)
            data["downloads"].sort(key=lambda x: x.get("download_date", ""), reverse=True)
            
            # Keep only last 200 downloads
            data["downloads"] = data["downloads"][:200]
            
            # Save the data
            success = self._save_json(DOWNLOADS_FILE, data)
            if success:
                logger.info(f"Download recorded: {anime_name} episode {episode}")
            
        except Exception as e:
            logger.error(f"Failed to add download record: {e}")
    
    def get_downloads(self, limit: int = 20) -> List[Tuple]:
        """Get download history"""
        try:
            data = self._load_json(DOWNLOADS_FILE)
            downloads_list = []
            
            for entry in data.get("downloads", [])[:limit]:
                download_tuple = (
                    entry.get("anime_name", ""),
                    entry.get("episode", ""),
                    entry.get("quality", ""),
                    entry.get("provider", ""),
                    entry.get("file_path", ""),
                    entry.get("file_size", 0),
                    entry.get("download_date", ""),
                    entry.get("status", "completed")
                )
                downloads_list.append(download_tuple)
            
            return downloads_list
            
        except Exception as e:
            logger.error(f"Failed to get downloads: {e}")
            return []
    
    def update_provider_stats(self, provider: str, success: bool, response_time: float = 0.0):
        """Update provider performance statistics"""
        try:
            data = self._load_json(PROVIDER_STATS_FILE)
            if "providers" not in data:
                data["providers"] = {}
            
            if provider not in data["providers"]:
                # Initialize new provider
                data["providers"][provider] = {
                    "success_count": 0,
                    "failure_count": 0,
                    "avg_response_time": 0.0,
                    "last_used": datetime.now().isoformat()
                }
            
            provider_data = data["providers"][provider]
            
            # Update counters
            if success:
                provider_data["success_count"] += 1
            else:
                provider_data["failure_count"] += 1
            
            # Update average response time
            total_requests = provider_data["success_count"] + provider_data["failure_count"]
            if total_requests > 1:
                current_avg = provider_data["avg_response_time"]
                provider_data["avg_response_time"] = ((current_avg * (total_requests - 1)) + response_time) / total_requests
            else:
                provider_data["avg_response_time"] = response_time
            
            provider_data["last_used"] = datetime.now().isoformat()
            
            # Save the data
            success_save = self._save_json(PROVIDER_STATS_FILE, data)
            if success_save:
                logger.debug(f"Provider stats updated for {provider}")
            
        except Exception as e:
            logger.error(f"Failed to update provider stats: {e}")
    
    def get_provider_rankings(self) -> List[Tuple]:
        """Get provider performance rankings"""
        try:
            data = self._load_json(PROVIDER_STATS_FILE)
            rankings = []
            
            for provider_name, stats in data.get("providers", {}).items():
                success_count = stats.get("success_count", 0)
                failure_count = stats.get("failure_count", 0)
                avg_response_time = stats.get("avg_response_time", 0.0)
                
                total_requests = success_count + failure_count
                if total_requests > 0:
                    success_rate = round((success_count * 100.0) / total_requests, 2)
                    
                    ranking_tuple = (
                        provider_name,
                        success_count,
                        failure_count,
                        avg_response_time,
                        success_rate
                    )
                    rankings.append(ranking_tuple)
            
            # Sort by success rate (descending), then by response time (ascending)
            rankings.sort(key=lambda x: (-x[4], x[3]))
            
            return rankings
            
        except Exception as e:
            logger.error(f"Failed to get provider rankings: {e}")
            return []
    
    def clear_history(self):
        """Clear all viewing history"""
        try:
            data = {"history": [], "last_updated": datetime.now().isoformat()}
            success = self._save_json(HISTORY_FILE, data)
            if success:
                logger.info("History cleared successfully")
            return success
        except Exception as e:
            logger.error(f"Failed to clear history: {e}")
            return False
    
    def clear_downloads(self):
        """Clear all download history"""
        try:
            data = {"downloads": [], "last_updated": datetime.now().isoformat()}
            success = self._save_json(DOWNLOADS_FILE, data)
            if success:
                logger.info("Download history cleared successfully")
            return success
        except Exception as e:
            logger.error(f"Failed to clear download history: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        try:
            history_data = self._load_json(HISTORY_FILE)
            downloads_data = self._load_json(DOWNLOADS_FILE)
            provider_data = self._load_json(PROVIDER_STATS_FILE)
            
            stats = {
                "total_anime_watched": len(history_data.get("history", [])),
                "total_downloads": len(downloads_data.get("downloads", [])),
                "total_providers_used": len(provider_data.get("providers", {})),
                "continue_available": len(self.get_continue_options(100)),
                "last_activity": None
            }
            
            # Get last activity date
            all_dates = []
            for entry in history_data.get("history", []):
                if entry.get("last_watched"):
                    all_dates.append(entry["last_watched"])
            
            for entry in downloads_data.get("downloads", []):
                if entry.get("download_date"):
                    all_dates.append(entry["download_date"])
            
            if all_dates:
                stats["last_activity"] = max(all_dates)
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}

class HexDecoder:
    """Advanced hex decoder for provider URLs with error handling"""
    
    def __init__(self):
        self.translation_table = {
            "79": "A", "7a": "B", "7b": "C", "7c": "D", "7d": "E", "7e": "F",
            "7f": "G", "70": "H", "71": "I", "72": "J", "73": "K", "74": "L",
            "75": "M", "76": "N", "77": "O", "68": "P", "69": "Q", "6a": "R",
            "6b": "S", "6c": "T", "6d": "U", "6e": "V", "6f": "W", "60": "X",
            "61": "Y", "62": "Z", "59": "a", "5a": "b", "5b": "c", "5c": "d",
            "5d": "e", "5e": "f", "5f": "g", "50": "h", "51": "i", "52": "j",
            "53": "k", "54": "l", "55": "m", "56": "n", "57": "o", "48": "p",
            "49": "q", "4a": "r", "4b": "s", "4c": "t", "4d": "u", "4e": "v",
            "4f": "w", "40": "x", "41": "y", "42": "z", "08": "0", "09": "1",
            "0a": "2", "0b": "3", "0c": "4", "0d": "5", "0e": "6", "0f": "7",
            "00": "8", "01": "9", "15": "-", "16": ".", "67": "_", "46": "~",
            "02": ":", "17": "/", "07": "?", "1b": "#", "63": "[", "65": "]",
            "78": "@", "19": "!", "1c": "$", "1e": "&", "10": "(", "11": ")",
            "12": "*", "13": "+", "14": ",", "03": ";", "05": "=", "1d": "%"
        }
    
    def decode(self, hex_blob: str) -> str:
        """Decode hex-encoded provider URL with validation"""
        try:
            if not hex_blob:
                raise ValueError("Empty hex blob")
            
            # Remove prefix
            if hex_blob.startswith("--"):
                hex_blob = hex_blob[2:]
            
            # Validate hex string
            if len(hex_blob) % 2 != 0:
                logger.warning(f"Invalid hex length: {len(hex_blob)}")
                return ""
            
            # Split into pairs and decode
            hex_pairs = re.findall(r"..", hex_blob)
            decoded_chars = []
            
            for pair in hex_pairs:
                if pair in self.translation_table:
                    decoded_chars.append(self.translation_table[pair])
                else:
                    logger.warning(f"Unknown hex pair: {pair}")
                    # Skip unknown pairs instead of failing
                    continue
            
            result = ''.join(decoded_chars)
            
            # Apply transformations
            result = result.replace("/clock", "/clock.json")
            
            logger.debug(f"Successfully decoded hex blob to: {result[:100]}...")
            return result
            
        except Exception as e:
            logger.error(f"Hex decoding failed: {e}")
            return ""

class ProviderManager:
    """Advanced provider management with intelligent fallback and performance tracking"""
    
    def __init__(self, config_manager: ConfigManager, data_manager: JSONDataManager):
        self.config = config_manager
        self.db = data_manager
        self.decoder = HexDecoder()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': config_manager.config.get('NETWORK', 'user_agent', fallback=USER_AGENT)
        })
        
        # Provider definitions with priority and capabilities
        self.providers = {
            'wixmp': {
                'name': 'Wixmp',
                'regex': r'Default:(--[a-f0-9]+)',
                'priority': 1,
                'supports_mp4': True,
                'supports_m3u8': True,
                'quality_levels': ['1080p', '720p', '480p', '360p']
            },
            'sharepoint': {
                'name': 'SharePoint',
                'regex': r'S-mp4:(--[a-f0-9]+)',
                'priority': 2,
                'supports_mp4': True,
                'supports_m3u8': False,
                'quality_levels': ['MP4']
            },
            'youtube': {
                'name': 'YouTube',
                'regex': r'Yt-mp4:(--[a-f0-9]+)',
                'priority': 3,
                'supports_mp4': True,
                'supports_m3u8': False,
                'quality_levels': ['YouTube']
            },
            'hianime': {
                'name': 'HiAnime',
                'regex': r'Luf-Mp4:(--[a-f0-9]+)',
                'priority': 4,
                'supports_mp4': False,
                'supports_m3u8': True,
                'quality_levels': ['HLS']
            }
        }
    
    def extract_wixmp_links(self, repackager_url: str) -> List[Tuple[str, str, str]]:
        """Extract Wixmp repackager links with enhanced error handling"""
        try:
            pattern = r'https://repackager\.wixmp\.com/(video\.wixstatic\.com/video/[^/]+)/,([^,/]+(?:,[^,/]+)*),/mp4/file\.mp4\.urlset/master\.m3u8'
            match = re.search(pattern, repackager_url)
            
            if not match:
                logger.warning(f"No Wixmp pattern match in URL: {repackager_url[:100]}...")
                return []
            
            base_url = match.group(1)
            qualities_str = match.group(2)
            qualities = [q.strip() for q in qualities_str.split(',') if q.strip()]
            
            links = []
            for quality in qualities:
                mp4_url = f"https://{base_url}/{quality}/mp4/file.mp4"
                links.append(('mp4', quality, mp4_url))
                logger.debug(f"Extracted Wixmp link: {quality} - {mp4_url[:50]}...")
            
            return links
            
        except Exception as e:
            logger.error(f"Wixmp extraction failed: {e}")
            return []
    
    def extract_sharepoint_links(self, response_text: str) -> List[Tuple[str, str, str]]:
        """Extract SharePoint MP4 links from JSON response"""
        try:
            links = []
            
            # Try JSON parsing first
            if response_text.strip().startswith('{'):
                json_data = json.loads(response_text)
                
                if "links" in json_data and isinstance(json_data["links"], list):
                    for link_obj in json_data["links"]:
                        if isinstance(link_obj, dict) and "link" in link_obj:
                            if link_obj.get("mp4", False):
                                quality = link_obj.get("resolutionStr", "SharePoint")
                                url = link_obj["link"]
                                links.append(('mp4', quality, url))
                                logger.debug(f"Extracted SharePoint link: {quality}")
            
            # Fallback to regex if JSON parsing fails or no links found
            if not links:
                patterns = [
                    r'"link":"([^"]*sharepoint[^"]*download[^"]*)"',
                    r'"src":"([^"]*sharepoint[^"]*download[^"]*)"'
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, response_text)
                    for match in matches:
                        if 'sharepoint.com' in match and 'download' in match:
                            links.append(('mp4', 'SharePoint', match))
                            logger.debug(f"Extracted SharePoint regex link")
            
            return links
            
        except Exception as e:
            logger.error(f"SharePoint extraction failed: {e}")
            return []
    
    def extract_youtube_links(self, response_text: str) -> List[Tuple[str, str, str]]:
        """Extract YouTube-style links with domain fix"""
        try:
            links = []
            patterns = [
                r'(https://tools\.fast4speed\.rsvp[^"\s]+)',
                r'"url":"([^"]*tools\.fast4speed[^"]*)"'
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, response_text)
                for match in matches:
                    # Fix double domain issue
                    if match.startswith("https://allanime.dayhttps://"):
                        match = match.replace("https://allanime.day", "")
                    
                    links.append(('mp4', 'YouTube', match))
                    logger.debug(f"Extracted YouTube link")
            
            return links
            
        except Exception as e:
            logger.error(f"YouTube extraction failed: {e}")
            return []
    
    def extract_hianime_links(self, response_text: str) -> List[Tuple[str, str, str]]:
        """Extract HiAnime M3U8 links"""
        try:
            links = []
            patterns = [
                r'"url":"([^"]*\.m3u8[^"]*)"',
                r'(https://[^"\s]+\.m3u8[^"\s]*)'
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, response_text)
                for match in matches:
                    if 'master.m3u8' in match:
                        links.append(('m3u8', 'HLS Master', match))
                    else:
                        links.append(('m3u8', 'HLS Stream', match))
                    logger.debug(f"Extracted HiAnime M3U8 link")
            
            return links
            
        except Exception as e:
            logger.error(f"HiAnime extraction failed: {e}")
            return []
    
    def fetch_provider_data(self, provider_key: str, decoded_url: str) -> Dict[str, Any]:
        """Fetch data from provider with performance tracking"""
        provider = self.providers[provider_key]
        start_time = time.time()
        
        try:
            full_url = f"https://{ALLANIME_BASE}{decoded_url}"
            timeout = self.config.config.getint('NETWORK', 'timeout', fallback=15)
            
            response = self.session.get(full_url, timeout=timeout)
            response.raise_for_status()
            
            response_time = time.time() - start_time
            self.db.update_provider_stats(provider['name'], True, response_time)
            
            return {
                'provider': provider['name'],
                'status': 'success',
                'response_text': response.text,
                'response_time': response_time,
                'url': full_url
            }
            
        except Exception as e:
            response_time = time.time() - start_time
            self.db.update_provider_stats(provider['name'], False, response_time)
            
            logger.error(f"Provider {provider['name']} failed: {e}")
            return {
                'provider': provider['name'],
                'status': 'error',
                'error': str(e),
                'response_time': response_time
            }
    
    def get_all_links(self, show_id: str, episode: str, mode: str = 'sub') -> List[Tuple[str, str, str, str]]:
        """Get all available links from all providers with intelligent prioritization"""
        try:
            # Fetch episode source data
            episode_gql = '''
            query($showId: String!, $translationType: VaildTranslationTypeEnumType!, $episodeString: String!) {
                episode(showId: $showId, translationType: $translationType, episodeString: $episodeString) {
                    episodeString sourceUrls
                }
            }
            '''
            
            variables = {"showId": show_id, "translationType": mode, "episodeString": str(episode)}
            params = {"variables": json.dumps(variables), "query": episode_gql}
            headers = {"User-Agent": USER_AGENT, "Referer": ALLANIME_REFR}
            
            response = self.session.get(f"{ALLANIME_API}/api", params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            source_urls = data.get("data", {}).get("episode", {}).get("sourceUrls", [])
            if not source_urls:
                logger.warning(f"No source URLs found for episode {episode}")
                return []
            
            # Build source response for provider parsing
            source_lines = []
            for source in source_urls:
                source_name = source.get("sourceName", "")
                source_url = source.get("sourceUrl", "").replace("\\u002F", "/").replace("\\", "")
                if source_name and source_url:
                    source_lines.append(f"{source_name}:{source_url}")
            
            source_response = "\n".join(source_lines)
            logger.info(f"Found {len(source_urls)} source providers for episode {episode}")
            
            # Process all providers with parallel execution
            all_links = []
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {}
                
                for provider_key, provider_info in self.providers.items():
                    match = re.search(provider_info['regex'], source_response, re.IGNORECASE)
                    if match:
                        encoded_url = match.group(1)
                        decoded_url = self.decoder.decode(encoded_url)
                        
                        if decoded_url:
                            future = executor.submit(self.fetch_provider_data, provider_key, decoded_url)
                            futures[future] = (provider_key, provider_info)
                
                # Collect results
                for future in as_completed(futures):
                    provider_key, provider_info = futures[future]
                    result = future.result()
                    
                    if result['status'] == 'success':
                        # Extract links based on provider type
                        response_text = result['response_text']
                        
                        if provider_key == 'wixmp':
                            repackager_urls = re.findall(r'https://repackager\.wixmp\.com/[^"\'>\s]+', response_text)
                            for url in repackager_urls:
                                links = self.extract_wixmp_links(url)
                                for fmt, quality, link_url in links:
                                    all_links.append((fmt, quality, link_url, provider_info['name']))
                        
                        elif provider_key == 'sharepoint':
                            links = self.extract_sharepoint_links(response_text)
                            for fmt, quality, link_url in links:
                                all_links.append((fmt, quality, link_url, provider_info['name']))
                        
                        elif provider_key == 'youtube':
                            links = self.extract_youtube_links(response_text)
                            for fmt, quality, link_url in links:
                                all_links.append((fmt, quality, link_url, provider_info['name']))
                        
                        elif provider_key == 'hianime':
                            links = self.extract_hianime_links(response_text)
                            for fmt, quality, link_url in links:
                                all_links.append((fmt, quality, link_url, provider_info['name']))
            
            # Sort by provider priority and quality
            def sort_key(link):
                fmt, quality, url, provider = link
                provider_priority = next((p['priority'] for p in self.providers.values() if p['name'] == provider), 999)
                quality_priority = {'1080p': 1, '720p': 2, '480p': 3, '360p': 4}.get(quality, 5)
                format_priority = {'mp4': 1, 'm3u8': 2}.get(fmt, 3)
                return (provider_priority, format_priority, quality_priority)
            
            all_links.sort(key=sort_key)
            
            logger.info(f"Successfully extracted {len(all_links)} total links")
            return all_links
            
        except Exception as e:
            logger.error(f"Failed to get links: {e}")
            return []

class AnimeAPI:
    """Advanced anime API interface with caching and error handling"""
    
    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': config_manager.config.get('NETWORK', 'user_agent', fallback=USER_AGENT),
            'Referer': config_manager.config.get('NETWORK', 'referer', fallback=ALLANIME_REFR)
        })
        
        # Initialize cache if available
        if CACHE_AVAILABLE and config_manager.config.getboolean('CACHE', 'enable_cache'):
            cache_duration = timedelta(hours=config_manager.config.getint('CACHE', 'cache_duration_hours', fallback=24))
            requests_cache.install_cache(
                str(CACHE_DIR / 'api_cache'),
                expire_after=cache_duration
            )
    
    def search_anime(self, query: str, mode: str = 'sub', limit: int = 20) -> List[Dict[str, Any]]:
        """Search for anime with enhanced error handling and validation"""
        try:
            search_gql = '''
            query($search: SearchInput, $limit: Int, $page: Int, $translationType: VaildTranslationTypeEnumType) {
                shows(search: $search, limit: $limit, page: $page, translationType: $translationType) {
                    edges { 
                        _id 
                        name 
                        availableEpisodes
                        englishName
                        nativeName
                        thumbnail
                        description
                        __typename 
                    }
                }
            }
            '''
            
            variables = {
                "search": {"allowAdult": False, "allowUnknown": False, "query": query.strip()},
                "limit": limit,
                "page": 1,
                "translationType": mode
            }
            
            params = {"variables": json.dumps(variables), "query": search_gql}
            timeout = self.config.config.getint('NETWORK', 'timeout', fallback=15)
            
            response = self.session.get(f"{ALLANIME_API}/api", params=params, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            
            shows = data.get("data", {}).get("shows", {}).get("edges", [])
            anime_list = []
            
            for show in shows:
                episodes = show.get("availableEpisodes", {}).get(mode, 0)
                if episodes and int(episodes) > 0:
                    anime_list.append({
                        "id": show.get("_id"),
                        "name": show.get("name", "").replace('\\"', ''),
                        "english_name": show.get("englishName", ""),
                        "native_name": show.get("nativeName", ""),
                        "episodes": int(episodes),
                        "thumbnail": show.get("thumbnail", ""),
                        "description": show.get("description", "")[:200] + "..." if show.get("description", "") else ""
                    })
            
            logger.info(f"Search for '{query}' returned {len(anime_list)} results")
            return anime_list
            
        except Exception as e:
            logger.error(f"Search failed for '{query}': {e}")
            return []
    
    def get_episodes_list(self, show_id: str, mode: str = 'sub') -> List[str]:
        """Get list of available episodes with validation"""
        try:
            episodes_gql = '''
            query($showId: String!) {
                show(_id: $showId) { 
                    _id 
                    availableEpisodesDetail
                    name
                }
            }
            '''
            
            variables = {"showId": show_id}
            params = {"variables": json.dumps(variables), "query": episodes_gql}
            timeout = self.config.config.getint('NETWORK', 'timeout', fallback=15)
            
            response = self.session.get(f"{ALLANIME_API}/api", params=params, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            
            show_data = data.get("data", {}).get("show", {})
            if not show_data:
                logger.warning(f"No show data found for ID: {show_id}")
                return []
            
            episodes = show_data.get("availableEpisodesDetail", {}).get(mode, [])
            if not episodes:
                logger.warning(f"No episodes found for show {show_id} in {mode} mode")
                return []
            
            # Sort episodes numerically
            try:
                sorted_episodes = sorted([str(ep) for ep in episodes], key=lambda x: float(x))
                logger.info(f"Found {len(sorted_episodes)} episodes for show {show_id}")
                return sorted_episodes
            except (ValueError, TypeError):
                # Fallback to string sorting if numeric sorting fails
                sorted_episodes = sorted([str(ep) for ep in episodes])
                logger.warning(f"Used string sorting for episodes due to non-numeric values")
                return sorted_episodes
            
        except Exception as e:
            logger.error(f"Failed to get episodes for show {show_id}: {e}")
            return []

class DownloadManager:
    """Advanced download manager with curl, progress tracking, and retry logic"""
    
    def __init__(self, config_manager: ConfigManager, data_manager: JSONDataManager):
        self.config = config_manager
        self.db = data_manager
        self.active_downloads = {}
        
        # Check curl availability
        self.curl_available = self._check_curl()
    
    def _check_curl(self) -> bool:
        """Check if curl is available"""
        try:
            result = subprocess.run(["curl", "--version"], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                logger.info("Curl is available for downloads")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        logger.warning("Curl not found - downloads may be slower")
        return False
    
    def download_with_curl(self, url: str, filepath: Path, anime_name: str, 
                          episode: str, quality: str, provider: str) -> bool:
        """Download using curl with progress tracking"""
        try:
            # Prepare curl command
            curl_cmd = [
                "curl",
                "-L",  # Follow redirects
                "-C", "-",  # Resume partial downloads
                "--user-agent", USER_AGENT,
                "--referer", ALLANIME_REFR,
                "--connect-timeout", "30",
                "--max-time", "3600",  # 1 hour max
                "--retry", str(self.config.config.getint('DOWNLOAD', 'retry_attempts', fallback=3)),
                "--retry-delay", "5",
                "--progress-bar",
                "-o", str(filepath),
                url
            ]
            
            print(f"{AnimeColor.INFO}Starting download with curl...{AnimeColor.RESET}")
            print(f"{AnimeColor.SECONDARY}URL: {url[:80]}...{AnimeColor.RESET}")
            print(f"{AnimeColor.SECONDARY}File: {filepath}{AnimeColor.RESET}")
            
            start_time = time.time()
            
            # Execute curl
            process = subprocess.Popen(
                curl_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )
            
            # Monitor progress
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output and ('#' in output or '%' in output):
                    print(f"\r{AnimeColor.PROGRESS}{output.strip()}{AnimeColor.RESET}", end="")
            
            return_code = process.poll()
            download_time = time.time() - start_time
            
            if return_code == 0 and filepath.exists():
                file_size = filepath.stat().st_size
                download_speed = file_size / download_time if download_time > 0 else 0
                
                print(f"\n{AnimeColor.SUCCESS}Download completed successfully!{AnimeColor.RESET}")
                print(f"{AnimeColor.INFO}File: {filepath}{AnimeColor.RESET}")
                print(f"{AnimeColor.INFO}Size: {file_size / (1024*1024):.1f} MB{AnimeColor.RESET}")
                print(f"{AnimeColor.INFO}Speed: {download_speed / (1024*1024):.1f} MB/s{AnimeColor.RESET}")
                print(f"{AnimeColor.INFO}Time: {download_time:.1f} seconds{AnimeColor.RESET}")
                
                # Record download in database
                self.db.add_download(anime_name, episode, quality, provider, 
                                   str(filepath), file_size, download_speed)
                
                return True
            else:
                print(f"\n{AnimeColor.ERROR}Download failed with exit code: {return_code}{AnimeColor.RESET}")
                return False
                
        except Exception as e:
            logger.error(f"Curl download failed: {e}")
            print(f"{AnimeColor.ERROR}Download error: {e}{AnimeColor.RESET}")
            return False
    
    def download_with_requests(self, url: str, filepath: Path, anime_name: str,
                             episode: str, quality: str, provider: str) -> bool:
        """Fallback download using requests with progress bar"""
        try:
            headers = {
                'User-Agent': USER_AGENT,
                'Referer': ALLANIME_REFR
            }
            
            timeout = self.config.config.getint('DOWNLOAD', 'timeout', fallback=30)
            
            print(f"{AnimeColor.INFO}Starting download with requests...{AnimeColor.RESET}")
            
            response = requests.get(url, headers=headers, stream=True, timeout=timeout)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            
            if TQDM_AVAILABLE and total_size > 0:
                progress_bar = tqdm(
                    total=total_size,
                    unit='B',
                    unit_scale=True,
                    unit_divisor=1024,
                    desc=f"{AnimeColor.PROGRESS}Downloading{AnimeColor.RESET}"
                )
            else:
                progress_bar = None
            
            start_time = time.time()
            downloaded = 0
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_bar:
                            progress_bar.update(len(chunk))
            
            if progress_bar:
                progress_bar.close()
            
            download_time = time.time() - start_time
            download_speed = downloaded / download_time if download_time > 0 else 0
            
            print(f"\n{AnimeColor.SUCCESS}Download completed!{AnimeColor.RESET}")
            print(f"{AnimeColor.INFO}Size: {downloaded / (1024*1024):.1f} MB{AnimeColor.RESET}")
            print(f"{AnimeColor.INFO}Speed: {download_speed / (1024*1024):.1f} MB/s{AnimeColor.RESET}")
            
            # Record download in database
            self.db.add_download(anime_name, episode, quality, provider,
                               str(filepath), downloaded, download_speed)
            
            return True
            
        except Exception as e:
            logger.error(f"Requests download failed: {e}")
            print(f"{AnimeColor.ERROR}Download error: {e}{AnimeColor.RESET}")
            return False
    
    def download_episode(self, anime_name: str, episode: str, quality: str,
                        url: str, provider: str) -> bool:
        """Download episode with automatic method selection"""
        # Create safe filename
        safe_name = sanitize_filename(anime_name)
        filename = f"{safe_name}_EP{episode}_{quality}.mp4"
        filepath = DOWNLOAD_DIR / filename
        
        # Check if file already exists
        if filepath.exists():
            overwrite = input(f"{AnimeColor.WARNING}File exists. Overwrite? (y/N): {AnimeColor.RESET}")
            if overwrite.lower() != 'y':
                return False
        
        print(f"\n{AnimeColor.HEADER}Download Details:{AnimeColor.RESET}")
        print(f"{AnimeColor.INFO}Anime: {anime_name}{AnimeColor.RESET}")
        print(f"{AnimeColor.INFO}Episode: {episode}{AnimeColor.RESET}")
        print(f"{AnimeColor.INFO}Quality: {quality}{AnimeColor.RESET}")
        print(f"{AnimeColor.INFO}Provider: {provider}{AnimeColor.RESET}")
        print(f"{AnimeColor.INFO}Filename: {filename}{AnimeColor.RESET}")
        
        confirm = input(f"\n{AnimeColor.WARNING}Start download? (y/N): {AnimeColor.RESET}")
        if confirm.lower() != 'y':
            return False
        
        # Try curl first, fallback to requests
        if self.curl_available:
            success = self.download_with_curl(url, filepath, anime_name, episode, quality, provider)
            if success:
                return True
            
            print(f"{AnimeColor.WARNING}Curl failed, trying alternative method...{AnimeColor.RESET}")
        
        return self.download_with_requests(url, filepath, anime_name, episode, quality, provider)

class MediaPlayer:
    """Advanced media player management with intelligent launching"""
    
    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager
        self.current_process = None
    
    def get_player_command(self, url: str, title: str, player_path: str, player_name: str, mode: str = 'sub') -> List[str]:
        """Build player command with subtitle control based on mode"""
        if player_name.upper() == 'VLC':
            base_args = self.config.config.get('PLAYER', 'player_args_vlc', 
                fallback='--play-and-exit --no-video-deco --vout directx --avcodec-hw none').split()
            
            cmd = [player_path, url] + base_args + [
                "--http-referrer", ALLANIME_REFR,
                "--meta-title", title
            ]
            
            # Disable subtitles for dub mode
            if mode == 'dub':
                cmd.extend([
                    "--no-sub-autodetect-file",
                    "--sub-track", "-1",
                    "--no-spu"
                ])
        
        elif player_name.upper() == 'MPV':
            base_args = self.config.config.get('PLAYER', 'player_args_mpv',
                fallback='--keep-open=no --vo=gpu --hwdec=no').split()
            
            cmd = [player_path] + base_args + [
                f"--http-header-fields=Referer: {ALLANIME_REFR}",
                f"--title={title}"
            ]
            
            # Disable subtitles for dub mode
            if mode == 'dub':
                cmd.extend([
                    "--no-sub",
                    "--sid=no", 
                    "--sub-visibility=no"
                ])
            
            cmd.append(url)
        
        else:
            # Generic fallback
            cmd = [player_path, url]
        
        return cmd
    
    def launch_player(self, url: str, anime_name: str, episode: str, 
                     player_path: str, player_name: str, mode: str = 'sub') -> Optional[subprocess.Popen]:
        """Windows-optimized player launching"""
        try:
            title = f"{anime_name} - Episode {episode}"
            cmd = self.get_player_command(url, title, player_path, player_name, mode)
            
            self.close_player()
            
            if os.name == 'nt':
                # Windows-specific process creation
                self.current_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW  # Hide console window
                )
            else:
                self.current_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            
            return self.current_process
            
        except Exception as e:
            logger.error(f"Failed to launch {player_name}: {e}")
            return None

    def close_player(self):
        """Close current player instance"""
        if self.current_process and self.current_process.poll() is None:
            try:
                self.current_process.terminate()
                time.sleep(1)
                if self.current_process.poll() is None:
                    self.current_process.kill()
                logger.info("Closed previous player instance")
            except Exception as e:
                logger.error(f"Failed to close player: {e}")
        self.current_process = None
    
    def is_player_running(self) -> bool:
        """Check if player is currently running"""
        return self.current_process is not None and self.current_process.poll() is None
    
    def get_player_status(self) -> str:
        """Get current player status"""
        if self.current_process is None:
            return "Not started"
        elif self.current_process.poll() is None:
            return "Running"
        else:
            return "Stopped"

class UserInterface:
    """Advanced user interface with intelligent menus and navigation"""
    
    def __init__(self, config_manager: ConfigManager, data_manager: JSONDataManager):
        self.config = config_manager
        self.db = data_manager
    
    def show_main_menu(self) -> int:
        """Display main application menu"""
        print_section("MAIN MENU", "🏠")
        
        options = [
            "🔍 Search and watch anime",
            "▶️  Continue watching",
            "📥 Download anime episodes",
            "📚 View watching history", 
            "📁 View download history",
            "📊 Provider statistics",
            "⚙️  Settings and configuration",
            "❌ Exit application"
        ]
        
        for i, option in enumerate(options, 1):
            print(f"  {AnimeColor.HIGHLIGHT}{i}.{AnimeColor.RESET} {option}")
        
        try:
            choice = int(input(f"\n{AnimeColor.WARNING}Select option (1-{len(options)}): {AnimeColor.RESET}"))
            return choice if 1 <= choice <= len(options) else 0
        except (ValueError, KeyboardInterrupt):
            return 0
    
    def show_anime_selection(self, anime_list: List[Dict]) -> Optional[Dict]:
        """Display anime selection with enhanced information"""
        if not anime_list:
            print(f"{AnimeColor.ERROR}No anime found{AnimeColor.RESET}")
            return None
        
        print_section(f"SEARCH RESULTS ({len(anime_list)} found)", "📺")
        
        for i, anime in enumerate(anime_list, 1):
            print(f"  {AnimeColor.HIGHLIGHT}{i:2d}.{AnimeColor.RESET} {anime['name']}")
            print(f"      {AnimeColor.SECONDARY}Episodes: {anime['episodes']}{AnimeColor.RESET}")
            if anime.get('english_name'):
                print(f"      {AnimeColor.SECONDARY}English: {anime['english_name']}{AnimeColor.RESET}")
            if anime.get('description'):
                print(f"      {AnimeColor.SECONDARY}{anime['description']}{AnimeColor.RESET}")
            print()
        
        try:
            choice = int(input(f"{AnimeColor.WARNING}Select anime (1-{len(anime_list)}): {AnimeColor.RESET}"))
            return anime_list[choice - 1] if 1 <= choice <= len(anime_list) else None
        except (ValueError, KeyboardInterrupt):
            return None
    
    def show_episode_selection(self, episodes: List[str], current_episode: str = None) -> Optional[str]:
        """Display episode selection with grid layout"""
        if not episodes:
            print(f"{AnimeColor.ERROR}No episodes available{AnimeColor.RESET}")
            return None
        
        print_section(f"EPISODE SELECTION ({len(episodes)} episodes)", "🎬")
        
        # Display in grid
        cols = self.config.config.getint('PREFERENCES', 'episode_grid_cols', fallback=8)
        for i in range(0, len(episodes), cols):
            row = episodes[i:i+cols]
            line = "  ".join(
                f"{AnimeColor.SUCCESS if ep == current_episode else AnimeColor.SECONDARY}{ep:>4s}{AnimeColor.RESET}"
                for ep in row
            )
            print(f"  {line}")
        
        try:
            choice = input(f"\n{AnimeColor.WARNING}Enter episode number: {AnimeColor.RESET}")
            return choice if choice in episodes else None
        except KeyboardInterrupt:
            return None
    
    def show_quality_selection(self, links: List[Tuple]) -> Optional[Tuple]:
        """Display quality selection with provider information"""
        if not links:
            print(f"{AnimeColor.ERROR}No quality options available{AnimeColor.RESET}")
            return None
        
        print_section("QUALITY & PROVIDER SELECTION", "⚡")
        
        # Group by provider
        providers = {}
        for i, (fmt, quality, url, provider) in enumerate(links):
            if provider not in providers:
                providers[provider] = []
            providers[provider].append((i, fmt, quality, url))
        
        # Display grouped options
        option_index = 0
        for provider, provider_links in providers.items():
            provider_color = AnimeColor.SUCCESS if provider == "Wixmp" else AnimeColor.INFO
            print(f"\n{provider_color}{provider} Provider:{AnimeColor.RESET}")
            
            for _, fmt, quality, url in provider_links:
                option_index += 1
                format_indicator = "🎥" if fmt == "mp4" else "📡"
                print(f"  {AnimeColor.HIGHLIGHT}{option_index:2d}.{AnimeColor.RESET} {format_indicator} {quality} [{fmt.upper()}]")
        
        try:
            choice = int(input(f"\n{AnimeColor.WARNING}Select option (1-{len(links)}): {AnimeColor.RESET}"))
            return links[choice - 1] if 1 <= choice <= len(links) else None
        except (ValueError, KeyboardInterrupt):
            return None
    
    def show_download_quality_selection(self, mp4_links: List[Tuple]) -> Optional[Tuple]:
        """Display download quality selection with provider grouping"""
        if not mp4_links:
            print(f"{AnimeColor.ERROR}No download options available{AnimeColor.RESET}")
            return None
        
        print_section("DOWNLOAD QUALITY SELECTION", "⚡")
        
        # Group by provider for better display
        providers = {}
        for i, (fmt, quality, url, provider) in enumerate(mp4_links):
            if provider not in providers:
                providers[provider] = []
            providers[provider].append((i, fmt, quality, url))
        
        # Display grouped options
        option_index = 0
        download_options = []
        
        for provider in ["Wixmp", "SharePoint", "YouTube"]:  # Skip HiAnime for downloads
            if provider in providers:
                provider_color = AnimeColor.SUCCESS if provider == "Wixmp" else AnimeColor.INFO
                print(f"\n{provider_color}{provider} Provider:{AnimeColor.RESET}")
                
                for _, fmt, quality, url in providers[provider]:
                    option_index += 1
                    print(f"  {AnimeColor.HIGHLIGHT}{option_index:2d}.{AnimeColor.RESET} 🎥 {quality} [{fmt.upper()}]")
                    download_options.append((fmt, quality, url, provider))
        
        if not download_options:
            print(f"{AnimeColor.ERROR}No download options available{AnimeColor.RESET}")
            return None
        
        # Ask user to select download option
        try:
            choice = int(input(f"\n{AnimeColor.WARNING}Select download option (1-{len(download_options)}): {AnimeColor.RESET}"))
            if 1 <= choice <= len(download_options):
                return download_options[choice - 1]
            else:
                print(f"{AnimeColor.ERROR}Invalid selection{AnimeColor.RESET}")
                return None
        except (ValueError, KeyboardInterrupt):
            print(f"{AnimeColor.ERROR}Invalid input{AnimeColor.RESET}")
            return None
    
    def show_player_controls(self, current_episode: str, episodes: List[str], current_links: List[Tuple] = None) -> Tuple[int, Any]:
        """Display player control menu with proper return values"""
        print_section("PLAYER CONTROLS", "🎮")
        
        controls = [
            "▶️  Continue watching",
            "⏭️  Next episode",
            "⏮️  Previous episode", 
            "🔄 Change episode",
            "⚡ Change quality/provider",
            "📥 Download current episode",
            "📊 View episode cache",
            "🏠 Back to main menu"
        ]
        
        for i, control in enumerate(controls, 1):
            print(f"  {AnimeColor.HIGHLIGHT}{i}.{AnimeColor.RESET} {control}")
        
        # Show current episode info
        current_idx = episodes.index(current_episode) if current_episode in episodes else -1
        total_eps = len(episodes)
        print(f"\n{AnimeColor.INFO}Current: Episode {current_episode} ({current_idx + 1}/{total_eps}){AnimeColor.RESET}")
        
        if current_links:
            print(f"{AnimeColor.INFO}Available qualities: {len(current_links)}{AnimeColor.RESET}")
        
        try:
            choice = int(input(f"\n{AnimeColor.WARNING}Select action (1-{len(controls)}): {AnimeColor.RESET}"))
            
            # Return choice and data for quality change
            if choice == 5 and current_links:  # Change quality
                return choice, current_links
            
            return choice, None
        except (ValueError, KeyboardInterrupt):
            return 0, None
    
    def handle_download_flow(self, api, provider_manager, download_manager, config_manager, args):
        """Complete download flow function"""
        query = input(f"\n{AnimeColor.WARNING}Enter anime name to download: {AnimeColor.RESET}")
        if not query.strip():
            return
        
        mode = "dub" if args.dub else "sub"
        loading_animation("Searching anime for download")
        
        anime_list = api.search_anime(query.strip(), mode)
        anime_info = self.show_anime_selection(anime_list)
        
        if not anime_info:
            input("Press Enter to continue...")
            return
        
        episodes = api.get_episodes_list(anime_info['id'], mode)
        if not episodes:
            print(f"{AnimeColor.ERROR}No episodes found{AnimeColor.RESET}")
            input("Press Enter to continue...")
            return
        
        print_section("DOWNLOAD EPISODE SELECTION", "📥")
        print(f"Anime: {anime_info['name']}")
        print(f"Available episodes: {len(episodes)}")
        
        # Show episodes in grid format
        cols = config_manager.config.getint('PREFERENCES', 'episode_grid_cols', fallback=8)
        for i in range(0, len(episodes), cols):
            row = episodes[i:i+cols]
            line = "  ".join(f"{AnimeColor.SECONDARY}{ep:>4s}{AnimeColor.RESET}" for ep in row)
            print(f"  {line}")
        
        # Main download loop for multiple episodes
        while True:
            # Ask for episode number
            episode_choice = input(f"\n{AnimeColor.WARNING}Enter episode number to download (or 'q' to quit): {AnimeColor.RESET}")
            
            if episode_choice.lower() == 'q':
                break
            
            if episode_choice not in episodes:
                print(f"{AnimeColor.ERROR}Episode {episode_choice} not found{AnimeColor.RESET}")
                continue
            
            # Get download links
            loading_animation("Getting download links")
            links = provider_manager.get_all_links(anime_info['id'], episode_choice, mode)
            
            if not links:
                print(f"{AnimeColor.ERROR}No download links found for Episode {episode_choice}{AnimeColor.RESET}")
                continue
            
            # Filter to only MP4 links for download
            mp4_links = [link for link in links if link[0] == 'mp4']
            
            if not mp4_links:
                print(f"{AnimeColor.ERROR}No MP4 download links available for Episode {episode_choice}{AnimeColor.RESET}")
                print(f"{AnimeColor.INFO}Only M3U8 streams found (not suitable for download){AnimeColor.RESET}")
                continue
            
            # Show download quality selection
            selected_download = self.show_download_quality_selection(mp4_links)
            if not selected_download:
                continue
            
            fmt, quality, url, provider = selected_download
            
            print(f"\n{AnimeColor.INFO}Selected for download:{AnimeColor.RESET}")
            print(f"  Anime: {anime_info['name']}")
            print(f"  Episode: {episode_choice}")
            print(f"  Quality: {quality}")
            print(f"  Provider: {provider}")
            print(f"  Format: {fmt.upper()}")
            
            # Start download
            success = download_manager.download_episode(
                anime_info['name'], 
                episode_choice, 
                quality, 
                url, 
                provider
            )
            
            if success:
                print(f"\n{AnimeColor.SUCCESS}✅ Episode {episode_choice} downloaded successfully!{AnimeColor.RESET}")
            else:
                print(f"\n{AnimeColor.ERROR}❌ Episode {episode_choice} download failed{AnimeColor.RESET}")
            
            # Ask if user wants to download another episode
            another = input(f"\n{AnimeColor.WARNING}Download another episode? (y/N): {AnimeColor.RESET}")
            if another.lower() != 'y':
                break
        
        input("Press Enter to continue...")
    
    def handle_continue_watching(self, api, provider_manager, player, config_manager, data_manager, args, player_path, player_name):
        """Complete continue watching flow function"""
        continue_options = data_manager.get_continue_options()
        if not continue_options:
            print(f"{AnimeColor.WARNING}No anime to continue{AnimeColor.RESET}")
            input("Press Enter to continue...")
            return
        
        print_section("CONTINUE WATCHING", "▶️")
        for i, (anime_id, name, episode, mode, total, quality, provider) in enumerate(continue_options, 1):
            next_ep = str(int(episode) + 1)
            print(f"  {AnimeColor.HIGHLIGHT}{i}.{AnimeColor.RESET} {name}")
            print(f"      {AnimeColor.SECONDARY}Continue from Episode {next_ep} ({mode.upper()}) - Last: {quality or 'Unknown'} [{provider or 'Unknown'}]{AnimeColor.RESET}")
        
        try:
            choice_idx = int(input(f"\n{AnimeColor.WARNING}Select anime (1-{len(continue_options)}): {AnimeColor.RESET}"))
            if 1 <= choice_idx <= len(continue_options):
                anime_id, anime_name, last_episode, mode, total_episodes, last_quality, last_provider = continue_options[choice_idx - 1]
                
                # Calculate next episode
                next_episode = str(int(last_episode) + 1)
                
                print(f"\n{AnimeColor.SUCCESS}Continuing: {anime_name}{AnimeColor.RESET}")
                print(f"{AnimeColor.INFO}Next episode: {next_episode}{AnimeColor.RESET}")
                
                # Get all episodes for navigation
                episodes = api.get_episodes_list(anime_id, mode)
                if not episodes:
                    print(f"{AnimeColor.ERROR}Could not fetch episodes list{AnimeColor.RESET}")
                    input("Press Enter to continue...")
                    return
                
                # Check if next episode exists
                if next_episode not in episodes:
                    print(f"{AnimeColor.ERROR}Episode {next_episode} not available{AnimeColor.RESET}")
                    print(f"{AnimeColor.INFO}Available episodes: {', '.join(episodes[-5:])}{AnimeColor.RESET}")
                    input("Press Enter to continue...")
                    return
                
                # Start the watching session from next episode
                self._start_watching_session(
                    {'id': anime_id, 'name': anime_name, 'episodes': total_episodes}, 
                    episodes, 
                    next_episode, 
                    mode, 
                    api, 
                    provider_manager, 
                    player, 
                    data_manager, 
                    player_path, 
                    player_name
                )
            else:
                print(f"{AnimeColor.ERROR}Invalid selection{AnimeColor.RESET}")
        except (ValueError, KeyboardInterrupt):
            pass
        
        input("Press Enter to continue...")
    
    def _start_watching_session(self, anime_info, episodes, starting_episode, mode, api, provider_manager, player, data_manager, player_path, player_name):
        """Start a complete watching session with navigation"""
        current_episode = starting_episode
        current_links = None
        
        while True:
            clear_terminal()
            print(f"{AnimeColor.SUCCESS}Watching: {anime_info['name']} - Episode {current_episode}{AnimeColor.RESET}")
            print(f"{AnimeColor.INFO}Mode: {mode.upper()}{AnimeColor.RESET}")
            
            loading_animation("Getting video links")
            links = provider_manager.get_all_links(anime_info['id'], current_episode, mode)
            current_links = links  # Store for quality change
            
            if not links:
                print(f"{AnimeColor.ERROR}No video links found for Episode {current_episode}{AnimeColor.RESET}")
                
                # Ask if user wants to try different episode
                retry_choice = input(f"{AnimeColor.WARNING}Try different episode? (y/N): {AnimeColor.RESET}")
                if retry_choice.lower() == 'y':
                    new_episode = self.show_episode_selection(episodes, current_episode)
                    if new_episode:
                        current_episode = new_episode
                        continue
                break
            
            # Auto-select best quality or show selection
            if len(links) == 1:
                selected_link = links[0]
            else:
                # Try to find previous quality/provider first
                preferred_link = None
                for link in links:
                    if link[0] == 'mp4':  # Prefer MP4 format
                        preferred_link = link
                        break
                
                if preferred_link:
                    use_auto = input(f"{AnimeColor.INFO}Auto-select {preferred_link[1]} from {preferred_link[3]}? (Y/n): {AnimeColor.RESET}")
                    if use_auto.lower() != 'n':
                        selected_link = preferred_link
                    else:
                        selected_link = self.show_quality_selection(links)
                        if not selected_link:
                            break
                else:
                    selected_link = self.show_quality_selection(links)
                    if not selected_link:
                        break
            
            fmt, quality, url, provider = selected_link
            print(f"{AnimeColor.SUCCESS}Selected: {quality} from {provider}{AnimeColor.RESET}")
            
            # Launch player
            process = player.launch_player(url, anime_info['name'], current_episode, player_path, player_name)
            if process:
                print(f"{AnimeColor.SUCCESS}Player launched successfully{AnimeColor.RESET}")
                
                # Update history
                data_manager.add_history(anime_info['id'], anime_info['name'], 
                                     current_episode, mode, anime_info['episodes'], quality, provider)
            else:
                print(f"{AnimeColor.ERROR}Failed to launch player{AnimeColor.RESET}")
                input("Press Enter to continue...")
                break
            
            # Show controls with current links
            time.sleep(2)
            action, data = self.show_player_controls(current_episode, episodes, current_links)
            
            if action == 1:  # Continue
                continue
            elif action == 2:  # Next episode
                current_idx = episodes.index(current_episode)
                if current_idx < len(episodes) - 1:
                    current_episode = episodes[current_idx + 1]
                    continue
                else:
                    print(f"{AnimeColor.SUCCESS}Finished watching {anime_info['name']}!{AnimeColor.RESET}")
                    input("Press Enter to continue...")
                    break
            elif action == 3:  # Previous episode
                current_idx = episodes.index(current_episode)
                if current_idx > 0:
                    current_episode = episodes[current_idx - 1]
                    continue
                else:
                    print(f"{AnimeColor.WARNING}Already at first episode{AnimeColor.RESET}")
                    input("Press Enter to continue...")
            elif action == 4:  # Change episode
                new_episode = self.show_episode_selection(episodes, current_episode)
                if new_episode:
                    current_episode = new_episode
                    continue
            elif action == 5:  # Change quality
                if data:  # data contains current_links
                    print_section("CHANGE QUALITY/PROVIDER", "⚡")
                    new_selection = self.show_quality_selection(data)
                    if new_selection:
                        new_fmt, new_quality, new_url, new_provider = new_selection
                        
                        # Close current player
                        player.close_player()
                        time.sleep(1)
                        
                        # Launch with new quality
                        process = player.launch_player(new_url, anime_info['name'], current_episode, player_path, player_name)
                        if process:
                            print(f"{AnimeColor.SUCCESS}Switched to: {new_quality} from {new_provider}{AnimeColor.RESET}")
                            
                            # Update history with new quality
                            data_manager.add_history(anime_info['id'], anime_info['name'], 
                                                 current_episode, mode, anime_info['episodes'], new_quality, new_provider)
                            
                            # Update current selection for future controls
                            selected_link = new_selection
                            fmt, quality, url, provider = selected_link
                            
                            time.sleep(2)
                            continue
                        else:
                            print(f"{AnimeColor.ERROR}Failed to launch with new quality{AnimeColor.RESET}")
                            input("Press Enter to continue...")
                else:
                    print(f"{AnimeColor.ERROR}No quality options available{AnimeColor.RESET}")
                    input("Press Enter to continue...")
            elif action == 6:  # Download
                # Get fresh links for download (MP4 only)
                download_links = [link for link in current_links if link[0] == 'mp4']
                if download_links:
                    selected_download = self.show_download_quality_selection(download_links)
                    if selected_download:
                        print(f"{AnimeColor.INFO}Download feature available - would download:{AnimeColor.RESET}")
                        print(f"  {anime_info['name']} - Episode {current_episode}")
                else:
                    print(f"{AnimeColor.ERROR}No MP4 links available for download{AnimeColor.RESET}")
                input("Press Enter to continue...")
            elif action == 7:  # Cache info
                cache_files = list(CACHE_DIR.glob("*.json"))
                print(f"{AnimeColor.INFO}Cache files: {len(cache_files)}{AnimeColor.RESET}")
                print(f"{AnimeColor.INFO}Cache directory: {CACHE_DIR}{AnimeColor.RESET}")
                input("Press Enter to continue...")
            else:  # Back to main
                break

def main():
    """Main application entry point with Windows optimization"""
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} v{APP_VERSION} - Windows-optimized anime streaming"
    )
    parser.add_argument("query", nargs="*", help="Anime search query")
    parser.add_argument("--dub", action="store_true", help="Search for dubbed anime")
    parser.add_argument("--player", choices=["vlc", "mpv"], help="Force specific media player")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--config", help="Custom config file path")
    
    args = parser.parse_args()
    
    try:
        # Initialize components
        config_manager = ConfigManager(Path(args.config) if args.config else CONFIG_FILE)
        data_manager = JSONDataManager()
        api = AnimeAPI(config_manager)
        provider_manager = ProviderManager(config_manager, data_manager)
        download_manager = DownloadManager(config_manager, data_manager)
        player = MediaPlayer(config_manager)
        ui = UserInterface(config_manager, data_manager)
        
        # Set debug mode
        if args.debug:
            logger.debug_mode = True
            logger.info("Debug mode enabled")
        
        # Handle direct command line usage
        if args.query:
            query = " ".join(args.query)
            mode = "dub" if args.dub else "sub"
            
            if args.download:
                # Direct download mode
                print(f"{AnimeColor.INFO}Direct download mode for: {query}{AnimeColor.RESET}")
                # Implementation would go here
            else:
                # Direct watch mode  
                print(f"{AnimeColor.INFO}Direct watch mode for: {query}{AnimeColor.RESET}")
                # Implementation would go here
            return
        
        # Main application loop
        print_banner()
        
        # Check player availability
        player_path, player_name = config_manager.get_player_path(args.player)
        if not player_path:
            print(f"{AnimeColor.ERROR}❌ No media player found!{AnimeColor.RESET}")
            print(f"{AnimeColor.INFO}Please install VLC or MPV, or check configuration.{AnimeColor.RESET}")
            print(f"{AnimeColor.INFO}Config file: {CONFIG_FILE}{AnimeColor.RESET}")
            return
        
        print(f"{AnimeColor.SUCCESS}✅ Using {player_name}: {player_path}{AnimeColor.RESET}")
        
        while True:
            try:
                clear_terminal()
                print_banner()
                print(f"{AnimeColor.INFO}🎥 Player: {player_name} | 📁 Downloads: {DOWNLOAD_DIR}{AnimeColor.RESET}")
                
                choice = ui.show_main_menu()
                
                if choice == 1:  # Search and watch
                    query = input(f"\n{AnimeColor.WARNING}Enter anime name: {AnimeColor.RESET}")
                    if not query.strip():
                        continue
                    
                    mode = "dub" if args.dub else "sub"
                    loading_animation("Searching anime")
                    
                    anime_list = api.search_anime(query.strip(), mode)
                    anime_info = ui.show_anime_selection(anime_list)
                    
                    if not anime_info:
                        input("Press Enter to continue...")
                        continue
                    
                    episodes = api.get_episodes_list(anime_info['id'], mode)
                    if not episodes:
                        print(f"{AnimeColor.ERROR}No episodes found{AnimeColor.RESET}")
                        input("Press Enter to continue...")
                        continue
                    
                    current_episode = ui.show_episode_selection(episodes)
                    if not current_episode:
                        continue
                    
                    # Main watching loop with quality change
                    current_links = None
                    while True:
                        clear_terminal()
                        print(f"{AnimeColor.SUCCESS}Watching: {anime_info['name']} - Episode {current_episode}{AnimeColor.RESET}")
                        
                        loading_animation("Getting video links")
                        links = provider_manager.get_all_links(anime_info['id'], current_episode, mode)
                        current_links = links  # Store for quality change
                        
                        if not links:
                            print(f"{AnimeColor.ERROR}No video links found{AnimeColor.RESET}")
                            input("Press Enter to continue...")
                            break
                        
                        # Auto-select best quality or show selection
                        if len(links) == 1:
                            selected_link = links[0]
                        else:
                            selected_link = ui.show_quality_selection(links)
                            if not selected_link:
                                break
                        
                        fmt, quality, url, provider = selected_link
                        print(f"{AnimeColor.SUCCESS}Selected: {quality} from {provider}{AnimeColor.RESET}")
                        
                        # Launch player
                        process = player.launch_player(url, anime_info['name'], current_episode, player_path, player_name)
                        if process:
                            print(f"{AnimeColor.SUCCESS}{player_name} launched successfully{AnimeColor.RESET}")
                            
                            # Update history
                            data_manager.add_history(anime_info['id'], anime_info['name'], 
                                                 current_episode, mode, anime_info['episodes'], quality, provider)
                        else:
                            print(f"{AnimeColor.ERROR}Failed to launch player{AnimeColor.RESET}")
                            input("Press Enter to continue...")
                            break
                        
                        # Show controls with current links
                        time.sleep(2)
                        action, data = ui.show_player_controls(current_episode, episodes, current_links)
                        
                        if action == 1:  # Continue
                            continue
                        elif action == 2:  # Next episode
                            current_idx = episodes.index(current_episode)
                            if current_idx < len(episodes) - 1:
                                current_episode = episodes[current_idx + 1]
                                continue
                            else:
                                print(f"{AnimeColor.WARNING}Already at last episode{AnimeColor.RESET}")
                                input("Press Enter to continue...")
                        elif action == 3:  # Previous episode
                            current_idx = episodes.index(current_episode)
                            if current_idx > 0:
                                current_episode = episodes[current_idx - 1]
                                continue
                            else:
                                print(f"{AnimeColor.WARNING}Already at first episode{AnimeColor.RESET}")
                                input("Press Enter to continue...")
                        elif action == 4:  # Change episode
                            new_episode = ui.show_episode_selection(episodes, current_episode)
                            if new_episode:
                                current_episode = new_episode
                                continue
                        elif action == 5:  # Change quality
                            if data:  # data contains current_links
                                
                                new_selection = ui.show_quality_selection(data)
                                if new_selection:
                                    new_fmt, new_quality, new_url, new_provider = new_selection
                                    
                                    # Close current player
                                    player.close_player()
                                    time.sleep(1)
                                    
                                    # Launch with new quality
                                    process = player.launch_player(new_url, anime_info['name'], current_episode, player_path, player_name)
                                    if process:
                                        print(f"{AnimeColor.SUCCESS}Switched to: {new_quality} from {new_provider}{AnimeColor.RESET}")
                                        
                                        # Update history with new quality
                                        data_manager.add_history(anime_info['id'], anime_info['name'], 
                                                             current_episode, mode, anime_info['episodes'], new_quality, new_provider)
                                        
                                        # Update current selection for future controls
                                        selected_link = new_selection
                                        fmt, quality, url, provider = selected_link
                                        
                                        time.sleep(2)
                                        continue
                                    else:
                                        print(f"{AnimeColor.ERROR}Failed to launch with new quality{AnimeColor.RESET}")
                                        input("Press Enter to continue...")
                            else:
                                print(f"{AnimeColor.ERROR}No quality options available{AnimeColor.RESET}")
                                input("Press Enter to continue...")
                        elif action == 6:  # Download
                            success = download_manager.download_episode(
                                anime_info['name'], current_episode, quality, url, provider
                            )
                            if success:
                                print(f"{AnimeColor.SUCCESS}Download completed{AnimeColor.RESET}")
                            input("Press Enter to continue...")
                        elif action == 7:  # Cache info
                            cache_files = list(CACHE_DIR.glob("*.json"))
                            print(f"{AnimeColor.INFO}Cache files: {len(cache_files)}{AnimeColor.RESET}")
                            print(f"{AnimeColor.INFO}Cache directory: {CACHE_DIR}{AnimeColor.RESET}")
                            input("Press Enter to continue...")
                        else:  # Back to main
                            break
                
                elif choice == 2:  # Continue watching
                    ui.handle_continue_watching(api, provider_manager, player, config_manager, data_manager, args, player_path, player_name)
                
                elif choice == 3:  # Download
                    ui.handle_download_flow(api, provider_manager, download_manager, config_manager, args)
                
                elif choice == 4:  # History
                    history = data_manager.get_history()
                    print_section("VIEWING HISTORY", "📚")
                    
                    if not history:
                        print(f"{AnimeColor.WARNING}No viewing history{AnimeColor.RESET}")
                    else:
                        for i, (name, episode, mode, quality, provider, date, total, rating) in enumerate(history, 1):
                            print(f"  {AnimeColor.HIGHLIGHT}{i:2d}.{AnimeColor.RESET} {name} - EP{episode}")
                            print(f"      {AnimeColor.SECONDARY}{mode.upper()} | {quality or 'Unknown'} | {provider or 'Unknown'} | {date}{AnimeColor.RESET}")
                    
                    input("Press Enter to continue...")
                
                elif choice == 5:  # Downloads
                    downloads = data_manager.get_downloads()
                    print_section("DOWNLOAD HISTORY", "📁")
                    
                    if not downloads:
                        print(f"{AnimeColor.WARNING}No download history{AnimeColor.RESET}")
                    else:
                        for i, (name, episode, quality, provider, path, size, date, status) in enumerate(downloads, 1):
                            print(f"  {AnimeColor.HIGHLIGHT}{i:2d}.{AnimeColor.RESET} {name} - EP{episode}")
                            print(f"      {AnimeColor.SECONDARY}{quality} | {provider} | {size/(1024*1024):.1f}MB | {status}{AnimeColor.RESET}")
                            print(f"      {AnimeColor.SECONDARY}{path}{AnimeColor.RESET}")
                    
                    input("Press Enter to continue...")
                
                elif choice == 6:  # Provider stats
                    stats = data_manager.get_provider_rankings()
                    print_section("PROVIDER STATISTICS", "📊")
                    
                    if not stats:
                        print(f"{AnimeColor.WARNING}No provider statistics available{AnimeColor.RESET}")
                    else:
                        print(f"{'Provider':<12} {'Success Rate':<12} {'Avg Response':<12} {'Total Requests'}")
                        print("─" * 60)
                        for provider, success, failure, avg_time, success_rate in stats:
                            total_requests = success + failure
                            print(f"{provider:<12} {success_rate:>10.1f}% {avg_time:>10.2f}s {total_requests:>13}")
                    
                    input("Press Enter to continue...")
                
                elif choice == 7:  # Settings
                    print_section("SETTINGS & CONFIGURATION", "⚙️")
                    print(f"Config file: {CONFIG_FILE}")
                    print(f"Player: {player_name} ({player_path})")
                    print(f"Download directory: {DOWNLOAD_DIR}")
                    print(f"Cache directory: {CACHE_DIR}")
                    print(f"Database: {HISTORY_FILE}")
                    print(f"Log file: {LOG_FILE}")
                    
                    input("Press Enter to continue...")
                
                elif choice == 8:  # Exit
                    break
                
                else:
                    print(f"{AnimeColor.ERROR}Invalid option{AnimeColor.RESET}")
                    input("Press Enter to continue...")
            
            except KeyboardInterrupt:
                print(f"\n{AnimeColor.WARNING}Interrupted by user{AnimeColor.RESET}")
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                print(f"{AnimeColor.ERROR}An error occurred: {e}{AnimeColor.RESET}")
                input("Press Enter to continue...")
    
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print(f"{AnimeColor.BG_ERROR}Fatal Error: {e}{AnimeColor.RESET}")
    
    finally:
        # Cleanup
        if 'player' in locals():
            player.close_player()
        
        print(f"\n{AnimeColor.SUCCESS}Thank you for using {APP_NAME}!{AnimeColor.RESET}")

if __name__ == "__main__":
    main()

"""
If you think is good piece of code for you then i am glad my hard work paid off bcz this work took about 10 hr to a lot to imagine but short to live 
It was fun build ani-cli in python just in simple way 
Hope You Will Enjoy It 😎
"""
