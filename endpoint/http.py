import json
import typing
from datetime import datetime, UTC

from aiogram.utils.web_app import WebAppInitData
from fastapi import APIRouter, Depends, HTTPException, Body, Header

from core import redis, set_user_rating, settings
from core._constants import USDT_RUB_PRICE, USDT_UZS_PRICE
from db.database import transaction
from db.repository import UsersRepository, GameRepository, FinanceOperationRepository
from endpoint.depends import get_web_app_info
from endpoint.models import Init, Rating, AdminSetDateGames, GameBet, GameBetResponse, ReferralResponse, \
    CompleteTaskInput, InitGameResponse, AccountOperationWithdrawRequest, AccountOperationWithdrawResponse, ProfileBetHistory, \
    AccountOperationDepositRequest, CreatedInvoiceDto, InvoiceModel, LogoGameStartResponse, LogoGameEndResponse, StarsPaymentRequest, StarsPaymentResponse
from endpoint.to_model import user_to_model_init, user_to_model_rating_user, bet_game_to_model_game_bet, \
    referrals_to_model_referral, game_to_model_init_game
from utils.get_payment_method import get_payment_method
from utils.rtnet import RtnetAPI

router = APIRouter()


@router.get(
    "/profiles/init",
    response_model=Init,
    response_model_exclude={"channel_id", }
)
@transaction()
async def init(
        ref_id: int | None = None,
        info: WebAppInitData = Depends(get_web_app_info),
):
    user = await UsersRepository.get_or_create(
        user_id=info.user.id,
        username=info.user.username,
        full_name=(info.user.first_name + " " + info.user.last_name or "").strip(),
        ref_id=ref_id,
    )

    return await user_to_model_init(user)


@router.get(
    "/profiles/rating",
    response_model=Rating,
)
@transaction()
async def rating(
        offset: int = 0,
        limit: int = 100,
        info: WebAppInitData = Depends(get_web_app_info),
):
    if limit > 100:
        raise HTTPException(status_code=400, detail="Limit can't exceed 100")

    user = await UsersRepository.get_or_raise_by_id(info.user.id)
    await set_user_rating(user.id, await GameRepository.get_user_rating(user.id))

    user_place_data = await redis.zrevrank("rating", user.id, withscore=True)
    user_place, user_points = user_place_data[0] + 1, int(user_place_data[1])

    rating_list = [
        (int(user_id), int(score)) for user_id, score in
        await redis.zrange("rating", offset, limit, desc=True, withscores=True)
    ]

    account_ids = [user.id] + [user_id for user_id, _ in rating_list]
    accounts_dict = {account.id: account for account in await UsersRepository.get_by_ids(account_ids)}

    users = [
        await user_to_model_rating_user(
            accounts_dict[user_id],
            await redis.zrevrank("rating", user_id) + 1,
            score
        )
        for user_id, score in rating_list
    ]

    return Rating(users=users, user=await user_to_model_rating_user(user, user_place, user_points))


@router.post(
    "/admin/set-dates",
    response_model=list[AdminSetDateGames]
)
@transaction()
async def set_dates(
        dates: list[AdminSetDateGames] = Body(min_length=24, max_length=24),
        info: WebAppInitData = Depends(get_web_app_info),
):
    user = await UsersRepository.get_or_raise_by_id(info.user.id)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="User is not admin")

    result = await GameRepository.set_or_create_games(dates)

    return result


@router.post(
    "/profiles/bet",
    response_model=GameBetResponse,
)
@transaction()
async def bet(
        bet_model: GameBet,
        info: WebAppInitData = Depends(get_web_app_info),
):
    bet_game = await GameRepository.bet(info.user.id, bet_model.game_id, bet_model)

    return await bet_game_to_model_game_bet(bet_game)


@router.get(
    "/profiles/referral",
    response_model=ReferralResponse,
)
@transaction()
async def referral(
        info: WebAppInitData = Depends(get_web_app_info),
):
    user = await UsersRepository.get_or_raise_by_id(info.user.id)
    referrals = await UsersRepository.get_referrals_by_ref_id(user.id)
    referrals_rewards = await UsersRepository.get_referral_rewards(referrals)

    return await referrals_to_model_referral(referrals_rewards)


