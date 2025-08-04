from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, PreCheckoutQuery

from core import settings
from db.repository import UsersRepository

bot = Bot(settings.TG_BOT_TOKEN)

dp = Dispatcher()
router = Router()


@router.message(CommandStart())
async def start_command(message: Message, command: CommandObject):
    url = settings.DOMAIN if not command.args else command.args
    await message.answer(
        text="Predict. Bet. Win!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="start", web_app=WebAppInfo(url=url))]
        ]),
    )


@router.pre_checkout_query()
async def pre_checkout_query(query: PreCheckoutQuery):
    if query.currency == "XTR":
        await query.answer(True)


@router.message(F.successful_payment)
async def successful_payment(message: Message):
    currency = message.successful_payment.currency
    total_amount = message.successful_payment.total_amount
    telegram_payment_charge_id = message.successful_payment.telegram_payment_charge_id

    if currency == "XTR":
        await UsersRepository.confirm_stars_payment(message.from_user.id, total_amount, telegram_payment_charge_id)


dp.include_router(router)
