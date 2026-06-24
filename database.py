from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    BOT_TOKEN: str
    DATABASE_URL: str
    SUPER_ADMIN_ID: int
    ORG_NAME: str = "ООО \"TO'PALANG HPD HOLDING\""
    ORG_OBJECT: str = ""
    GEMINI_API_KEY: str = ""

settings = Settings()

def _fix(url):
    if url.startswith("postgres://"):      return url.replace("postgres://","postgresql+asyncpg://",1)
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        return url.replace("postgresql://","postgresql+asyncpg://",1)
    return url

class Base(DeclarativeBase): pass

engine  = create_async_engine(_fix(settings.DATABASE_URL), pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def init_db():
    import models  # noqa
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
