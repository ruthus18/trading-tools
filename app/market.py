import typing as t
from decimal import Decimal

from .schemas import PortfolioItem
from .tinkoff import client as tinkoff_client


class Market:
    """Interface for market access

    Provide major market operations (asset management, performing deals etc.)
    """
    def get_balance(self) -> Decimal:
        raise NotImplementedError

    def get_portfolio(self) -> t.List[PortfolioItem]:
        raise NotImplementedError

    def buy(self, amount: Decimal):
        raise NotImplementedError

    def sell(self, amount: Decimal):
        raise NotImplementedError


class TinkoffMarket(Market):
    """Proxy to Tinkoff Investments API
    """
    def get_balance(self) -> Decimal:
        return tinkoff_client.get_balance_usd()

    def get_portfolio(self) -> t.List[PortfolioItem]:
        return tinkoff_client.get_portfolio()

    def buy(self, amount: Decimal):
        ...

    def sell(self, amount: Decimal):
        ...
