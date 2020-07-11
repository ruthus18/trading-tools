from pytz.tzinfo import DstTzInfo
import datetime as dt
from decimal import Decimal
import enum

from pydantic import BaseModel
import requests

import config


def make_tz_aware(dt: dt.datetime) -> dt.datetime:
    return config.TIMEZONE.localize(dt)


class CandleInterval(str, enum.Enum):
    MIN_1 = '1min'
    MIN_2 = '2min'
    MIN_3 = '3min'
    MIN_5 = '5min'
    MIN_10 = '10min'
    MIN_15 = '15min'
    MIN_30 = '30min'
    HOUR = 'hour'
    DAY = 'day'
    WEEK = 'week'
    MONTH = 'month'


class Candle(BaseModel):
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    time: dt.datetime


class TinkoffClient:
    """Client for working with Tinkoff Investment API

    Documentation:
        https://tinkoffcreditsystems.github.io/invest-openapi/swagger-ui - OpenAPI 
        https://tinkoffcreditsystems.github.io/invest-openapi/marketdata/ - Streaming
    """
    def __init__(self, base_url: str, token: str):
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {token}'
        })
        self._base_url = base_url

        self._balance_id = None

    @property
    def balance_id(self) -> str:
        if not self._balance_id:
            self._balance_id = self.register_sandbox()

        return self._balance_id

    def request(self, method: str, endpoint: str, data: dict = None, params: dict = None) -> dict:
        if data is None:
            data = dict()

        if params is None:
            params = dict()

        response = self.session.request(method, self._base_url + endpoint, json=data, params=params)
        # response.raise_for_status()

        return response.json()['payload']

    def register_sandbox(self) -> str:
        response_data = self.request('POST', 'sandbox/register', data={
            'brokerAccountType': 'Tinkoff'
        })
        return response_data['brokerAccountId']

    def get_portfolio(self) -> dict:
        return self.request('GET', 'portfolio')

    def get_stocks(self) -> list:
        return self.request('GET', 'market/stocks')['instruments']

    def get_bonds(self) -> list:
        return self.request('GET', 'market/bonds')['instruments']

    def get_currencies(self) -> list:
        return self.request('GET', 'market/currencies')['instruments']

    def get_candles(self, figi: str, interval: CandleInterval, start_dt: dt.datetime, end_dt: dt.datetime) -> list:
        response = self.request('GET', 'market/candles', params={
            'figi': figi,
            'from': make_tz_aware(start_dt).isoformat(),
            'to': make_tz_aware(end_dt).isoformat(),
            'interval': interval
        })
        return response['candles']


client = TinkoffClient(config.TINKOFF_SANDBOX_URL, config.TINKOFF_SANDBOX_TOKEN)
