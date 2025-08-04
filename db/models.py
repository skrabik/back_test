import datetime
import uuid

from sqlalchemy import BigInteger, DateTime, func, String, Boolean, false, null, Float, ForeignKey, UUID, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Mapped, mapped_column, relationship

from endpoint.models import MoneyCurrencyLiteral, MoneyNetworkLiteral, MoneyPaymentMethodLiteral, \
    OperationTypeLiteral

Base = declarative_base()


class ModelBase(Base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True, autoincrement=True, unique=True)
    time_created: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    time_updated: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)


class User(ModelBase):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False, index=True, unique=True)
    nickname: Mapped[str | None] = mapped_column(String, nullable=True)
    full_name: Mapped[str] = mapped_column(String)
    avatar: Mapped[str | None] = mapped_column(String, nullable=True)

    is_admin: Mapped[bool] = mapped_column(Boolean, server_default=false())
    ref_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    balance: Mapped[float] = mapped_column(Float, server_default="0")
    balance_usdt: Mapped[float] = mapped_column(Float, server_default="0")
    wins: Mapped[int] = mapped_column(BigInteger, server_default="0")

    logo_game_start_time: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), server_default=null())

    users_games: Mapped[list["UsersGames"]] = relationship(back_populates="user")
    users_referrals: Mapped[list["UserReferral"]] = relationship(
        back_populates="user",
        foreign_keys="[UserReferral.user_id]"
    )

    finance_operations: Mapped[list["FinanceOperation"]] = relationship(back_populates="user")
    stars_payments: Mapped[list["StarsPayment"]] = relationship(back_populates="user")


class Game(ModelBase):
    __tablename__ = 'games'

    date_game: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), server_default=null(), nullable=True)
    course: Mapped[float | None] = mapped_column(Float, nullable=True, server_default=null())
    course_at_computed: Mapped[float | None] = mapped_column(Float, nullable=True, server_default=null())
    is_computed: Mapped[bool] = mapped_column(Boolean, server_default=false())

    users_games: Mapped[list["UsersGames"]] = relationship(back_populates="game")


class UsersGames(ModelBase):
    __tablename__ = 'users_games_m2m'

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id', ondelete="CASCADE"))
    game_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('games.id', ondelete="CASCADE"))

    total_rate: Mapped[float] = mapped_column(Float, server_default="0")
    win_total_rate: Mapped[float | None] = mapped_column(Float, server_default=null())
    currency: Mapped[str] = mapped_column(String, nullable=False)  # "usdt" and "words"

    choose: Mapped[str] = mapped_column(String, nullable=False)  # "yes" and "no"

    user: Mapped["User"] = relationship(back_populates="users_games")
    game: Mapped["Game"] = relationship(back_populates="users_games")


class UserReferral(ModelBase):
    __tablename__ = 'users_referrals'

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id', ondelete="CASCADE"))
    user_game_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey('users_games_m2m.id', ondelete="CASCADE"), nullable=True)
    ref_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id', ondelete="CASCADE"))

    amount: Mapped[float] = mapped_column(Float, server_default="0")
    currency: Mapped[str] = mapped_column(String, nullable=False)

    user: Mapped["User"] = relationship(
        back_populates="users_referrals",
        foreign_keys="[UserReferral.user_id]"
    )


class FinanceOperation(ModelBase):
    __tablename__ = 'finance_operations'

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id', ondelete="NO ACTION"))

    amount: Mapped[float] = mapped_column(Float)

    operation_type: Mapped[OperationTypeLiteral] = mapped_column(String)
    currency: Mapped[MoneyCurrencyLiteral] = mapped_column(String)

    network: Mapped[MoneyNetworkLiteral | None] = mapped_column(String, nullable=True)
    payment_method: Mapped[MoneyPaymentMethodLiteral | None] = mapped_column(String, nullable=True)

    is_success: Mapped[bool] = mapped_column(Boolean, server_default=false())

    card_number: Mapped[str | None] = mapped_column(String, nullable=True)
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    from_ip: Mapped[str | None] = mapped_column(String, nullable=True)

    user: Mapped["User"] = relationship(back_populates="finance_operations")


class StarsPayment(ModelBase):
    __tablename__ = 'stars_payments'

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id', ondelete="NO ACTION"))

    amount_stars: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_usdt: Mapped[float] = mapped_column(Float, nullable=False)

    telegram_payment_charge_id: Mapped[str] = mapped_column(String, nullable=False)

    user: Mapped["User"] = relationship(back_populates="stars_payments")
