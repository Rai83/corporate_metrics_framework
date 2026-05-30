import pandas as pd
from fredapi import Fred
import os

fred = Fred(api_key=os.getenv("FRED_API_KEY", ""))

def download_by_ticker(ticker: str, asset_name: str, start_date: str, end_date: str) -> pd.DataFrame:
    data = fred.get_series(ticker, observation_start=start_date, observation_end=end_date)
    data.name = asset_name
    return data