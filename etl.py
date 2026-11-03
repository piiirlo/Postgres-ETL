"""
ETL pipeline: load Sparkify song and event-log JSON files into PostgreSQL.

1. Song files  -> artists, songs            (dimension tables)
2. Log files   -> time, users               (dimension tables)
                  songplays                 (fact table)

Run `create_tables.py` first to create the schema.
"""
import glob
import os
import time

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

import config
from sql_queries import (
    artist_table_insert,
    song_lookup_select,
    song_table_insert,
    songplay_table_insert,
    time_table_insert,
    user_table_insert,
)

SONG_DATA_DIR = os.path.join("data", "song_data")
LOG_DATA_DIR = os.path.join("data", "log_data")

# Durations are floats; round before matching log events to songs.
DURATION_PRECISION = 5


def get_files(root):
    """Return every *.json file under `root`, sorted so logs load in date order."""
    return sorted(glob.glob(os.path.join(root, "**", "*.json"), recursive=True))


def to_records(df):
    """Convert a DataFrame to a list of tuples of plain Python values (NaN -> None)."""
    df = df.astype(object).where(df.notna(), None)
    return list(df.itertuples(index=False, name=None))


def bulk_insert(cur, query, df):
    """Insert all rows of `df` with a single multi-row INSERT."""
    if not df.empty:
        execute_values(cur, query, to_records(df))


# --------------------------------------------------------------------------- #
# Song data
# --------------------------------------------------------------------------- #
def process_song_files(cur, filepaths):
    """Load every song file into the `artists` and `songs` tables."""
    df = pd.concat((pd.read_json(f, lines=True) for f in filepaths), ignore_index=True)

    artists = (
        df[["artist_id", "artist_name", "artist_location", "artist_latitude", "artist_longitude"]]
        .drop_duplicates("artist_id")
    )
    songs = (
        df[["song_id", "title", "artist_id", "year", "duration"]]
        .drop_duplicates("song_id")
        .copy()
    )
    songs["year"] = songs["year"].astype("Int64").mask(songs["year"] == 0)  # 0 = unknown

    bulk_insert(cur, artist_table_insert, artists)  # artists first: songs reference them
    bulk_insert(cur, song_table_insert, songs)
    return len(artists), len(songs)


# --------------------------------------------------------------------------- #
# Log data
# --------------------------------------------------------------------------- #
def load_song_lookup(cur):
    """Return {(title, artist_name, duration): (song_id, artist_id)} from the database."""
    cur.execute(song_lookup_select)
    return {
        (title, name, round(duration, DURATION_PRECISION)): (song_id, artist_id)
        for title, name, duration, song_id, artist_id in cur.fetchall()
    }


def process_log_file(cur, filepath, song_lookup):
    """Load one event-log file into the `time`, `users` and `songplays` tables."""
    df = pd.read_json(filepath, lines=True)

    # Only song-play events matter for analytics.
    df = df[df["page"] == "NextSong"].copy()
    df["user_id"] = pd.to_numeric(df["userId"], errors="coerce")
    df = df.dropna(subset=["user_id"])
    if df.empty:
        return 0
    df["user_id"] = df["user_id"].astype(int)

    # `ts` is a Unix epoch in milliseconds.
    df["start_time"] = pd.to_datetime(df["ts"], unit="ms")
    df = df.sort_values("start_time")

    # time dimension
    t = df["start_time"].drop_duplicates()
    time_df = pd.DataFrame({
        "start_time": t,
        "hour": t.dt.hour,
        "day": t.dt.day,
        "week": t.dt.isocalendar().week.astype(int),
        "month": t.dt.month,
        "year": t.dt.year,
        "weekday": t.dt.day_of_week,  # Monday = 0
    })
    bulk_insert(cur, time_table_insert, time_df)

    # users dimension: keep each user's latest record so `level` reflects upgrades
    users = (
        df[["user_id", "firstName", "lastName", "gender", "level"]]
        .drop_duplicates("user_id", keep="last")
    )
    bulk_insert(cur, user_table_insert, users)

    # songplays fact: resolve song/artist ids from the in-memory lookup
    keys = zip(df["song"], df["artist"], df["length"].round(DURATION_PRECISION))
    matches = [song_lookup.get(k, (None, None)) for k in keys]
    df["song_id"] = [m[0] for m in matches]
    df["artist_id"] = [m[1] for m in matches]

    songplays = df[["start_time", "user_id", "level", "song_id", "artist_id",
                    "sessionId", "location", "userAgent"]]
    bulk_insert(cur, songplay_table_insert, songplays)
    return len(songplays)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def main():
    started = time.perf_counter()
    conn = psycopg2.connect(config.dsn())
    try:
        with conn.cursor() as cur:
            song_files = get_files(SONG_DATA_DIR)
            print(f"{len(song_files)} song files found in {SONG_DATA_DIR}")
            n_artists, n_songs = process_song_files(cur, song_files)
            conn.commit()
            print(f"  loaded {n_artists} artists, {n_songs} songs")

            song_lookup = load_song_lookup(cur)

            log_files = get_files(LOG_DATA_DIR)
            print(f"{len(log_files)} log files found in {LOG_DATA_DIR}")
            total_events = 0
            for i, path in enumerate(log_files, 1):
                try:
                    total_events += process_log_file(cur, path, song_lookup)
                    conn.commit()  # one transaction per file
                except Exception:
                    conn.rollback()
                    print(f"  failed on {path}")
                    raise
                print(f"  {i}/{len(log_files)} log files processed", end="\r")
            print()
            print(f"  processed {total_events} song-play events")
    finally:
        conn.close()
    print(f"ETL finished in {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    main()
