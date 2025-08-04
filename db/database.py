from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import ParamSpec, TypeVar, Callable, Coroutine, Any, cast

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

from core import settings

SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL.replace(
    "postgresql://", "postgresql+asyncpg://"
).replace("sqlite://", "sqlite+aiosqlite://")

engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    **(
        dict(pool_recycle=900, pool_size=100, max_overflow=3)
        if "sqlite" not in SQLALCHEMY_DATABASE_URL
        else {}
    ),
)

SessionLocal = async_sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)

Base = declarative_base()
P = ParamSpec("P")
T = TypeVar("T")


def require_session():
    session = db_session_var.get()
    assert session is not None, "Session context is not provided"
    return session


def transaction():
    def wrapper(
            cb: Callable[P, Coroutine[Any, Any, T]]
    ) -> Callable[P, Coroutine[Any, Any, T]]:
        @wraps(cb)
        async def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
            if db_session_var.get() is not None:
                return await cb(*args, **kwargs)

            async with cast(AsyncSession, SessionLocal()) as session:
                with use_context_value(db_session_var, session):
                    result = await cb(*args, **kwargs)
                    await session.commit()
                    return result

        return wrapped

    return wrapper


@contextmanager
def use_context_value(context: ContextVar[T], value: T):
    reset = context.set(value)
    try:
        yield
    finally:
        context.reset(reset)


db_session_var: ContextVar[AsyncSession | None] = ContextVar(
    "db_session_var", default=None
)
