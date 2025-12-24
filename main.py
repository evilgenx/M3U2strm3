import logging
import re
import concurrent.futures
import argparse
from pathlib import Path
from collections import defaultdict
import requests
import config
from core import (
    SQLiteCache,
    build_existing_media_cache,
    canonical_movie_key,
    canonical_tv_key,
    make_cache_key,
    sanitize_title,
    extract_year,
)
from m3u_utils import (
    parse_m3u,
    split_by_market_filter,
    Category,
    VODEntry,
)
from strm_utils import (
    write_strm_file,
    cleanup_strm_tree,
    movie_strm_path,
    tv_strm_path,
    doc_strm_path,
)
from progress_tracker import ProgressTracker, ProgressPhase, VerbosityLevel
from user_progress_display import UserProgressDisplay, SimpleProgressDisplay


def touch_emby(api_url: str, api_key: str):
    try:
        refresh_url = api_url.rstrip("/") + "/Library/Refresh"
        headers = {"X-Emby-Token": api_key}
        r = requests.post(refresh_url, headers=headers, timeout=10)
        if r.status_code in (200, 204):
            logging.info(f"Triggered Emby library refresh via {refresh_url}")
        else:
            logging.warning(f"Emby refresh failed: {r.status_code} - {r.text} ({refresh_url})")
    except Exception as e:
        logging.error(f"Emby refresh error: {e}", exc_info=True)


def write_excluded_report(path: Path, excluded, allowed_count: int, enabled: bool):
    if not enabled:
        logging.info("Excluded report skipped (write_non_us_report = false)")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    movies = [e.raw_title for e in excluded if e.category == Category.MOVIE]
    shows = [e.raw_title for e in excluded if e.category == Category.TVSHOW]
    grouped_shows = defaultdict(list)
    for title in shows:
        base = re.sub(r"[sS]\d{1,2}\s*[eE]\d{1,2}.*", "", title).strip()
        grouped_shows[base].append(title)
    with path.open("w", encoding="utf-8") as f:
        f.write("=== Excluded Entries Report ===\n\n")
        f.write(f"Total allowed: {allowed_count}\n")
        f.write(f"Total excluded: {len(excluded)}\n\n")
        f.write("--- Movies ---\n")
        for m in sorted(movies):
            f.write(f"{m}\n")
        f.write(f"\nTotal movies excluded: {len(movies)}\n\n")
        f.write("--- TV Shows ---\n")
        for base, eps in sorted(grouped_shows.items()):
            f.write(f"{base} — {len(eps)} episodes excluded\n")
        f.write(f"\nTotal shows excluded: {len(grouped_shows)}\n")
        f.write("=== End of Report ===\n")
    logging.info(f"Excluded entries written: {path}")


