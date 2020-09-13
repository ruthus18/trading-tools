import yfinance as yf

sp500 = yf.Ticker('^GSPC')
df = sp500.history(period='1y', interval='1h')