@router.post(
    "/profiles/task",
    response_model=Init
)
@transaction()
async def complete_task(
        task: CompleteTaskInput,
        info: WebAppInitData = Depends(get_web_app_info),
):
    user = await UsersRepository.get_or_raise_by_id(info.user.id)
    await UsersRepository.complete_task(user.id, task.id)

    return await user_to_model_init(user)


@router.get(
    "/profiles/game-info",
    response_model=InitGameResponse
)
@transaction()
async def game_info(info: WebAppInitData = Depends(get_web_app_info)):
    user = await UsersRepository.get_or_raise_by_id(info.user.id)
    next_game = await GameRepository.get_next_game()

    if next_game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    return await game_to_model_init_game(next_game, user.id)


@router.post(
    "/profiles/logo-game/start",
    response_model=LogoGameStartResponse
)
@transaction()
async def start_logo_game(info: WebAppInitData = Depends(get_web_app_info)):
    user = await UsersRepository.get_or_raise_by_id(info.user.id)

    if user.logo_game_start_time:
        raise HTTPException(status_code=400, detail="The logo game is already started")

    user.logo_game_start_time = datetime.now(UTC)
    return LogoGameStartResponse(start_time=user.logo_game_start_time)


@router.post(
    "/profiles/logo-game/end",
    response_model=LogoGameEndResponse
)
@transaction()
async def end_logo_game(info: WebAppInitData = Depends(get_web_app_info)):
    user = await UsersRepository.get_or_raise_by_id(info.user.id)

    if not user.logo_game_start_time:
        raise HTTPException(status_code=400, detail="The logo game is not started")

    end_time = datetime.now(UTC)
    seconds_passed = (end_time - user.logo_game_start_time).total_seconds()

    words_reward = (
        1000 if seconds_passed <= 5 else
        500 if seconds_passed <= 10 else
        200 if seconds_passed <= 20 else
        0
    )

    user.balance += words_reward
    user.logo_game_start_time = None
    return LogoGameEndResponse(end_time=end_time, words_reward=words_reward)


@router.post(
    "/profiles/withdrawal",
    response_model=AccountOperationWithdrawResponse,
)
@transaction()
async def withdrawal(
        operation: AccountOperationWithdrawRequest,
        x_ip: typing.Annotated[str | None, Header(alias="CF-Connecting-IP")] = None,
        info: WebAppInitData = Depends(get_web_app_info),
):
    user = await UsersRepository.get_or_raise_by_id(info.user.id)

    withdrawal_model = await FinanceOperationRepository.create_withdrawal(
        user_id=user.id,
        account_operation=operation,
        cf_connecting_ip=x_ip,
    )

    if withdrawal_model.currency == "RUB" and withdrawal_model.payment_method in ("Sber", "T-Bank"):
        rtnet = RtnetAPI(
            settings.RTNET_RUB_PROJECT_ID,
            settings.RTNET_RUB_API_ID,
            settings.RTNET_RUB_PRIVATE_KEY,
            settings.RTNET_BASE_URL,
        )
        await rtnet.create_withdrawal(
            client_id=user.id,
            external_id=str(withdrawal_model.id),
            payment_method=get_payment_method(operation.payment_method),
            amount=int(withdrawal_model.amount),
            client_card_number=withdrawal_model.card_number,
            ext_ip=x_ip,
        )
    elif withdrawal_model.currency == "UZS" and withdrawal_model.payment_method in ("Humo", "Uzcard"):
        rtnet = RtnetAPI(
            settings.RTNET_UZS_PROJECT_ID,
            settings.RTNET_UZS_API_ID,
            settings.RTNET_UZS_PRIVATE_KEY,
            settings.RTNET_BASE_URL,
        )
        await rtnet.create_withdrawal(
            client_id=user.id,
            external_id=str(withdrawal_model.id),
            payment_method=get_payment_method(operation.payment_method),
            amount=int(withdrawal_model.amount),
            client_card_number=withdrawal_model.card_number,
            ext_ip=x_ip,
        )
    else:
        raise HTTPException(status_code=403, detail="Другие способы временно недоступны")

    return AccountOperationWithdrawResponse.model_validate(
        withdrawal_model, from_attributes=True
    )