def run_pipeline(force_regenerate=False):
    cfg = config.load_config(Path(__file__).parent / "config.json")
    
    # Initialize progress tracking
    try:
        verbosity = VerbosityLevel(cfg.verbosity.lower())
    except ValueError:
        verbosity = VerbosityLevel.NORMAL
        logging.warning(f"Invalid verbosity level '{cfg.verbosity}', using 'normal'")
    
    progress_tracker = ProgressTracker(verbosity=verbosity)
    
    # Initialize progress display
    try:
        progress_display = UserProgressDisplay(progress_tracker)
    except Exception:
        # Fall back to simple display if tqdm fails
        progress_display = SimpleProgressDisplay(progress_tracker)
    
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(str(cfg.log_file), mode="a", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    if logger.hasHandlers():
        logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    m3u_path = cfg.m3u
    output_dir = cfg.output_dir
    db_path = cfg.sqlite_cache_file
    ignore_keywords = cfg.ignore_keywords or {}
    write_non_us_report = cfg.write_non_us_report
    
    # Phase 1: Scanning Local Media
    with progress_tracker.phase_context(ProgressPhase.SCANNING_LOCAL):
        progress_tracker.start_phase(ProgressPhase.SCANNING_LOCAL)
        
        # Check for shutdown request
        if progress_tracker.is_shutdown_requested():
            logging.info("Shutdown requested during local media scan, exiting...")
            return
            
        cache = SQLiteCache(db_path)
        existing = {}
        for d in cfg.existing_media_dirs:
            existing.update(build_existing_media_cache(Path(d)))
        cache.replace_existing_media(existing)
        existing_keys = set(existing.keys())
        progress_tracker.update_stats(
            movies_found=sum(1 for k, v in existing.items() if v == "MOVIE"),
            tv_episodes_found=sum(1 for k, v in existing.items() if v == "TVEPISODE"),
            documentaries_found=sum(1 for k, v in existing.items() if v == "DOCUMENTARY")
        )
    # Phase 2: Parsing M3U Playlist
    with progress_tracker.phase_context(ProgressPhase.PARSING_M3U):
        progress_tracker.start_phase(ProgressPhase.PARSING_M3U, total_items=0)  # We don't know the count yet
        
        # Check for shutdown request
        if progress_tracker.is_shutdown_requested():
            logging.info("Shutdown requested during M3U parsing, exiting...")
            return
            
        entries = parse_m3u(
            m3u_path,
            tv_keywords=cfg.tv_group_keywords,
            doc_keywords=cfg.doc_group_keywords,
            movie_keywords=cfg.movie_group_keywords,
            replay_keywords=cfg.replay_group_keywords,
            ignore_keywords=cfg.ignore_keywords,
        )
        
        # Count entries by category
        movie_count = sum(1 for e in entries if e.category == Category.MOVIE)
        tv_count = sum(1 for e in entries if e.category == Category.TVSHOW)
        doc_count = sum(1 for e in entries if e.category == Category.DOCUMENTARY)
        replay_count = sum(1 for e in entries if e.category == Category.REPLAY)
        
        progress_tracker.update_stats(
            movies_found=movie_count,
            tv_episodes_found=tv_count,
            documentaries_found=doc_count
        )
        
        # Deduplicate entries
        unique_entries = {}
        for e in entries:
            if e.category == Category.MOVIE:
                key = canonical_movie_key(e.raw_title)
            elif e.category == Category.TVSHOW:
                m = re.search(r"[sS](\d{1,2})\s*[eE](\d{1,2})", e.raw_title)
                if m:
                    season, episode = int(m.group(1)), int(m.group(2))
                    base = re.sub(r"[sS]\d{1,2}\s*[eE]\d{1,2}.*", "", e.raw_title).strip()
                    key = canonical_tv_key(base, season, episode)
                else:
                    key = make_cache_key(e.raw_title)
            elif e.category == Category.DOCUMENTARY:
                key = canonical_movie_key(e.raw_title)
            else:
                key = make_cache_key(e.raw_title)
            unique_entries[key] = e
        
        entries = list(unique_entries.values())
        progress_tracker.update_phase(ProgressPhase.PARSING_M3U, len(entries), f"Parsed {len(entries)} unique entries")
        logging.info("Deduplicated playlist entries: %d -> %d unique", len(entries), len(unique_entries))
    strm_cache = cache.strm_cache_dict()
    logging.debug("Loaded %d entries from strm_cache", len(strm_cache))
    to_check = []
    reused_allowed = []
    reused_excluded = []
    for e in entries:
        key = None
        if e.category == Category.MOVIE:
            key = canonical_movie_key(e.raw_title)
        elif e.category == Category.TVSHOW:
            m = re.search(r"[sS](\d{1,2})\s*[eE](\d{1,2})", e.raw_title)
            if m:
                season, episode = int(m.group(1)), int(m.group(2))
                base = re.sub(r"[sS]\d{1,2}\s*[eE]\d{1,2}.*", "", e.raw_title).strip()
                key = canonical_tv_key(base, season, episode)
            else:
                key = make_cache_key(e.raw_title)
        elif e.category == Category.DOCUMENTARY:
            key = canonical_movie_key(e.raw_title)
        else:
            key = make_cache_key(e.raw_title)
        if key in existing_keys:
            reused_allowed.append(e)
            logging.debug(f"Reusing local-existing result for {e.raw_title}")
            continue
        cached = strm_cache.get(key)
        if cached and cached.get("allowed") is not None:
            if cached["allowed"] == 1:
                reused_allowed.append(e)
                logging.debug(f"Reusing cached allowed result for {e.raw_title}")
            else:
                reused_excluded.append(e)
                logging.debug(f"Reusing cached excluded result for {e.raw_title}")
        else:
            logging.debug("CACHE MISS: raw_title=%r key=%s cached_entry=%s", e.raw_title, key, strm_cache.get(key))
            to_check.append(e)
    # Phase 3: TMDb Filtering
    with progress_tracker.phase_context(ProgressPhase.FILTERING_TMDB):
        progress_tracker.start_phase(ProgressPhase.FILTERING_TMDB, total_items=len(to_check))
        
        # Check for shutdown request
        if progress_tracker.is_shutdown_requested():
            logging.info("Shutdown requested during TMDb filtering, exiting...")
            return
        
        allowed, excluded = split_by_market_filter(
            to_check,
            allowed_movie_countries=cfg.allowed_movie_countries,
            allowed_tv_countries=cfg.allowed_tv_countries,
            api_key=cfg.tmdb_api,
            max_workers=cfg.max_workers,
            ignore_keywords=cfg.ignore_keywords,
        )
        
        # Update statistics with filtering results
        allowed.extend(reused_allowed)
        excluded.extend(reused_excluded)
        
        # Count results by category
        allowed_movies = sum(1 for e in allowed if e.category == Category.MOVIE)
        allowed_tv = sum(1 for e in allowed if e.category == Category.TVSHOW)
        allowed_docs = sum(1 for e in allowed if e.category == Category.DOCUMENTARY)
        
        excluded_movies = sum(1 for e in excluded if e.category == Category.MOVIE)
        excluded_tv = sum(1 for e in excluded if e.category == Category.TVSHOW)
        excluded_docs = sum(1 for e in excluded if e.category == Category.DOCUMENTARY)
        
        progress_tracker.update_stats(
            movies_allowed=allowed_movies,
            movies_excluded=excluded_movies,
            tv_episodes_allowed=allowed_tv,
            tv_episodes_excluded=excluded_tv,
            documentaries_allowed=allowed_docs,
            documentaries_excluded=excluded_docs
        )
        
        progress_tracker.update_phase(ProgressPhase.FILTERING_TMDB, len(to_check), 
                                    f"Filtered {len(allowed)} allowed, {len(excluded)} excluded")
    
    write_excluded_report(output_dir / "excluded_entries.txt", excluded, len(allowed), write_non_us_report)
    existing_keys = set(existing.keys())
    strm_cache = cache.strm_cache_dict()
    new_cache = strm_cache.copy()
    written_count = 0
    skipped_count = 0

    def process_entry(e):
        nonlocal written_count, skipped_count
        key = None
        rel_path = None
        logging.debug(
            "PROCESS START: raw_title=%r, safe_title=%r, category=%s, year=%s, url=%s",
            getattr(e, "raw_title", None),
            getattr(e, "safe_title", None),
            getattr(e, "category", None),
            getattr(e, "year", None),
            getattr(e, "url", None),
        )
        if not e.year:
            e.year = extract_year(e.raw_title)
            if e.year:
                logging.debug("Extracted year=%s from raw_title %r", e.year, e.raw_title)
        ignore = ignore_keywords.get("tvshows" if e.category == Category.TVSHOW else "movies", [])
        if any(word.lower() in e.raw_title.lower() for word in ignore):
            logging.debug("Ignored by keyword: %s", e.raw_title)
            return
        try:
            if e.category == Category.MOVIE:
                key = canonical_movie_key(e.raw_title)
                logging.debug(f"Key built for {e.raw_title} (MOVIE): {key}")
                rel_path = movie_strm_path(output_dir, e)
            elif e.category == Category.TVSHOW:
                base = re.sub(r"[sS]\d{1,2}\s*[eE]\d{1,2}.*", "", e.raw_title).strip()
                m = re.search(r"[sS](\d{1,2})\s*[eE](\d{1,2})", e.raw_title)
                if m:
                    season, episode = int(m.group(1)), int(m.group(2))
                    key = canonical_tv_key(base, season, episode)
                    logging.debug(f"Key built for {e.raw_title} (TVSHOW S{season:02d}E{episode:02d}): {key}")
                    rel_path = tv_strm_path(
                        output_dir,
                        VODEntry(
                            raw_title=base,
                            safe_title=sanitize_title(base),
                            url=e.url,
                            category=e.category,
                            year=e.year,
                        ),
                        season,
                        episode,
                    )
                else:
                    key = make_cache_key(e.raw_title)
                    logging.debug(f"Key built for {e.raw_title} (TVSHOW no S/E): {key}")
                    rel_path = tv_strm_path(output_dir, e, 1, 1)
            elif e.category == Category.DOCUMENTARY:
                key = canonical_movie_key(e.raw_title)
                logging.debug(f"Key built for {e.raw_title} (DOC): {key}")
                rel_path = doc_strm_path(output_dir, e)
            else:
                logging.warning("Unknown category %s for entry %r", e.category, e.raw_title)
                return
            if not key:
                logging.error("No cache key generated for %r", e.raw_title)
                return
            abs_path = rel_path
            url = e.url
            if key in existing_keys:
                skipped_count += 1
                logging.debug("Skip existing media: %s", e.raw_title)
                new_cache[key] = {"url": e.url, "path": None, "allowed": 1}
                return
            # Skip cache check if force_regenerate is enabled
            if not force_regenerate:
                cached = strm_cache.get(key)
                if cached:
                    cached_path = Path(cached.get("path") or "").resolve() if cached.get("path") else None
                    if cached.get("url") == url and cached.get("path") and cached_path == abs_path.resolve():
                        skipped_count += 1
                        logging.debug("Skip cached (unchanged): %s", e.raw_title)
                        new_cache[key] = {
                            "url": cached.get("url"),
                            "path": cached.get("path"),
                            "allowed": cached.get("allowed", 1),
                        }
                        return
            write_strm_file(output_dir, rel_path, url)
            new_cache[key] = {"url": url, "path": str(abs_path.resolve()), "allowed": 1}
            written_count += 1
            logging.info("STRM written: %s", abs_path)
        except Exception as ex:
            logging.error(
                "Error processing entry %r (category=%s, year=%s): %s",
                e.raw_title,
                getattr(e, "category", None),
                getattr(e, "year", None),
                ex,
                exc_info=True,
            )

    # Phase 4: Creating STRM Files
    with progress_tracker.phase_context(ProgressPhase.CREATING_STRM):
        progress_tracker.start_phase(ProgressPhase.CREATING_STRM, total_items=len(allowed))
        
        # Pre-compute all file operations for batch processing
        file_operations = []
        batch_size = 50  # Process files in batches of 50
        written_count = 0
        skipped_count = 0
        
        # First pass: determine which files need to be created
        for e in allowed:
            key = None
            rel_path = None
            try:
                if e.category == Category.MOVIE:
                    key = canonical_movie_key(e.raw_title)
                    rel_path = movie_strm_path(output_dir, e)
                elif e.category == Category.TVSHOW:
                    base = re.sub(r"[sS]\d{1,2}\s*[eE]\d{1,2}.*", "", e.raw_title).strip()
                    m = re.search(r"[sS](\d{1,2})\s*[eE](\d{1,2})", e.raw_title)
                    if m:
                        season, episode = int(m.group(1)), int(m.group(2))
                        key = canonical_tv_key(base, season, episode)
                        rel_path = tv_strm_path(
                            output_dir,
                            VODEntry(
                                raw_title=base,
                                safe_title=sanitize_title(base),
                                url=e.url,
                                category=e.category,
                                year=e.year,
                            ),
                            season,
                            episode,
                        )
                    else:
                        key = make_cache_key(e.raw_title)
                        rel_path = tv_strm_path(output_dir, e, 1, 1)
                elif e.category == Category.DOCUMENTARY:
                    key = canonical_movie_key(e.raw_title)
                    rel_path = doc_strm_path(output_dir, e)
                else:
                    continue
                
                if not key:
                    continue
                
                # Check if already exists or cached
                if key in existing_keys or (not force_regenerate and key in strm_cache):
                    skipped_count += 1
                    continue
                
                # Add to batch operations
                file_operations.append((rel_path, e.url, key, e))
                
            except Exception as ex:
                progress_tracker.add_error(f"Error processing {e.raw_title}: {str(ex)}")
        
        # Process files in optimized batches
        for i in range(0, len(file_operations), batch_size):
            batch = file_operations[i:i + batch_size]
            
            # Extract just the paths and URLs for batch processing
            batch_ops = [(rel_path, url) for rel_path, url, key, entry in batch]
            
            # Process batch
            batch_written, batch_skipped = batch_write_strm_files(output_dir, batch_ops)
            written_count += batch_written
            skipped_count += batch_skipped
            
            # Update cache for successfully written files
            for rel_path, url, key, entry in batch:
                abs_path = output_dir / rel_path
                new_cache[key] = {"url": url, "path": str(abs_path.resolve()), "allowed": 1}
            
            # Update progress (less frequent updates for better performance)
            current_processed = min(i + batch_size, len(file_operations))
            progress_tracker.batch_update_phase(
                ProgressPhase.CREATING_STRM, 
                current_processed + skipped_count,
                f"Batch {i//batch_size + 1}/{(len(file_operations)-1)//batch_size + 1}",
                success_count=batch_written,
                skipped_count=batch_skipped
            )
            
            # Update statistics
            movie_count = sum(1 for _, _, _, entry in batch if entry.category == Category.MOVIE)
            tv_count = sum(1 for _, _, _, entry in batch if entry.category == Category.TVSHOW)
            doc_count = sum(1 for _, _, _, entry in batch if entry.category == Category.DOCUMENTARY)
            
            progress_tracker.update_stats(
                strm_created=batch_written,
                strm_skipped=batch_skipped
            )
        
        # Process excluded entries
        for e in excluded:
            if e.category in (Category.MOVIE, Category.DOCUMENTARY):
                key = canonical_movie_key(e.raw_title)
            elif e.category == Category.TVSHOW:
                m = re.search(r"[sS](\d{1,2})\s*[eE](\d{1,2})", e.raw_title)
                if m:
                    season, episode = int(m.group(1)), int(m.group(2))
                    base = re.sub(r"[sS]\d{1,2}\s*[eE]\d{1,2}.*", "", e.raw_title).strip()
                    key = canonical_tv_key(base, season, episode)
                else:
                    key = make_cache_key(e.raw_title)
            else:
                key = make_cache_key(e.raw_title)
            new_cache[key] = {"url": e.url, "path": None, "allowed": 0}
        
        progress_tracker.update_phase(ProgressPhase.CREATING_STRM, len(allowed), 
                                    f"Created {written_count} STRMs, skipped {skipped_count}")
    
    cache.replace_strm_cache(new_cache)
    
    # Phase 5: Cleanup & Finalization
    with progress_tracker.phase_context(ProgressPhase.CLEANUP):
        progress_tracker.start_phase(ProgressPhase.CLEANUP)
        logging.info("Cleaning up orphan STRMs...")
        cleanup_strm_tree(output_dir, new_cache)
        
        # Count orphaned files (this would need to be tracked in cleanup_strm_tree)
        progress_tracker.update_phase(ProgressPhase.CLEANUP, 1, "Cleanup completed")
        
        if not cfg.dry_run and getattr(cfg, "emby_api_url", None) and getattr(cfg, "emby_api_key", None):
            logging.info("Triggering Emby library refresh...")
            touch_emby(cfg.emby_api_url, cfg.emby_api_key)
        else:
            logging.info("Skipping Emby refresh (either dry_run or not configured)")
    
    # Show final summary
    progress_display.show_final_summary()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="M3U to STRM converter")
    parser.add_argument(
        "--force-regenerate",
        action="store_true",
        help="Force regeneration of all STRM files, skipping cache checks",
    )
    args = parser.parse_args()
    run_pipeline(force_regenerate=args.force_regenerate)
