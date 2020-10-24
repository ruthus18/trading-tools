import datetime as dt
import itertools
import typing as t
from decimal import Decimal

from pydantic import BaseModel
import numpy as np
import pandas as pd
from tortoise.queryset import QuerySet
import plotly.graph_objects as go
from tqdm import tqdm

from . import schemas
from .indicators import Indicator, PositionType

TINKOFF_COMISSION = Decimal(0.0005)


class Position(BaseModel):
    type: t.Optional[PositionType]
    open_time: t.Optional[dt.datetime]
    open_price: t.Optional[dt.datetime]
    close_time: t.Optional[dt.datetime]
    close_price: t.Optional[dt.datetime]


class BacktesterMarket:

    def __init__(self, balance=Decimal(10000)):
        self._positions: t.List[Position] = []

        self.current_time: dt.datetime = None
        self.current_price: Decimal = None
        self.current_position = Position()

    def open_position(self, position_type: PositionType):
        if self.current_position.type is not None:
            raise RuntimeError('Position already opened!')

        self.current_position.type = position_type
        self.current_position.open_time = self.current_time
        self.current_position.open_price = self.current_price

    def close_position(self):
        if self.current_position.type is None:
            raise RuntimeError('Position is not opened!')

        self.current_position.close_time = self.current_time
        self.current_position.close_price = self.current_price

        self._positions.append(self.current_position)
        self.current_position = Position()

    @property
    def positions_df(self) -> pd.DataFrame:
        return pd.DataFrame.from_dict(position.dict() for position in self._positions)


class Backtester:

    def __init__(self, candles: t.Iterable[schemas.Candle]):
        self._candles = candles
        self.market = BacktesterMarket()

        self._tested = False
        self._candles_cache = None

    @classmethod
    def from_df(cls, df: pd.DataFrame) -> 'Backtester':
        return cls(candles=(
            schemas.Candle(**candle) for candle in df.to_dict(orient='records')
        ))

    @classmethod
    def from_db(cls, candles_qs: QuerySet) -> 'Backtester':
        return cls(candles=(
            schemas.Candle.from_orm(candle) for candle in candles_qs
        ))

    def run(self, indicator: Indicator, comission_fee=TINKOFF_COMISSION) -> 'BacktesterStatistics':
        indicator.start(self.market)

        self._candles, self._candles_cache = itertools.tee(self._candles)
        self._candles_cache = list(self._candles_cache)

        prev_candle = next(self._candles)

        for next_candle in tqdm(self._candles, total=len(self._candles_cache) - 1):
            self.market.current_time = next_candle.time
            self.market.current_price = next_candle.open

            indicator._on_candle(prev_candle)

            prev_candle = next_candle

        return BacktesterStatistics(self.market.positions_df, comission_fee)

    # def _prepare_trades_df(self) -> pd.DataFrame:
    #     """Собрать DataFrame с совершенными сделками на основе рыночной истории сделок
    #     """
    #     candles_df = pd.DataFrame.from_dict(
    #         candle.dict() for candle in self._candles_cache
    #     )
    #     candles_df = candles_df[['open', 'time']]

    #     candles_df['price'] = candles_df['open'].shift(-1)
    #     candles_df = candles_df.drop(columns=['open'])

    #     return candles_df.merge(
    #         self.market.trade_history.rename('order'),
    #         left_on='time',
    #         right_index=True
    #     )[:-1].reset_index(drop=True)


class BacktesterStatistics:

    def __init__(self, positions: pd.DataFrame, comission_fee: Decimal):
        self._raw_positions = positions
        self.comission_fee = comission_fee

        self._positions = None

    def _calc_profit_ratio(self, row):
        if row.type == PositionType.long:
            return float(
                (Decimal(row.close_price) - Decimal(row.close_price) * self.comission_fee) /
                (Decimal(row.open_price) + Decimal(row.open_price) * self.comission_fee)
            )
        else:
            return float(
                (Decimal(row.open_price) + Decimal(row.open_price) * self.comission_fee) /
                (Decimal(row.close_price) - Decimal(row.close_price) * self.comission_fee)
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

        positions = self._raw_positions.copy()
        positions['profit_ratio'] = positions.apply(self._calc_profit_ratio, axis=1)
        positions['equity'] = self._calc_equity(positions.profit_ratio.values)

        self._positions = positions
        return positions

    @property
    def profit_stats(self):
        return self.positions.profit_ratio.describe()

    @property
    def profit_density(self):
        return self.positions.profit_ratio.plot.density()

    @property
    def ariph_mean(self):
        # при ariph_mean < 1 торговая система убыточна
        return self.profit_stats['mean']

    @property
    def geo_mean(self):
        # при geo_mean < 1 торговая система убыточна
        a = np.log(self.positions.profit_ratio)
        return np.exp(a.sum() / len(a))

    @property
    def twr(self):
        return self.positions.profit_ratio.product()

    @property
    def equity_graph(self):
        equity_graph = go.Figure(data=[
            go.Scatter(
                name='Equity',
                x=self.positions.close_time,
                y=self.positions.equity,
                line=dict(color='#fe8019', width=1)
            ),
        ])
        equity_graph.update_layout(template='plotly_white')
        return equity_graph
