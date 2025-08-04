import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

OperationTypeLiteral = Literal["WITHDRAWAL", "DEPOSIT"]
CurrencyLiteral = Literal["USDT", "WORDS"]
ChoiceLiteral = Literal["YES", "NO"]
TypeTasks = Literal["Daily reward", "Tasks list"]
GameStatLiteral = Literal["total_rate", "users"]
MoneyTypeLiteral = Literal["CRYPTO", "FIAT"]
MoneyCurrencyLiteral = Literal["USDT", "RUB", "UZS"]
MoneyNetworkLiteral = Literal["TRON"]
MoneyPaymentMethodLiteral = Literal["Sber", "T-Bank", "Humo", "Uzcard"]


class GameResponse(BaseModel):
    id: int
    date: datetime


class InitGameResponse(GameResponse):
    stats: dict[CurrencyLiteral, dict[ChoiceLiteral, dict[GameStatLiteral, float]]]
    user_bet: dict[CurrencyLiteral, dict[ChoiceLiteral, dict[GameStatLiteral, float]]]
    course: float


class Tasks(BaseModel):
    id: int
    icon: str
    title: str
    status: Literal["waiting", "inProgress", "done"]

    type: Literal["daily", "link", "channel"]
    link: str | None = None
    channel: str | None = None
    value: int | None = None

    channel_id: int | None = Field(None, exclude=True)


class Init(BaseModel):
    id: int
    nickname: str | None
    full_name: str
    avatar: str | None
    is_admin: bool
    previous_game_results: dict[CurrencyLiteral, float]

    balance: int
    balance_usdt: float
    wins: int

    tasks: dict[TypeTasks, list[Tasks]]

    next_game: InitGameResponse | None

    current_token_price: float | None

    daily_task_day: int = Field(description="Число от 1 до 7 или null")


class RatingUser(BaseModel):
    id: int
    avatar: str | None
    full_name: str
    points: int
    place: int


class Rating(BaseModel):
    users: list[RatingUser]
    user: RatingUser


class AdminSetDateGames(BaseModel):
    date: datetime
    exchange_rate: float


class GameBet(BaseModel):
    game_id: int
    currency: CurrencyLiteral
    amount: float
    choice: ChoiceLiteral


class GameBetResponse(BaseModel):
    game: GameResponse
    currency: CurrencyLiteral
    amount: float
    choice: ChoiceLiteral
    actual_balance_usdt: float
    actual_balance: float
    stats: dict[CurrencyLiteral, dict[ChoiceLiteral, dict[GameStatLiteral, float]]]
    user_bet: dict[CurrencyLiteral, dict[ChoiceLiteral, dict[GameStatLiteral, float]]]


class ReferralUserResponse(BaseModel):
    full_name: str
    words: int
    usdt: float


class ReferralResponse(BaseModel):
    referrals: list[ReferralUserResponse]
    total_users: int
    total_usdt: float
    total_words: int


class CompleteTaskInput(BaseModel):
    id: int


class LogoGameStartResponse(BaseModel):
    start_time: datetime


class LogoGameEndResponse(BaseModel):
    end_time: datetime
    words_reward: int


class AccountOperationWithdrawRequest(BaseModel):
    currency: MoneyCurrencyLiteral

    network: MoneyNetworkLiteral | None = None
    payment_method: MoneyPaymentMethodLiteral | None = None

    card_number: str | None = None
    address: str | None = None

    amount: float


class AccountOperationWithdrawResponse(AccountOperationWithdrawRequest):
    id: uuid.UUID


class AccountOperationDepositRequest(BaseModel):
    currency: MoneyCurrencyLiteral

    network: MoneyNetworkLiteral | None = None
    payment_method: MoneyPaymentMethodLiteral | None = None

    amount: float | None


class AccountOperationDepositResponse(AccountOperationDepositRequest):
    id: uuid.UUID


class GameBetHistoryResponse(BaseModel):
    id: int
    date_game: datetime
    course: float
    course_at_computed: float | None


class ProfileBetHistory(BaseModel):
    id: int
    total_rate: float
    currency: CurrencyLiteral
    choice: ChoiceLiteral = Field(validation_alias="choose")
    win_total_rate: float | None
    game: GameBetHistoryResponse
    time_created: datetime


class StarsPaymentRequest(BaseModel):
    amount_stars: int


class StarsPaymentResponse(BaseModel):
    payment_url: str


class BankSettings(BaseModel):
    id: str = Field(description="Код банка")
    currency: Literal['RUB', 'USD', 'EUR', 'UZS', 'AZN', 'TJR', 'KZT', 'BYN', 'KGS', 'AMD'] = Field(description="Мировая валюта")
    name: str = Field(description="Название банка")
    logo: str = Field(description="Логотип банка в base64 формате (svg)")
    bankType: int = Field(description="Числовой код банка")


class CreatedInvoiceDto(BaseModel):
    id: int = Field(description="RT ID")
    externalId: str = Field(description="ID счета в вашей системе")
    amount: float = Field(description="Сумма, на которую был выставлен счет")
    usdtPrice: float = Field(description="Цена Usdt к рублю на момент создания счета")
    usdtAmount: float | None = Field(None, description="Сумма Usdt")
    expiryDate: datetime = Field(description="Время жизни счета (UTC)")
    cardNumber: Optional[str] = Field(None, description="Карта, на которую клиент должен отправить деньги (только для C2C методов)")
    cardHolder: Optional[str] = Field(None, description="Имя держателя карты/СБП счета")
    bank: Optional[str] = Field(None, description="Банк карты")
    bankSettings: Optional[BankSettings] = Field(None, description="Имя и лого банка карты для оплаты счета")
    paymentMethod: str = Field(description="Платёжный метод")


class InvoiceModel(BaseModel):
    EntityType: Literal['Invoice'] | str = Field(description="Тип сущности")
    Id: str = Field(description="Идентификатор счета")
    ExternalId: str = Field(description="Внешний идентификатор счета")
    Status: Literal['Paid', 'Unpaid', 'Cancelled'] | str = Field(description="Статус счета")
    Currency: str = Field(description="Валюта счета")
    Amount: float = Field(description="Сумма счета")
    PaidAmount: float = Field(description="Фактически оплаченная сумма")
    UsdtPrice: float = Field(description="Цена USDT к валюте счета")
