# M3U2strm3

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Stable-brightgreen.svg)](#)

**M3U2strm3** is a powerful Python application that converts IPTV M3U playlists into organized STRM files for media servers like Emby, Jellyfin, and Plex. It intelligently filters content by country, manages duplicates, and keeps your media library synchronized with your IPTV provider.

## 🚀 Features

### Core Functionality
- **Smart Playlist Processing**: Parse M3U playlists and extract movie, TV show, and documentary entries
- **Country-Based Filtering**: Use TMDb API to filter content by allowed countries (US, GB, CA by default)
- **Duplicate Detection**: Automatically skip content that already exists in your local media library
- **Organized Output**: Create structured STRM files in Movies, TV Shows, and Documentaries folders
- **Emby Integration**: Automatic library refresh after updates

### Advanced Features
- **Multi-Category Support**: Handle Movies, TV Shows, Documentaries, and Replays
- **Concurrent Processing**: Multi-threaded for optimal performance (configurable workers)
- **Cache Management**: SQLite database for tracking processed content and avoiding re-processing
- **Keyword Filtering**: Ignore specific content using customizable keyword lists
- **Force Regeneration**: Command-line option to rebuild all STRM files
- **Comprehensive Logging**: Detailed logs with file and console output
- **Cleanup Features**: Remove orphaned STRM files and empty directories

### Smart Filtering
- **TMDb Integration**: Verify content availability and country restrictions
- **Language Filtering**: Automatically exclude Japanese content
- **Year Extraction**: Extract and use release years for accurate matching
- **Group-Based Classification**: Use M3U group titles to categorize content

## 📋 Requirements

- Python 3.8 or higher
- TMDb API key (free registration required)
- Access to your IPTV M3U playlist

## 🛠️ Installation

### 1. Clone the Repository
```bash
git clone https://github.com/evilgenx/M3U2strm3.git
cd M3U2strm3
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure the Application
Copy the example configuration file and edit it with your settings:
```bash
cp config.json.example config.json
```

Edit `config.json` with your settings (see [Configuration](#-configuration) below).

**Note:** The `config.json` file contains sensitive information like API keys and should not be committed to version control. The `config.json.example` file provides a template with placeholder values that you can use as a reference.

## ⚙️ Configuration

The `config.json` file contains all settings for M3U2strm3. Here's a breakdown of the key sections:

### Basic Settings
```json
{
  "m3u": "/path/to/your/playlist.m3u",
  "sqlite_cache_file": "/path/to/cache.db",
  "log_file": "/path/to/m3u2strm.log",
  "output_dir": "/path/to/output/strm/files",
  "tmdb_api": "your_tmdb_api_key_here"
}
```

### Media Directories
```json
{
  "existing_media_dirs": [
    "/path/to/local/movies/",
    "/path/to/local/tv_shows/"
  ]
}
```

### Country Filtering
```json
{
  "allowed_movie_countries": ["US", "GB", "CA"],
  "allowed_tv_countries": ["US", "GB", "CA"]
}
```

### Content Classification
```json
{
  "tv_group_keywords": ["ser", "action", "comedy", "drama"],
  "doc_group_keywords": ["doc"],
  "movie_group_keywords": ["4k", "actionm", "comedym", "dramam"],
  "replay_group_keywords": ["replays"]
}
```

### Keyword Filtering
```json
{
  "ignore_keywords": {
    "tvshows": ["ufc", "wwe", "pokemon"],
    "movies": ["ufc", "pokemon", "wwe"],
    "documentaries": []
  }
}
```

### Emby Integration
```json
{
  "emby_api_url": "https://your-emby-server.com",
  "emby_api_key": "your_emby_api_key",
  "dry_run": false
}
```

## 📖 Usage

### Basic Usage
```bash
python main.py
```

### Force Regeneration
Rebuild all STRM files, ignoring cache:
```bash
python main.py --force-regenerate
```

### Configuration Options
- `--force-regenerate`: Force regeneration of all STRM files, skipping cache checks

## 📁 Project Structure

```
M3U2strm3/
├── main.py              # Main application orchestrator
├── core.py              # Core logic: media scanning, title normalization, caching
├── m3u_utils.py         # M3U parsing and TMDb filtering
├── strm_utils.py        # STRM file creation and cleanup
├── config.py            # Configuration loading
├── config.json          # Configuration file
├── requirements.txt     # Python dependencies
└── readme.md           # This file
```

### File Purposes

| File | Purpose |
|------|---------|
| `main.py` | Orchestrates the full process: scanning, filtering, and STRM creation |
| `core.py` | Scans local media, normalizes titles, manages SQLite cache |
| `m3u_utils.py` | Parses M3U files, applies TMDb filters, categorizes content |
| `strm_utils.py` | Writes and cleans STRM files, manages directory structure |
| `config.py` | Loads and validates configuration settings |

## 🔄 How It Works

### Processing Pipeline

1. **Scan Local Media**
   - Searches existing movie and TV folders
   - Builds a cache of locally available content
   - Identifies Movies, TV Episodes, and Documentaries

2. **Parse M3U Playlist**
   - Reads your IPTV playlist file
   - Extracts titles, URLs, and group information
   - Classifies content by category

3. **Apply Filters**
   - Uses TMDb API to verify country availability
   - Filters by allowed countries (US, GB, CA by default)
   - Applies keyword-based exclusions
   - Skips Japanese content automatically

4. **Generate STRM Files**
   - Creates organized directory structure
   - Writes STRM files pointing to IPTV streams
   - Maintains SQLite cache for efficiency

5. **Cleanup and Integration**
   - Removes orphaned STRM files
   - Cleans up empty directories
   - Triggers Emby library refresh (if configured)

### Example Output Structure

```
/media/m3u2strm/
├── Movies/
│   ├── Heat (1995)/Heat (1995).strm
│   └── Inception (2010)/Inception (2010).strm
├── TV Shows/
│   ├── Breaking Bad (2008)/Season 01/Breaking Bad (2008) S01E01.strm
│   └── The Office (2005)/Season 02/The Office (2005) S02E03.strm
└── Documentaries/
    ├── Planet Earth (2006)/Planet Earth (2006).strm
    └── Cosmos (2014)/Cosmos (2014).strm
```

## 🐛 Troubleshooting

### Common Issues

**TMDb API Rate Limits**
- The application includes automatic retry logic for rate limits
- Consider reducing `max_workers` in config if you hit limits frequently
- Ensure your TMDb API key is valid

**Permission Errors**
- Ensure write permissions to output directory
- Check that media directories are readable
- Verify log file directory exists and is writable

**Missing Dependencies**
```bash
pip install -r requirements.txt
```

**Configuration Errors**
- Validate JSON syntax in `config.json`
- Ensure all required paths exist
- Check TMDb API key format

### Log Analysis
The application provides detailed logging. Check the log file for:
- Processing progress and statistics
- Filtering decisions and reasons
- Error messages and stack traces
- Performance metrics

### Debug Mode
For detailed debugging, modify the logging level in `main.py`:
```python
logger.setLevel(logging.DEBUG)  # Change from INFO to DEBUG
```

## 🤝 Contributing

We welcome contributions! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Setup
```bash
# Clone your fork
git clone https://github.com/your-username/M3U2strm3.git
cd M3U2strm3

# Install development dependencies
pip install -r requirements.txt

# Run tests (if available)
python -m pytest

# Make your changes and test thoroughly
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **TMDb API** for providing comprehensive movie and TV show data
- **IPTV providers** for making content accessible
- **Emby team** for creating excellent media server software

## 🔗 Related Projects

- [Emby](https://emby.media/) - Media server with excellent STRM support
- [Jellyfin](https://jellyfin.org/) - Open-source media server
- [Plex](https://www.plex.tv/) - Popular media server platform

---

**M3U2strm3** - Keeping your media library in sync with your IPTV provider since 2025.
