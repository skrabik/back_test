from core import get_token_price
from db.database import transaction
from db.models import User, Game, UsersGames, UserReferral
from db.repository import GameRepository, UsersRepository
from endpoint.models import Init, RatingUser, GameResponse, GameBetResponse, ReferralResponse, ReferralUserResponse, \
    InitGameResponse


@transaction()
async def user_to_model_init(user: User):
    next_game = await GameRepository.get_next_game()
    user_daily_task_day = await UsersRepository.get_user_daily_task_day(user.id)

    return Init(
        id=user.id,
        full_name=user.full_name,
        nickname=user.nickname,
        avatar=user.avatar,
        balance=int(user.balance),
        is_admin=user.is_admin,
        previous_game_results=await UsersRepository.get_previous_game_wins(user.id),
        tasks=await UsersRepository.get_updates_task_status(user.id),
        wins=user.wins,
        next_game=(await game_to_model_init_game(next_game, user.id)) if next_game else None,
        balance_usdt=user.balance_usdt,
        current_token_price=await get_token_price(),
        daily_task_day=user_daily_task_day,
    )


async def user_to_model_rating_user(user: User, place: int, points: int) -> RatingUser:
    return RatingUser(
        id=user.id,
        full_name=user.full_name,
        avatar=user.avatar,
        points=points,
        place=place,
    )


@transaction()
async def game_to_model(game: Game) -> GameResponse:
    return GameResponse(
        id=game.id,
        date=game.date_game,
    )


@transaction()
async def game_to_model_init_game(game: Game, user_id: int) -> InitGameResponse:
    stats = await GameRepository.get_stats_of_game(game.id)
    user_bet = await GameRepository.get_user_game_bets(game.id, user_id)
    return InitGameResponse(
        **((await game_to_model(game)).model_dump()),
        stats=stats,
        course=game.course,
        user_bet=user_bet
    )


async def bet_game_to_model_game_bet(bet_game: UsersGames) -> GameBetResponse:
    user_bet = await GameRepository.get_user_game_bets(bet_game.game.id, bet_game.user.id)
    return GameBetResponse(
        game=await game_to_model(bet_game.game),
        currency=bet_game.currency,  # type: ignore
        amount=bet_game.total_rate,
        choice=bet_game.choose,  # type: ignore
        actual_balance_usdt=bet_game.user.balance_usdt,
        actual_balance=int(bet_game.user.balance),
        stats=await GameRepository.get_stats_of_game(bet_game.game_id),
        user_bet=user_bet
    )


async def referrals_to_model_referral(referrals: list[UserReferral]) -> ReferralResponse:
    total_usdt = sum([ref.amount for ref in referrals if ref.currency == "USDT"])
    total_words = sum([ref.amount for ref in referrals if ref.currency == "WORDS"])

    referrals_group: dict[int, list[UserReferral]] = {}
    for ref in referrals:
        referrals_group[ref.user_id] = referrals_group.get(ref.user_id, []) + [ref]

    referrals_group_sum: list[tuple[str, int, int]] = []
    for value in referrals_group.values():
        total_usdt_user = sum([ref.amount for ref in value if ref.currency == "USDT"])
        total_words_user = sum([ref.amount for ref in value if ref.currency == "WORDS"])

        referrals_group_sum.append((value[0].user.full_name, total_usdt_user, total_words_user))

    return ReferralResponse(
        total_usdt=total_usdt,
        total_words=total_words,
        total_users=len(referrals_group_sum),
        referrals=[
            ReferralUserResponse(
                full_name=value[0],
                usdt=value[1],
                words=value[2],
            ) for value in referrals_group_sum
        ]
    )
