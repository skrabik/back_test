from endpoint.models import MoneyPaymentMethodLiteral


def get_payment_method(payment: MoneyPaymentMethodLiteral | None) -> str | None:
    return {
        "Sber": "CardToCardSberbank",
        "T-Bank": "CardToCardTinkoff",
        "Humo": "CardToCardHumo",
        "Uzcard": "CardToCardUzCard",
    }.get(payment)
