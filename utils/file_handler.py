"""
File handling utilities for M3U2strm3 Web Interface.
Handles file uploads, configuration management, and file validation.
"""

import os
import json
import shutil
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging
from slugify import slugify

logger = logging.getLogger(__name__)


class FileHandler:
    """Handles file operations for the web interface."""
    
    def __init__(self, upload_dir: str = "web/uploads", config_dir: str = "web/configs"):
        self.upload_dir = Path(upload_dir)
        self.config_dir = Path(config_dir)
        
        # Create directories
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Configuration presets
        self._default_config = {
            "m3u": "",
            "sqlite_cache_file": "cache.db",
            "log_file": "m3u2strm.log",
            "output_dir": "output",
            "existing_media_dirs": [],
            "tmdb_api": "",
            "emby_api_url": "",
            "emby_api_key": "",
            "dry_run": False,
            "max_workers": None,
            "verbosity": "normal",
            "allowed_movie_countries": ["US", "GB", "CA"],
            "allowed_tv_countries": ["US", "GB", "CA"],
            "write_non_us_report": True,
            "tv_group_keywords": ["ser", "action", "comedy", "drama"],
            "doc_group_keywords": ["doc"],
            "movie_group_keywords": ["4k", "actionm", "comedym", "dramam"],
            "replay_group_keywords": ["replays"],
            "ignore_keywords": {
                "tvshows": ["ufc", "wwe", "pokemon"],
                "movies": ["ufc", "pokemon", "wwe"]
            }
        }
    
    async def save_upload(self, file) -> Dict[str, Any]:
        """Save uploaded file with validation."""
        try:
            # Validate file type
            if not self._is_valid_m3u_file(file.filename):
                raise ValueError(f"Invalid file type: {file.filename}")
            
            # Generate safe filename
            safe_name = self._generate_safe_filename(file.filename)
            file_path = self.upload_dir / safe_name
            
            # Save file
            content = await file.read()
            async with open(file_path, 'wb') as f:
                f.write(content)
            
            # Get file info
            file_size = len(content)
            file_hash = self._calculate_file_hash(content)
            
            logger.info(f"Uploaded file: {file.filename} -> {safe_name} ({file_size} bytes)")
            
            return {
                "filename": file.filename,
                "safe_name": safe_name,
                "size": file_size,
                "path": str(file_path),
                "hash": file_hash,
                "message": "File uploaded successfully"
            }
            
        except Exception as e:
            logger.error(f"Error saving upload: {e}")
            raise
    
    def _is_valid_m3u_file(self, filename: str) -> bool:
        """Validate if file is a valid M3U playlist."""
        if not filename:
            return False
        
        # Check file extension
        if not filename.lower().endswith(('.m3u', '.m3u8')):
            return False
        
        # Check filename characters
        safe_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.')
        if not all(c in safe_chars for c in filename.replace('.', '')):
            return False
        
        return True
    
    def _generate_safe_filename(self, filename: str) -> str:
        """Generate a safe filename for uploads."""
        # Remove extension and create slug
        name_without_ext = Path(filename).stem
        safe_name = slugify(name_without_ext, allow_unicode=False)
        
        # Add timestamp to avoid conflicts
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"{safe_name}_{timestamp}.m3u"
        
        # Ensure uniqueness
        counter = 1
        while (self.upload_dir / safe_filename).exists():
            safe_filename = f"{safe_name}_{timestamp}_{counter}.m3u"
            counter += 1
        
        return safe_filename
    
    def _calculate_file_hash(self, content: bytes) -> str:
        """Calculate SHA256 hash of file content."""
        return hashlib.sha256(content).hexdigest()
    
    def list_uploads(self) -> List[Dict[str, Any]]:
        """List all uploaded files."""
        uploads = []
        
        for file_path in self.upload_dir.glob("*.m3u"):
            try:
                stat = file_path.stat()
                uploads.append({
                    "filename": file_path.name,
                    "size": stat.st_size,
                    "created": datetime.fromtimestamp(stat.st_ctime),
                    "modified": datetime.fromtimestamp(stat.st_mtime),
                    "path": str(file_path)
                })
            except Exception as e:
                logger.error(f"Error reading file info for {file_path}: {e}")
        
        # Sort by modification time, newest first
        uploads.sort(key=lambda x: x["modified"], reverse=True)
        return uploads
    
    def get_upload_path(self, filename: str) -> Optional[Path]:
        """Get the full path to an uploaded file."""
        file_path = self.upload_dir / filename
        if file_path.exists():
            return file_path
        return None
    
    def delete_upload(self, filename: str) -> bool:
        """Delete an uploaded file."""
        file_path = self.upload_dir / filename
        try:
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Deleted upload: {filename}")
                return True
        except Exception as e:
            logger.error(f"Error deleting upload {filename}: {e}")
        return False
    
    def save_config(self, config_data: Dict[str, Any]) -> bool:
        """Save configuration to file."""
        try:
            # Validate required fields
            required_fields = ["m3u", "sqlite_cache_file", "log_file", "output_dir", "tmdb_api"]
            for field in required_fields:
                if field not in config_data or not config_data[field]:
                    raise ValueError(f"Missing required field: {field}")
            
            # Save configuration
            config_file = self.config_dir / "config.json"
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            
            logger.info("Configuration saved successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            raise
    
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        config_file = self.config_dir / "config.json"
        
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # Merge with defaults for any missing fields
                merged_config = self._default_config.copy()
                merged_config.update(config)
                
                return merged_config
                
            except Exception as e:
                logger.error(f"Error loading configuration: {e}")
                return self._default_config
        else:
            return self._default_config
    
    def save_config_preset(self, preset_name: str, config_data: Dict[str, Any]) -> bool:
        """Save a configuration preset."""
        try:
            # Validate preset name
            safe_name = slugify(preset_name, allow_unicode=False)
            if not safe_name:
                raise ValueError("Invalid preset name")
            
            preset_file = self.config_dir / f"preset_{safe_name}.json"
            
            with open(preset_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Configuration preset saved: {preset_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving preset {preset_name}: {e}")
            return False
    
    def load_config_preset(self, preset_name: str) -> Optional[Dict[str, Any]]:
        """Load a configuration preset."""
        try:
            safe_name = slugify(preset_name, allow_unicode=False)
            preset_file = self.config_dir / f"preset_{safe_name}.json"
            
            if preset_file.exists():
                with open(preset_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            
        except Exception as e:
            logger.error(f"Error loading preset {preset_name}: {e}")
        
        return None
    
    def list_config_presets(self) -> List[str]:
        """List available configuration presets."""
        presets = []
        
        for preset_file in self.config_dir.glob("preset_*.json"):
            try:
                # Extract preset name from filename
                preset_name = preset_file.stem.replace("preset_", "").replace("_", " ").title()
                presets.append(preset_name)
            except Exception as e:
                logger.error(f"Error reading preset {preset_file}: {e}")
        
        return sorted(presets)
    
    def delete_config_preset(self, preset_name: str) -> bool:
        """Delete a configuration preset."""
        try:
            safe_name = slugify(preset_name, allow_unicode=False)
            preset_file = self.config_dir / f"preset_{safe_name}.json"
            
            if preset_file.exists():
                preset_file.unlink()
                logger.info(f"Deleted preset: {preset_name}")
                return True
                
        except Exception as e:
            logger.error(f"Error deleting preset {preset_name}: {e}")
        
        return False
    
    def validate_config(self, config_data: Dict[str, Any]) -> List[str]:
        """Validate configuration data and return list of errors."""
        errors = []
        
        # Required fields
        required_fields = ["m3u", "sqlite_cache_file", "log_file", "output_dir", "tmdb_api"]
        for field in required_fields:
            if field not in config_data or not config_data[field]:
                errors.append(f"Missing required field: {field}")
        
        # File path validation
        if "m3u" in config_data and config_data["m3u"]:
            m3u_path = Path(config_data["m3u"])
            if not m3u_path.exists():
                errors.append(f"M3U file does not exist: {config_data['m3u']}")
        
        if "output_dir" in config_data and config_data["output_dir"]:
            try:
                output_path = Path(config_data["output_dir"])
                output_path.mkdir(parents=True, exist_ok=True)
                if not output_path.is_dir():
                    errors.append(f"Output directory is not a directory: {config_data['output_dir']}")
            except Exception as e:
                errors.append(f"Cannot create output directory: {e}")
        
        # TMDb API key validation
        if "tmdb_api" in config_data and config_data["tmdb_api"]:
            api_key = config_data["tmdb_api"]
            if len(api_key) < 10:  # Basic length check
                errors.append("TMDb API key appears to be too short")
        
        # Country codes validation
        if "allowed_movie_countries" in config_data:
            for country in config_data["allowed_movie_countries"]:
                if not isinstance(country, str) or len(country) != 2:
                    errors.append(f"Invalid country code: {country}")
        
        if "allowed_tv_countries" in config_data:
            for country in config_data["allowed_tv_countries"]:
                if not isinstance(country, str) or len(country) != 2:
                    errors.append(f"Invalid country code: {country}")
        
        return errors
    
    def get_file_info(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Get information about a file."""
        try:
            path = Path(file_path)
            if not path.exists():
                return None
            
            stat = path.stat()
            return {
                "name": path.name,
                "size": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_ctime),
                "modified": datetime.fromtimestamp(stat.st_mtime),
                "path": str(path),
                "is_file": path.is_file(),
                "is_dir": path.is_dir()
            }
            
        except Exception as e:
            logger.error(f"Error getting file info for {file_path}: {e}")
            return None
    
    def cleanup_old_uploads(self, days: int = 7) -> int:
        """Clean up uploads older than specified days."""
        cutoff_time = datetime.now().timestamp() - (days * 24 * 60 * 60)
        deleted_count = 0
        
        for file_path in self.upload_dir.glob("*.m3u"):
            try:
                if file_path.stat().st_mtime < cutoff_time:
                    file_path.unlink()
                    deleted_count += 1
                    logger.info(f"Cleaned up old upload: {file_path.name}")
            except Exception as e:
                logger.error(f"Error cleaning up {file_path}: {e}")
        
        return deleted_count
