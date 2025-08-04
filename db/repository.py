import logging
import typing
import uuid
from datetime import UTC
from datetime import datetime, timedelta
from typing import Dict

from aiogram import Bot
from aiogram.types import LabeledPrice
from fastapi import HTTPException
from sqlalchemy import select, Sequence, func, update
from sqlalchemy.orm import selectinload

from core import get_user_profile_photo, set_user_rating, redis, settings, get_token_price
from core._constants import STARS_USDT_PRICE
from db.database import transaction, require_session
from db.models import User, Game, UsersGames, UserReferral, FinanceOperation, StarsPayment
from endpoint.models import AdminSetDateGames, GameBet, CurrencyLiteral, Tasks, TypeTasks, ChoiceLiteral, \
    GameStatLiteral, AccountOperationWithdrawRequest, OperationTypeLiteral, AccountOperationDepositRequest
from utils.currency import get_usdt_uzs, get_usdt_rub
from utils.get_token_price import get_token_price as gtp
from utils.tasks import tasks, rewards_for_daily, tasks_json
from utils.time_until_next_day import seconds_until_tomorrow, seconds_until_day_after_tomorrow


class UsersRepository:

    @staticmethod
    @transaction()
    async def complete_task(user_id: int, task_id: int):
        task = await TaskRepository.get_by_id(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")

        if task.type == "daily":
            await UsersRepository.incr_user_daily_task_day(user_id)
        elif task.type == "channel":
            await UsersRepository.complete_channel_task(user_id, task_id)
        elif task.type == "link":
            await UsersRepository.complete_link_task(user_id, task_id)

    @staticmethod
    async def check_subscribe_user(user_id: int, chat_id: int | str, token: str = settings.TG_BOT_TOKEN):
        bot = Bot(token=token)
        try:
            data = await bot.get_chat_member(chat_id, user_id)
            return data.status not in {"left", "kicked"}
        except:
            return True

    @staticmethod
    @transaction()
    async def get_previous_game_wins(user_id: int) -> Dict[CurrencyLiteral, float] | None:
        previous_game = await GameRepository.get_previous_game()
        if not previous_game or not previous_game.is_computed:
            return {}

        # прошло больше 15 секунд -> не отдаём ничего
        current_time = datetime.now(UTC)
        if previous_game.date_game is None or current_time > (previous_game.date_game + timedelta(seconds=15)):
            return {}

        user_games = await GameRepository.get_bets_by_user_and_game_id(user_id, previous_game.id)
        if not user_games:
            return {}

        game_result = {}
        for bet in user_games:
            game_result[bet.currency] = game_result.get(bet.currency, 0) + bet.win_total_rate

        return game_result

    @staticmethod
    @transaction()
    async def complete_channel_task(user_id: int, task_id: int):
        if await redis.exists(f"user:{user_id}:task:{task_id}:complete"):
            raise HTTPException(status_code=404, detail="Task already completed")

        task = await TaskRepository.get_by_id(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")

        if task.channel_id is None:
            raise HTTPException(status_code=404, detail="Channel is not set")

        if await UsersRepository.check_subscribe_user(user_id, task.channel_id):
            user = await UsersRepository.get_or_raise_by_id(user_id)
            user.balance += task.value

            await redis.set(f"user:{user_id}:task:{task_id}:complete", 1)

    @staticmethod
    @transaction()
    async def complete_link_task(user_id: int, task_id: int):
        if await redis.exists(f"user:{user_id}:task:{task_id}:complete"):
            raise HTTPException(status_code=404, detail="Task already completed")

        task = await TaskRepository.get_by_id(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")

        user = await UsersRepository.get_or_raise_by_id(user_id)
        user.balance += task.value

        await redis.set(f"user:{user_id}:task:{task_id}:complete", 1)

    @staticmethod
    @transaction()
    async def get_updates_task_status(user_id: int) -> dict[TypeTasks, list[Tasks]]:
        tasks_json_copy = tasks_json.copy()
        daily_task = tasks_json_copy["Daily reward"][0]

        daily_task["status"] = "waiting" if await UsersRepository.can_get_daily_task(user_id) else "done"
        daily_task["value"] = await UsersRepository.next_daily_bonus(user_id)

        tasks_json_copy["Daily reward"] = [daily_task]
        other_tasks = tasks_json_copy["Tasks list"]

        for other_task in other_tasks:
            if other_task["type"] in {"channel", "link"}:
                other_task["status"] = "done" if await redis.exists(f"user:{user_id}:task:{other_task["id"]}:complete") else "waiting"

        return tasks_json_copy

    @staticmethod
    async def next_daily_bonus(user_id: int) -> int:
        task_day = await UsersRepository.get_user_daily_task_day(user_id)
        return rewards_for_daily[task_day]

    @staticmethod
    async def can_get_daily_task(user_id: int) -> bool:
        return not bool(await redis.exists(f"user:{user_id}:daily_task_day_status"))

    @staticmethod
    async def get_user_daily_task_day(user_id: int) -> int:
        user_value = await redis.get(f"user:{user_id}:daily_task_day")
        return int(user_value) if isinstance(user_value, str) else 1

    @staticmethod
    async def incr_user_daily_task_day(user_id: int) -> None:
        if await redis.exists(f"user:{user_id}:daily_task_day_status"):
            raise HTTPException(status_code=400, detail="Daily task call one time in day")

        task_day = await UsersRepository.get_user_daily_task_day(user_id)
        if task_day < 8:
            set_value = task_day + 1
        else:
            set_value = 1

        user = await UsersRepository.get_or_raise_by_id(user_id)
        user.balance += rewards_for_daily[task_day]

        await redis.set(f"user:{user_id}:daily_task_day_status", 1, seconds_until_tomorrow())
        await redis.set(f"user:{user_id}:daily_task_day", set_value, seconds_until_day_after_tomorrow())

    @staticmethod
    @transaction()
    async def create_record_of_referral(
            user_id: int, ref_id: int, amount: float, currency: CurrencyLiteral, user_game_id: int | None = None
    ):
        db = require_session()
        referral_record = UserReferral(
            user_id=user_id,
            ref_id=ref_id,
            user_game_id=user_game_id,
            amount=amount,
            currency=currency,
        )

        db.add(referral_record)
        await db.commit()
        await db.refresh(referral_record)

        return referral_record

    @staticmethod
    @transaction()
    async def reward_for_referral_and_user(user_id: int, ref_id: int) -> None:
        user = await UsersRepository.get_by_id(user_id)
        ref = await UsersRepository.get_by_id(ref_id)

        if user is None or ref is None:
            return

        ref.balance += 25000
        await UsersRepository.create_record_of_referral(
            user_id=user_id,
            ref_id=ref_id,
            amount=25000,
            currency="WORDS",
        )

    @staticmethod
    @transaction()
    async def create_stars_payment(amount_stars: int, token: str = settings.TG_BOT_TOKEN) -> str | None:
        bot = Bot(token=token)
        amount_usdt = amount_stars * STARS_USDT_PRICE

        try:
            return await bot.create_invoice_link(
                title="USDT",
                description=f"The balance will be topped up with {amount_usdt} USDT",
                payload=f"balance={amount_usdt}",
                provider_token="",
                currency="XTR",
                prices=[LabeledPrice(label=f"{amount_usdt} USDT", amount=amount_stars)]
            )
        except Exception as e:
            logging.exception("create invoice link exception", exc_info=e)
            return None

    @staticmethod
    @transaction()
    async def confirm_stars_payment(user_id: int, amount_stars: int, telegram_payment_charge_id: str):
        user = await UsersRepository.get_or_raise_by_id(user_id)

        amount_usdt = amount_stars * STARS_USDT_PRICE
        user.balance_usdt += amount_usdt

        db = require_session()
        stars_payment = StarsPayment(
            id=uuid.uuid4(),
            user_id=user_id,
            amount_stars=amount_stars,
            amount_usdt=amount_usdt,
            telegram_payment_charge_id=telegram_payment_charge_id
        )

        db.add(stars_payment)
        await db.commit()

    @staticmethod
    @transaction()
    async def get_referral_rewards(users: list[User]) -> Sequence[UserReferral]:
        db = require_session()

        return (
            await db.execute(
                select(UserReferral)
                .where(UserReferral.user_id.in_([user.id for user in users]))
                .options(selectinload(UserReferral.user))
            )
        ).scalars().all()

    @staticmethod
    @transaction()
    async def get_referrals_by_ref_id(ref_id: int) -> Sequence[User]:
        db = require_session()

        return (
            await db.execute(
                select(User)
                .where(User.ref_id == ref_id)
            )
        ).scalars().all()

    @staticmethod
    @transaction()
    async def get_by_id(user_id: int) -> User | None:
        db = require_session()

        return (
            await db.execute(
                select(User)
                .where(User.id == user_id)
            )
        ).scalar_one_or_none()

    @staticmethod
    @transaction()
    async def get_or_create(
            user_id: int,
            username: str | None,
            full_name: str,
            ref_id: int | None,
    ):
        db = require_session()

        user = await UsersRepository.get_by_id(user_id)
        if user is not None:
            return user

        avatar = await get_user_profile_photo(user_id)
        new_user = User(
            id=user_id,
            full_name=full_name,
            nickname=username,
            avatar=avatar,
            ref_id=ref_id,
            balance=20000,
        )

        db.add(new_user)
        await db.commit()

        if ref_id is not None:
            await UsersRepository.reward_for_referral_and_user(user_id, ref_id)

        await set_user_rating(user_id, await GameRepository.get_user_rating(user_id))
        return new_user

    @staticmethod
    @transaction()
    async def get_or_raise_by_id(user_id: int) -> User:
        user = await UsersRepository.get_by_id(user_id)

        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        return user

    @staticmethod
    @transaction()
    async def get_by_ids(ids: list[int]) -> Sequence[User]:
        db = require_session()

        return (
            await db.execute(
                select(User)
                .where(User.id.in_(ids))
            )
        ).scalars().all()


class GameRepository:
    @staticmethod
    @transaction()
    async def count_next_games() -> int:
        db = require_session()

        return (
            await db.execute(
                select(func.count(Game.id))
                .select_from(Game)
                .where(Game.date_game > datetime.now(UTC))
            )
        ).scalar_one_or_none()

    @staticmethod
    @transaction()
    async def get_user_game_bets(game_id: int, user_id: int):
        db = require_session()
        ret_stat: dict[GameStatLiteral, float] = {
            stat_: 0 for stat_ in ["total_rate"]
        }
        ret_stat_choice: dict[ChoiceLiteral, dict[GameStatLiteral, float]] = {
            choice_: ret_stat.copy() for choice_ in list(typing.get_args(ChoiceLiteral))
        }
        ret_stat_choice_currency: dict[CurrencyLiteral, dict[ChoiceLiteral, dict[GameStatLiteral, float]]] = {
            currency_: ret_stat_choice.copy() for currency_ in list(typing.get_args(CurrencyLiteral))
        }

        stats = (
            await db.execute(
                select(UsersGames.currency, UsersGames.choose, func.sum(UsersGames.total_rate))
                .select_from(UsersGames)
                .where(
                    Game.id == game_id,
                    UsersGames.user_id == user_id,
                )
                .join(Game, UsersGames.game_id == Game.id)
                .group_by(UsersGames.currency, UsersGames.choose)
            )
        ).all()

        for k in stats:
            ret_stat_choice_currency[k[0]][k[1]] = {
                "total_rate": k[2]
            }
        return ret_stat_choice_currency

    @staticmethod
    @transaction()
    async def get_bets_by_user_id(user_id: int) -> Sequence[UsersGames]:
        db = require_session()

        return (
            await db.execute(
                select(UsersGames)
                .join(Game, Game.id == UsersGames.game_id)
                .where(
                    UsersGames.user_id == user_id,
                    Game.course.isnot(None),
                )
                .order_by(Game.date_game.desc())
                .options(selectinload(UsersGames.game))
            )
        ).scalars().all()

    @staticmethod
    @transaction()
    async def get_bets_by_user_and_game_id(user_id: int, game_id: int) -> Sequence[UsersGames]:
        db = require_session()

        return (
            await db.execute(
                select(UsersGames)
                .where(
                    UsersGames.user_id == user_id,
                    UsersGames.game_id == game_id
                )
                .options(selectinload(UsersGames.game))
            )
        ).scalars().all()

    @staticmethod
    @transaction()
    async def get_win_pool(game_id: int, currency: str, choice: str | None = None) -> float:
        db = require_session()

        additional_parameters = []
        if choice is not None:
            additional_parameters.append(UsersGames.choose == choice)

        ret = (
                  await db.execute(
                      select(func.sum(UsersGames.total_rate))
                      .select_from(UsersGames)
                      .where(
                          UsersGames.game_id == game_id,
                          UsersGames.currency == currency,
                          *additional_parameters
                      )
                  )
              ).scalar_one_or_none() or 0
        print(f"ret - {ret}")
        return ret

    @staticmethod
    @transaction()
    async def get_user_rating(user_id: int) -> float:
        db = require_session()

        bets = (
            await db.execute(
                select(UsersGames)
                .select_from(UsersGames)
                .join(Game, Game.id == UsersGames.game_id)
                .where(
                    Game.course_at_computed.isnot(None),
                    UsersGames.user_id == user_id,
                    UsersGames.win_total_rate.isnot(None),
                )
                .options(
                    selectinload(UsersGames.game)
                )
            )
        ).scalars().all()

        rating = 0
        for bet in bets:
            if (
                    (bet.game.course_at_computed > bet.game.course and bet.choose == "YES") or
                    (bet.game.course_at_computed < bet.game.course and bet.choose == "NO")
            ):
                if bet.currency == "WORDS":
                    rating += bet.win_total_rate
                elif bet.currency == "USDT":
                    rating += bet.win_total_rate * 1000

        return rating

    @staticmethod
    @transaction()
    async def get_stats_of_game(game_id: int) -> dict[CurrencyLiteral, dict[ChoiceLiteral, dict[GameStatLiteral, float]]]:
        db = require_session()
        ret_stat: dict[GameStatLiteral, float] = {
            stat_: 0 for stat_ in list(typing.get_args(GameStatLiteral))
        }
        ret_stat_choice: dict[ChoiceLiteral, dict[GameStatLiteral, float]] = {
            choice_: ret_stat.copy() for choice_ in list(typing.get_args(ChoiceLiteral))
        }
        ret_stat_choice_currency: dict[CurrencyLiteral, dict[ChoiceLiteral, dict[GameStatLiteral, float]]] = {
            currency_: ret_stat_choice.copy() for currency_ in list(typing.get_args(CurrencyLiteral))
        }

        stats = (
            await db.execute(
                select(UsersGames.currency, UsersGames.choose, func.sum(UsersGames.total_rate), func.count(UsersGames.id))
                .select_from(UsersGames)
                .where(Game.id == game_id)
                .join(Game, UsersGames.game_id == Game.id)
                .group_by(UsersGames.currency, UsersGames.choose)
            )
        ).all()

        for k in stats:
            ret_stat_choice_currency[k[0]][k[1]] = {
                "users": k[3],
                "total_rate": k[2]
            }
        return ret_stat_choice_currency

    @staticmethod
    @transaction()
    async def get_by_id(game_id: int) -> Game | None:
        db = require_session()
        return (
            await db.execute(
                select(Game)
                .where(Game.id == game_id)
            )
        ).scalar_one_or_none()

    @staticmethod
    @transaction()
    async def game_to_compute() -> Game | None:
        db = require_session()

        return (
            await db.execute(
                select(Game)
                .where(
                    Game.is_computed.is_(False),
                    Game.date_game.isnot(None),
                    Game.course.isnot(None),
                )
                .order_by(Game.date_game)
                .limit(1)
            )
        ).scalar_one_or_none()

    @staticmethod
    @transaction()
    async def set_actual_course_for_game(game_id: int):
        db = require_session()

        await gtp()
        await db.execute(
            update(Game)
            .where(Game.id == game_id)
            .values(course_at_computed=await get_token_price())
        )
        await db.commit()

    @staticmethod
    @transaction()
    async def get_last_game_by_date() -> Game | None:
        db = require_session()

        game = (
            await db.execute(
                select(Game)
                .order_by(Game.date_game.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        return game

    @staticmethod
    @transaction()
    async def get_next_game() -> Game | None:
        db = require_session()

        return (
            await db.execute(
                select(Game)
                .where(
                    Game.date_game > datetime.now(UTC),
                    Game.date_game.isnot(None),
                )
                .order_by(Game.date_game)
                .limit(1)
            )
        ).scalar_one_or_none()

    @staticmethod
    @transaction()
    async def get_previous_game() -> Game | None:
        db = require_session()

        return (
            await db.execute(
                select(Game)
                .where(
                    Game.date_game <= datetime.now(UTC),
                    Game.date_game.isnot(None),
                )
                .order_by(Game.date_game.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    @staticmethod
    @transaction()
    async def get_or_raise_by_id(game_id: int) -> Game:
        db = require_session()
        game = (
            await db.execute(
                select(Game)
                .where(Game.id == game_id)
                .options(selectinload(Game.users_games))

            )
        ).scalar_one_or_none()

        if game is None:
            raise HTTPException(status_code=404, detail="Game not found")

        return game

    @staticmethod
    @transaction()
    async def get_by_date(date: datetime) -> Game | None:
        db = require_session()

        game = (
            await db.execute(
                select(Game)
                .where(
                    Game.date_game == date
                )
            )
        ).scalar_one_or_none()

        return game

    @staticmethod
    @transaction()
    async def create_next_game(last_time_game: datetime, last_exchange_rate_db: float):
        date_future = last_time_game.replace(second=0, microsecond=0, tzinfo=UTC) + timedelta(minutes=10)

        last_exchange_rate = await get_token_price()
        if last_exchange_rate is None:
            last_exchange_rate = last_exchange_rate_db

        await GameRepository.set_or_create_games(
            [
                AdminSetDateGames(
                    date=date_future,
                    exchange_rate=last_exchange_rate,
                )
            ]
        )

    @staticmethod
    @transaction()
    async def set_or_create_games(dates: list[AdminSetDateGames]) -> list[AdminSetDateGames]:
        db = require_session()

        games = []
        dates_set = set()
        for date in dates:
            if date.date.second != 0 or date.date.microsecond != 0:
                date.date = date.date.replace(second=0, microsecond=0, tzinfo=UTC)

            if date.date in dates_set:
                raise HTTPException(status_code=400, detail=f"Duplicate date - {date.date}")

            if exists_game := await GameRepository.get_by_date(date.date):
                exists_game.date_game = date.date
                continue

            dates_set.add(date.date)

            game = Game(
                date_game=date.date,
                course=date.exchange_rate,
            )
            games.append(game)

        db.add_all(games)
        await db.commit()

        return dates

    @staticmethod
    @transaction()
    async def get_user_bet_choice(user_id: int, game_id: int, currency: str) -> str | None:
        db = require_session()

        choices = (
            await db.execute(
                select(UsersGames)
                .where(
                    UsersGames.user_id == user_id,
                    UsersGames.game_id == game_id,
                    UsersGames.currency == currency,
                )
                .limit(1)
            )
        ).scalar_one_or_none()

        return choices.choose if choices is not None else None

    @staticmethod
    @transaction()
    async def bet(user_id: int, game_id: int, bet_model: GameBet) -> UsersGames:
        db = require_session()

        user = await UsersRepository.get_or_raise_by_id(user_id)
        game = await GameRepository.get_or_raise_by_id(game_id)

        user_bet_choice = await GameRepository.get_user_bet_choice(
            user_id, game_id, bet_model.currency
        )

        if user_bet_choice is not None and user_bet_choice != bet_model.choice:
            raise HTTPException(status_code=400, detail=f"You can bet only {user_bet_choice}")

        if bet_model.currency == "WORDS":
            bet_model.amount = int(bet_model.amount)

        if bet_model.amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be greater than zero")

        if bet_model.currency == "USDT":
            if user.balance_usdt < bet_model.amount:
                raise HTTPException(status_code=400, detail="Not enough money")

            user.balance_usdt -= bet_model.amount

        else:
            if user.balance < bet_model.amount:
                raise HTTPException(status_code=400, detail="Not enough money")

            user.balance -= bet_model.amount

        bet_game = UsersGames(
            game=game,
            user=user,
            total_rate=bet_model.amount,
            currency=bet_model.currency,
            choose=bet_model.choice,
        )

        db.add(bet_game)
        await db.commit()

        return bet_game


class TaskRepository:
    @staticmethod
    async def get_by_id(task_id: int) -> Tasks | None:
        for task in tasks:
            if task.id == task_id:
                return task

        return None


class FinanceOperationRepository:
    @staticmethod
    @transaction()
    async def revert_withdrawal(operation_id: str) -> FinanceOperation:
        operation = await FinanceOperationRepository.get_by_id(operation_id)
        if operation is None:
            raise HTTPException(status_code=404, detail="Operation not found")

        if operation.operation_type != "WITHDRAWAL":
            return operation

        if operation.currency == "UZS":
            operation.user.balance_usdt += operation.amount / await get_usdt_uzs()
        elif operation.currency == "RUB":
            operation.user.balance_usdt += operation.amount / await get_usdt_rub()
        elif operation.currency == "USDT":
            operation.user.balance_usdt += operation.amount

        return operation

    @staticmethod
    @transaction()
    async def get_by_id(id: str) -> FinanceOperation | None:
        db = require_session()

        return (
            await db.execute(
                select(FinanceOperation)
                .where(FinanceOperation.id == id)
                .options(selectinload(FinanceOperation.user))
            )
        ).scalar_one_or_none()

    @staticmethod
    @transaction()
    async def create_deposit(
            user_id: int,
            account_operation: AccountOperationDepositRequest,
            cf_connecting_ip: str | None = None,
            operation_type: OperationTypeLiteral = "DEPOSIT",
    ):
        db = require_session()
        fin_op = FinanceOperation(
            id=uuid.uuid4(),
            user_id=user_id,
            operation_type=operation_type,
            amount=account_operation.amount,

            currency=account_operation.currency,

            network=account_operation.network,
            payment_method=account_operation.payment_method,

            from_ip=cf_connecting_ip,
        )

        db.add(fin_op)
        await db.commit()

        return fin_op

    @staticmethod
    @transaction()
    async def create_withdrawal(
            user_id: int,
            account_operation: AccountOperationWithdrawRequest,
            cf_connecting_ip: str,
            operation_type: OperationTypeLiteral = "WITHDRAWAL",

    ) -> FinanceOperation:
        db = require_session()

        fin_op = FinanceOperation(
            id=uuid.uuid4(),
            user_id=user_id,
            operation_type=operation_type,
            amount=account_operation.amount,

            currency=account_operation.currency,

            network=account_operation.network,
            payment_method=account_operation.payment_method,

            card_number=account_operation.card_number,
            address=account_operation.address,

            from_ip=cf_connecting_ip,
        )

        db.add(fin_op)
        await db.commit()

        fin_op_loaded = await FinanceOperationRepository.get_by_id(fin_op.id)
        if fin_op_loaded.currency == "UZS":
            fin_op_loaded.user.balance_usdt -= fin_op_loaded.amount / await get_usdt_uzs()
        elif fin_op_loaded.currency == "RUB":
            fin_op_loaded.user.balance_usdt -= fin_op_loaded.amount / await get_usdt_rub()
        elif fin_op_loaded.currency == "USDT":
            fin_op_loaded.user.balance_usdt -= fin_op_loaded.amount

        return fin_op
