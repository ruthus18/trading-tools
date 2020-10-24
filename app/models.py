from tortoise import Tortoise
from tortoise import fields
from tortoise import models
from tortoise.fields.base import CASCADE

from . import config
from .schemas import Currency


async def init_db():
    await Tortoise.init(config.TORTOISE_ORM)


async def db_size():
    conn = Tortoise.get_connection("default")
    _, result = await conn.execute_query(f"SELECT pg_database_size('{config.DB_NAME}')/1024 AS kb_size;")
    size_mb = result[0].get('kb_size') / 1000

    return f'{size_mb} MB'


class Instrument(models.Model):
    id = fields.IntField(pk=True)

    name = fields.TextField()
    ticker = fields.CharField(max_length=8, unique=True)
    figi = fields.CharField(max_length=32, unique=True)
    currency = fields.TextField(default=Currency.USD)

    imported_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        indexes = ('ticker', 'figi', )


class Candle(models.Model):
    instrument = fields.ForeignKeyField('models.Instrument', related_name='candles', on_delete=CASCADE)
    interval = fields.CharField(max_length=5)

    open = fields.DecimalField(max_digits=10, decimal_places=2)
    high = fields.DecimalField(max_digits=10, decimal_places=2)
    low = fields.DecimalField(max_digits=10, decimal_places=2)
    close = fields.DecimalField(max_digits=10, decimal_places=2)
    volume = fields.DecimalField(max_digits=10, decimal_places=2)
    time = fields.DatetimeField()

    class Meta:
        indexes = (('instrument', 'interval', 'time'), )
        unique_together = (('instrument', 'interval', 'time'), )
