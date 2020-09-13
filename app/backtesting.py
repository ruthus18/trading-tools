import typing as t
from decimal import Decimal

import numpy as np
import pandas as pd
from tqdm import tqdm

from .market import Market
from .schemas import Candle, OrderType
from .trading import Trader


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
