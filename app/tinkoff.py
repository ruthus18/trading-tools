import datetime as dt
import enum
import json
import logging
import typing as t
from decimal import Decimal

import requests
from pydantic import BaseModel
import websocket
from websocket._app import WebSocketApp

from . import config


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s]: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def make_tz_aware(dt: dt.datetime) -> str:
    return config.TIMEZONE.localize(dt).isoformat()


def convert_api_dt(dt_str: str) -> dt.datetime:
    return dt.datetime.fromisoformat(dt_str.replace('Z', '+00:00')).astimezone(config.TIMEZONE)


class APIError(requests.RequestException):

    def __init__(self, message, code):
        super().__init__(message)

        self.code = code

    def __str__(self):
        return f'{self.code} {super().__str__()}'


class StreamingError(RuntimeError):
    pass


class Interval(str, enum.Enum):
    M1 = '1min'
    M2 = '2min'
    M3 = '3min'
    M5 = '5min'
    M10 = '10min'
    M15 = '15min'
    M30 = '30min'
    H1 = 'hour'
    D1 = 'day'
    D7 = 'week'
    D30 = 'month'

    def __str__(self):
        return self.value


class Currency(str, enum.Enum):
    USD = 'USD'
    RUB = 'RUB'
    EUR = 'EUR'

    def __str__(self):
        return self.value


class Instrument(BaseModel):
    name: str
    ticker: str
    currency: Currency
    figi: str


class Candle(BaseModel):
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    time: dt.datetime


class TinkoffClient:
    """Client for making HTTP requests to Invest API

    Documentation:
        https://tinkoffcreditsystems.github.io/invest-openapi/swagger-ui
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
        response_data = response.json()

        if response_data['status'] == 'Error':
            payload = response_data['payload']

            raise APIError(payload['message'], payload['code'])

        return response_data['payload']

    def register_sandbox(self) -> str:
        response_data = self.request('POST', 'sandbox/register', data={
            'brokerAccountType': 'Tinkoff'
        })
        return response_data['brokerAccountId']

    def get_portfolio(self) -> dict:
        return self.request('GET', 'portfolio')

    def get_stocks(self) -> t.List[Instrument]:

        stocks = self.request('GET', 'market/stocks')['instruments']
        return [Instrument(**stock) for stock in stocks]

    def get_bonds(self) -> t.List[Instrument]:

        bonds = self.request('GET', 'market/bonds')['instruments']
        return [Instrument(**bond) for bond in bonds]

    def get_currencies(self) -> t.List[Instrument]:

        currencies = self.request('GET', 'market/currencies')['instruments']
        return [Instrument(**currency) for currency in currencies]

    def get_candles(
        self, figi: str, interval: Interval, start_dt: dt.datetime, end_dt: dt.datetime
    ) -> t.Generator[Candle, None, None]:
        """Get historic candles for selected instrument, period and interval.
        """
        response = self.request('GET', 'market/candles', params={
            'figi': figi,
            'from': make_tz_aware(start_dt),
            'to': make_tz_aware(end_dt),
            'interval': interval
        })
        if 'candles' not in response:
            raise APIError(response['message'], response['code'])

        return (
            Candle(
                open=candle['o'],
                high=candle['h'],
                low=candle['l'],
                close=candle['c'],
                volume=candle['v'],
                time=convert_api_dt(candle['time'])
            )
            for candle in response['candles']
        )


class TinkoffStreamClient:
    """Client for getting real-time data from Invest API

    Documentation: https://tinkoffcreditsystems.github.io/invest-openapi/marketdata/
    """
    def __init__(self, token: str):
        self._url = config.TINKOFF_STREAMING_URL
        self.token = token

    @staticmethod
    def subscribe_candles(ws: WebSocketApp, candles_sub: dict):

        for figi, interval in candles_sub.items():
            body = {'event': 'candle:subscribe', 'figi': figi, "interval": interval}
            ws.send(json.dumps(body))

            logger.info('Subscribed to candles of %s', figi)

        logger.info('Stream connection started')

    @staticmethod
    def on_message(ws: WebSocketApp, msg: str):
        msg_data = json.loads(msg)
        logger.info('Got message (event=%s): %s', msg_data['event'], msg_data['payload'])

    @staticmethod
    def on_error(ws: WebSocketApp, err: Exception):
        raise err

    def run(
        self,
        on_message: t.Callable = None,
        on_error: t.Callable = None,
        candles_sub: dict = None,
    ):
        on_message = on_message or self.on_message
        on_error = on_error or self.on_error

        if not candles_sub:
            logger.warning('No candles to subscribe!')
            candles_sub = candles_sub or {}

        ws = websocket.WebSocketApp(
            url=self._url,
            header=[f'Authorization: Bearer {config.TINKOFF_TRADING_TOKEN}'],
            on_open=lambda ws: self.subscribe_candles(ws, candles_sub),
            on_message=on_message,
            on_error=on_error,
        )
        try:
            ws.run_forever()
        except KeyboardInterrupt:
            ws.close()
        except Exception:
            ws.close()
            logger.info('Stream connection closed')
            raise


client = TinkoffClient(config.TINKOFF_SANDBOX_URL, config.TINKOFF_SANDBOX_TOKEN)
stream_client = TinkoffStreamClient(config.TINKOFF_SANDBOX_TOKEN)
