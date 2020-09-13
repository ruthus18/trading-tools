import typing as t
from decimal import Decimal

import numpy as np
import pandas as pd
from tqdm import tqdm

from .schemas import Candle, PortfolioItem, OrderType
from .tinkoff import client as tinkoff_client
from .utils import PriceHistory


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


class BacktesterMarket(Market):
    """Market object for perfoming tests on historical data
    """
    def __init__(self, balance=Decimal(10000)):
        self._balance = balance
        self.current_dt = None

        self.trade_history = pd.Series(dtype=np.short)

    def get_balance(self):
        return self._balance

    def buy(self, amount: Decimal = Decimal(1)):
        self.trade_history = self.trade_history.append(
            pd.Series([OrderType.BUY], index=[self.current_dt])
        )

    def sell(self, amount: Decimal = Decimal(1)):
        self.trade_history = self.trade_history.append(
            pd.Series([OrderType.SELL], index=[self.current_dt])
        )


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


class Trader:
    """Entity which perform deals with assets on market.
    """
    def __init__(self):
        self.market = None

    def _on_candle(self, candle: Candle):
        if not self.market:
            raise RuntimeError('You should call `start` method before receiving candles data!')

        self.on_candle(candle)

    def on_candle(self, candle: Candle):
        raise NotImplementedError

    def start(self, market: Market):
        self.market = market


class MAIntersectionTrader(Trader):
    """Робот, торгующий сигналы на основе пересечения SMA

    Сигнал покупки:
        * SMA(2) пересекает SMA(10) вверх

    Сигнал продажи:
        * SMA(2) пересекает SMA(10) вниз
    """
    sma_short_size = 2
    sma_long_size = 10

    def __init__(self):
        super().__init__()

        self.history = PriceHistory(size=10)
        self.sma_diffs = pd.Series(dtype=np.int)
        self.sma_signs = pd.Series(dtype=np.short)  # (value < 0) -> -1 ; (value > 0) -> 1

    def on_candle(self, candle: Candle):
        self.history.add(candle.close, candle.time)

        if len(self.history) == self.sma_long_size:
            # 1. Calc SMA's
            date, sma_short = self.history.calc_sma(self.sma_short_size)
            _, sma_long = self.history.calc_sma(self.sma_long_size)

            # 2. Calc SMA diff
            sma_diff = sma_short - sma_long
            self.sma_diffs = self.sma_diffs.append(pd.Series([sma_diff], index=[date]))

            # 3. Calc SMA sign change
            if len(self.sma_diffs) >= 2:
                if sma_diff > 0:
                    sign = 1  # SMA(2) > SMA(10)
                elif sma_diff < 0:
                    sign = -1  # SMA(2) < SMA(10)
                else:
                    sign = 0  # SMA(2) = SMA(10)

                self.sma_signs = self.sma_signs.append(pd.Series([sign], index=[date]))

            # 4. Generate trading signals
            if len(self.sma_signs) >= 2:
                self.generate_signal()

    def generate_signal(self):
        prev, last = self.sma_signs[-2:]
        sign_diff = last - prev

        if sign_diff == 2:
            self.market.buy()

        elif sign_diff == -2:
            self.market.sell()

        elif prev == 0:
            if last == 1:
                self.market.buy()

            elif last == -1:
                self.market.sell()


class Backtester:

    def __init__(self, candles: t.Iterable[Candle]):
        self._candles = candles
        self.market = BacktesterMarket()

    @classmethod
    def from_df(cls, df: pd.DataFrame):
        candles = [Candle(**candle_data) for candle_data in df.to_dict(orient='records')]

        return cls(candles=candles)

    def run(self, trader: Trader) -> pd.Series:
        trader.start(self.market)

        for candle in tqdm(self._candles):
            self.market.current_dt = candle.time
            trader._on_candle(candle)

        return self.market.trade_history
