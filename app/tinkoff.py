import datetime as dt
import json
import logging
import typing as t
from decimal import Decimal

import requests
import websocket
from websocket._app import WebSocketApp

from . import config
from . import models
from .schemas import Candle
from .schemas import Instrument
from .schemas import Interval
from .schemas import PortfolioItem

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s]: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


USD_FIGI = 'BBG0013HGFT4'


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

    def get_portfolio(self) -> t.List[PortfolioItem]:
        portfolio_data = self.request('GET', 'portfolio')['positions']
        return [
            PortfolioItem(
                instrument=Instrument(
                    name=item['name'],
                    ticker=item['ticker'],
                    figi=item['figi'],
                    currency=item['averagePositionPrice']['currency']
                ),
                lots=item['lots'],
            )
            for item in portfolio_data
            if item['figi'] != USD_FIGI
        ]

    def get_balance_usd(self) -> Decimal:
        portfolio = self.get_portfolio()

        for asset in portfolio:
            if asset['figi'] == USD_FIGI:
                return Decimal(asset['balance'])

        return Decimal(0)

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

    def sandbox_set_balance(self, amount=Decimal(10000)):
        self.request('POST', 'sandbox/positions/balance', data={
            'figi': USD_FIGI,
            'balance': float(amount)
        })

    # def limit_order(self, ...):
    #     ...

    # def market_order(self, ...):
    #     ...

    # def cancel_order(self, ...):
    #     ...


class TinkoffStreamClient:
    """Client for getting real-time data from Invest API

    Documentation: https://tinkoffcreditsystems.github.io/invest-openapi/marketdata/
    """
    def __init__(self, token: str):
        self._url = config.TINKOFF_STREAMING_URL
        self.token = token

    @staticmethod
    def subscribe_candles(ws: WebSocketApp, candles_sub: dict):
        """Subscribe to candles info.

        `candles_sub` dict contains elements like (figi code -> candle interval):
        >>> {
        >>>     'BBG0013HGFT4': Interval.M5,
        >>>     ...
        >>> }
        """
        for figi, interval in candles_sub.items():
            body = {'event': 'candle:subscribe', 'figi': figi, "interval": interval}
            ws.send(json.dumps(body))

            logger.info('Subscribed to candle (FIGI=%s)', figi)

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
            candles_sub = {}

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
            logger.info('Stream connection closed')


client = TinkoffClient(config.TINKOFF_SANDBOX_URL, config.TINKOFF_SANDBOX_TOKEN)
stream_client = TinkoffStreamClient(config.TINKOFF_SANDBOX_TOKEN)


def import_to_db(start_dt: dt.datetime, end_dt: dt.datetime, instrument: models.Instrument):
    start = start_dt
    end = start + dt.timedelta(days=7)

    while end < end_dt:
        print(f'{start} - {end}')
        candles = list(client.get_candles(instrument.figi, interval=Interval.H1, start_dt=start, end_dt=end))
        for candle in candles:
            data = candle.dict()
            data['time'] = data['time'].replace(tzinfo=None)

            models.Candle.get_or_create(**data, instrument=instrument, interval=Interval.H1)

        start = end
        end = start + dt.timedelta(days=7)


class TinkoffImporter:

    def __init__(self, tinkoff_client: TinkoffClient = None):
        if tinkoff_client is None:
            tinkoff_client = client

        self._client = tinkoff_client

    async def import_stocks(self):
        stocks = self._client.get_stocks()

        


    async def import_candles(
        self,
        instrument: str,
        start_dt: dt.datetime,
        end_dt: dt.datetime,
        interval=Interval.H1
    ):
        ...
