import pandas as pd
import yfinance as yf

def download_tickers(tickers: dict, start: str, end: str) -> pd.DataFrame:
    result = pd.DataFrame()
    for ticker, name in tickers.items():
        df = yf.download(ticker, start=start, end=end, auto_adjust=True)["Close"]
        df = df.resample("MS").mean()
        df.name = name
        result = pd.concat([result, df], axis=1)
    return result

def download_by_ticker(ticker: str, start: str, end: str) -> pd.DataFrame:
    return yf.download(ticker, start=start, end=end, auto_adjust=True)

def extract_close(df, ticker):
    if isinstance(df.columns, pd.MultiIndex):
        return df["Close"][ticker]
    return df["Close"]