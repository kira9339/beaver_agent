"""Database connection configuration"""

import os
from typing import AsyncGenerator
from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from config.settings import settings

from sqlalchemy.orm import declarative_base

# SQLAlchemy Base
Base = declarative_base()

# Metadata
metadata = MetaData()

# Database engine
engine = create_engine(
    settings.database.url,
    echo=settings.database.echo,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database.url else {}
)

# Async database engine
async_engine = create_async_engine(
    settings.database.async_url,
    echo=settings.database.echo
)

# Session factories
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
AsyncSessionLocal = async_sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False
)


def get_db():
    """Get database session (synchronous)"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session (asynchronous)"""
    session = AsyncSessionLocal()
    try:
        yield session
        # Ensure transaction is committed correctly
        if session.in_transaction():
            await session.commit()
    except Exception as e:
        # Rollback transaction on exception
        if session.in_transaction():
            await session.rollback()
        raise
    finally:
        # Ensure session is closed properly
        try:
            await session.close()
        except Exception:
            # Ignore errors on close to avoid state conflicts
            pass


async def create_tables():
    """Create all tables"""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_tables():
    """Drop all tables"""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)