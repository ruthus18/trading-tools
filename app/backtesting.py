import itertools
import typing as t
from decimal import Decimal

import numpy as np
import pandas as pd
import peewee as pw
import plotly.graph_objects as go
from tqdm import tqdm

from .market import Market
from .schemas import Candle, OrderType
from .trading import Trader

TINKOFF_COMISSION = Decimal(0.0005)


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


class BacktesterStatistics:

    def __init__(self, trades: pd.DataFrame, comission_fee: Decimal):
        self._trades = trades
        self.comission_fee = comission_fee

        self._positions = None

    def _calc_profit_ratio(self, row):
        if row.order_enter == 'buy':
            return float(
                (Decimal(row.price_exit) - Decimal(row.price_exit) * self.comission_fee) /
                (Decimal(row.price_enter) + Decimal(row.price_enter) * self.comission_fee)
            )
        else:
            return float(
                (Decimal(row.price_enter) + Decimal(row.price_enter) * self.comission_fee) /
                (Decimal(row.price_exit) - Decimal(row.price_exit) * self.comission_fee)
            )

    @staticmethod
    def _calc_equity(profit_ratio):
        equity = [Decimal(1)]
        for val in profit_ratio:
            current_eq = equity[-1] * Decimal(val)
            equity.append(current_eq)

        return equity[1:]

    @property
    def positions(self):
        if self._positions is not None:
            return self._positions

        positions = self._trades.merge(
            self._trades.shift(-1),
            suffixes=('_enter', '_exit'),
            left_index=True,
            right_index=True
        )[:-1]
        positions['profit_ratio'] = positions.apply(self._calc_profit_ratio, axis=1)
        positions['equity'] = self._calc_equity(positions['profit_ratio'].values)

        self._positions = positions
        return positions

    def geo_mean(self):
        # при geo_mean < 1 торговая система убыточна
        a = np.log(self.positions.profit_ratio)
        return np.exp(a.sum() / len(a))

    def profit_stats(self):
        return self.positions.profit_ratio.describe()

    def profit_density(self):
        return self.positions.profit_ratio.plot.density()

    def twr(self):
        return self.positions.profit_ratio.product()

    @property
    def equity_graph(self):
        equity_graph = go.Figure(data=[
            go.Scatter(
                name='Equity',
                x=self.positions.time_exit,
                y=self.positions.equity,
                line=dict(color='#fe8019', width=1)
            ),
        ])
        equity_graph.update_layout(template='plotly_white')
        return equity_graph


class Backtester:

    def __init__(self, candles: t.Iterable[Candle]):
        self._candles = candles
        self.market = BacktesterMarket()

        self._tested = False
        self._candles_cache = None

    @classmethod
    def from_df(cls, df: pd.DataFrame):
        candles = (Candle(**candle_data) for candle_data in df.to_dict(orient='records'))

        return cls(candles=candles)

    @classmethod
    def from_db(cls, query: pw.ModelSelect):
        candles = (Candle(**row) for row in query.dicts())

        return cls(candles=candles)

    def _prepare_trades_df(self) -> pd.DataFrame:
        """Собрать DataFrame с совершенными сделками на основе рыночной истории сделок
        """
        candles_df = pd.DataFrame.from_dict(
            candle.dict() for candle in self._candles_cache
        )
        candles_df = candles_df[['open', 'time']]

        candles_df['price'] = candles_df['open'].shift(-1)
        candles_df = candles_df.drop(columns=['open'])

        return candles_df.merge(
            self.market.trade_history.rename('order'),
            left_on='time',
            right_index=True
        )[:-1].reset_index(drop=True)

    def run(self, trader: Trader, comission_fee=TINKOFF_COMISSION) -> pd.Series:
        trader.start(self.market)

        self._candles, self._candles_cache = itertools.tee(self._candles)
        self._candles_cache = list(self._candles_cache)

        for candle in tqdm(self._candles, total=len(self._candles_cache)):
            self.market.current_dt = candle.time
            trader._on_candle(candle)

        trades = self._prepare_trades_df()
        return BacktesterStatistics(trades, comission_fee)
