"""Database initialization script"""

import asyncio
import sys
import os

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from src.beaver_storage.database import create_tables, drop_tables
from src.beaver_storage.models import *  # Import all models


async def init_database():
    """Initialize the database"""
    print("Creating database tables...")
    await create_tables()
    print("Database tables created!")


async def reset_database():
    """Reset the database"""
    print("Dropping all tables...")
    await drop_tables()
    print("Creating tables...")
    await create_tables()
    print("Database reset complete!")

async def update_database():
    print("Updating database tables...")
    from sqlalchemy import MetaData, text
    from src.beaver_storage.database import Base, async_engine
    async with async_engine.begin() as conn:
        def _update(sync_conn):
            current = MetaData()
            current.reflect(bind=sync_conn)
            target = Base.metadata
            dialect = sync_conn.dialect.name
            for name, target_table in target.tables.items():
                if name not in current.tables:
                    target_table.create(bind=sync_conn)
                    continue
                curr_table = current.tables[name]
                needs_rebuild = False
                for col in target_table.columns:
                    cur_col = curr_table.columns.get(col.name)
                    if cur_col is None:
                        needs_rebuild = True
                        break
                    if str(cur_col.type) != str(col.type) or bool(cur_col.nullable) != bool(col.nullable):
                        if dialect == "postgresql" and str(cur_col.type) == str(col.type) and col.nullable and not cur_col.nullable:
                            sync_conn.execute(text(f'ALTER TABLE "{name}" ALTER COLUMN "{col.name}" DROP NOT NULL'))
                            continue
                        if dialect == "mysql" and str(cur_col.type) == str(col.type) and col.nullable != cur_col.nullable:
                            type_sql = col.type.compile(sync_conn.dialect)
                            null_sql = "NULL" if col.nullable else "NOT NULL"
                            sync_conn.execute(text(f'ALTER TABLE `{name}` MODIFY COLUMN `{col.name}` {type_sql} {null_sql}'))
                            continue
                        needs_rebuild = True
                        break
                if needs_rebuild:
                    if dialect == "sqlite":
                        sync_conn.execute(text("PRAGMA foreign_keys=OFF"))
                    temp_name = f"{name}_tmp_update"
                    new_meta = MetaData()
                    for t in target.tables.values():
                        if t.name == name:
                            t.to_metadata(new_meta, name=temp_name)
                        else:
                            t.to_metadata(new_meta)
                    new_meta.tables[temp_name].create(bind=sync_conn)
                    common = [c.name for c in target_table.columns if c.name in curr_table.columns]
                    if common:
                        cols = ", ".join([f'"{c}"' if dialect=="postgresql" else c for c in common])
                        sync_conn.execute(text(f'INSERT INTO {temp_name} ({cols}) SELECT {cols} FROM {name}'))
                    sync_conn.execute(text(f'DROP TABLE {name}'))
                    sync_conn.execute(text(f'ALTER TABLE {temp_name} RENAME TO {name}'))
                    if dialect == "sqlite":
                        sync_conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(_update)
    print("Database update complete!")


if __name__ == "__main__":
    import argparse
        
    parser = argparse.ArgumentParser(description="Database management tool")
    parser.add_argument("--reset", action="store_true", help="Reset the database")
    parser.add_argument("--update", action="store_true", help="Update the database (preserve data)")
    args = parser.parse_args()
    
    if args.reset:
        asyncio.run(reset_database())
    elif args.update:
        asyncio.run(update_database())
    else:
        asyncio.run(init_database())