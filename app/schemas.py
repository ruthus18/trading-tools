import datetime as dt
import enum
from decimal import Decimal

from pydantic import BaseModel


class Enum(str, enum.Enum):

    def __str__(self):
        return self.value


class Interval(Enum):
    M1 = '1min'
    M5 = '5min'
    M10 = '10min'
    M30 = '30min'
    H1 = 'hour'
    D1 = 'day'
    D7 = 'week'
    D30 = 'month'


class Currency(Enum):
    USD = 'USD'
    RUB = 'RUB'
    EUR = 'EUR'


class Instrument(BaseModel):
    name: str
    ticker: str
    figi: str
    currency: Currency

    def __repr__(self):
        return f"Instrument('{self.name}')"


class Candle(BaseModel):
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    time: dt.datetime


class PortfolioItem(BaseModel):
    instrument: Instrument
    lots: int


class OrderType(Enum):
    BUY = 'buy'
    SELL = 'sell'