@router.get(
    "/profiles/bets",
    response_model=list[ProfileBetHistory],
)
@transaction()
async def bets(info: WebAppInitData = Depends(get_web_app_info), ):
    user = await UsersRepository.get_or_raise_by_id(info.user.id)

    return [
        ProfileBetHistory.model_validate(
            bet_db, from_attributes=True
        ) for bet_db in await GameRepository.get_bets_by_user_id(user.id)
    ]


@router.post(
    "/profiles/stars",
    response_model=StarsPaymentResponse
)
async def create_stars_payment(request: StarsPaymentRequest, _: WebAppInitData = Depends(get_web_app_info)):
    payment_url = await UsersRepository.create_stars_payment(request.amount_stars)
    if not payment_url:
        raise HTTPException(status_code=400, detail="Error creating payment")

    return StarsPaymentResponse(payment_url=payment_url)


@router.post(
    "/profiles/deposit",
    response_model=CreatedInvoiceDto,
    response_model_exclude={"id", "externalId"}
)
@transaction()
async def deposit(
        operation: AccountOperationDepositRequest,
        x_ip: typing.Annotated[str | None, Header(alias="CF-Connecting-IP")] = None,
        info: WebAppInitData = Depends(get_web_app_info),
):
    user = await UsersRepository.get_or_raise_by_id(info.user.id)

    if operation.currency in ("RUB", "UZS") and operation.amount is None:
        raise HTTPException(status_code=400, detail="Amount required")

    deposit_model = await FinanceOperationRepository.create_deposit(
        user_id=user.id,
        account_operation=operation,
        cf_connecting_ip=x_ip,
    )

    if deposit_model.currency == "RUB" and deposit_model.payment_method in ("Sber", "T-Bank"):
        rtnet = RtnetAPI(
            settings.RTNET_RUB_PROJECT_ID,
            settings.RTNET_RUB_API_ID,
            settings.RTNET_RUB_PRIVATE_KEY,
            settings.RTNET_BASE_URL,
        )
        response = await rtnet.create_deposit(
            client_id=user.id,
            external_id=str(deposit_model.id),
            payment_method=get_payment_method(operation.payment_method),
            amount=int(deposit_model.amount),
        )
    elif deposit_model.currency == "UZS" and deposit_model.payment_method in ("Humo", "Uzcard"):
        rtnet = RtnetAPI(
            settings.RTNET_UZS_PROJECT_ID,
            settings.RTNET_UZS_API_ID,
            settings.RTNET_UZS_PRIVATE_KEY,
            settings.RTNET_BASE_URL,
        )
        response = await rtnet.create_deposit(
            client_id=user.id,
            external_id=str(deposit_model.id),
            payment_method=get_payment_method(operation.payment_method),
            amount=int(deposit_model.amount),
        )
    else:
        raise HTTPException(status_code=403, detail="Другие способы временно недоступны")

    return response


@router.post(
    "/callback",
)
@transaction()
async def callback(
        data: InvoiceModel,
        sign: typing.Annotated[str, Header(alias="Authorization1")],
):
    # validate = RtnetAPI.validate(json.dumps(data, separators=(",", ":")), sign.split(" ")[-1])
    operation = await FinanceOperationRepository.get_by_id(data.ExternalId)
    if operation is None:
        raise HTTPException(status_code=200, detail="Operation not found")

    if operation.operation_type == "DEPOSIT":
        if data.Status == "Paid":
            await redis.set(f"user:{operation.user_id}:pooling", json.dumps({"detail": "Депозит успешно внесен"}, ensure_ascii=False))
            operation.user.balance_usdt += operation.amount / (USDT_RUB_PRICE if operation.currency == "RUB" else USDT_UZS_PRICE)

    if operation.operation_type == "WITHDRAWAL":
        if data.Status == "Cancelled":
            operation.user.balance_usdt += operation.amount / (USDT_RUB_PRICE if operation.currency == "RUB" else USDT_UZS_PRICE)

    return {"status": "ok"}


@router.get(
    "/profiles/pooling/deposit",
)
@transaction()
async def pooling_deposit(
        info: WebAppInitData = Depends(get_web_app_info),
):
    if not await redis.exists(f"user:{info.user.id}:pooling"):
        return {}

    data = await redis.get(f"user:{info.user.id}:pooling")

    await redis.delete(f"user:{info.user.id}:pooling")

    return json.loads(data)
