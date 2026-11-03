"""
(Re)create the Sparkify database and its star-schema tables.

WARNING: this drops the existing database (DB_NAME) and all of its data.
"""
import psycopg2
from psycopg2 import sql

import config
from sql_queries import create_table_queries, drop_table_queries


def create_database():
    """Drop and recreate the target database, then return a connection to it."""
    admin_conn = psycopg2.connect(config.dsn(config.DB_ADMIN_DB))
    admin_conn.autocommit = True
    try:
        with admin_conn.cursor() as cur:
            db = sql.Identifier(config.DB_NAME)
            cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(db))
            cur.execute(
                sql.SQL("CREATE DATABASE {} WITH ENCODING 'utf8' TEMPLATE template0").format(db)
            )
    finally:
        admin_conn.close()

    return psycopg2.connect(config.dsn())


def drop_tables(cur):
    """Drop every table listed in `drop_table_queries`."""
    for query in drop_table_queries:
        cur.execute(query)


def create_tables(cur):
    """Create every table listed in `create_table_queries`."""
    for query in create_table_queries:
        cur.execute(query)


def main():
    conn = create_database()
    try:
        with conn, conn.cursor() as cur:  # commits on success, rolls back on error
            drop_tables(cur)
            create_tables(cur)
        print(f"Database '{config.DB_NAME}' and tables created.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
