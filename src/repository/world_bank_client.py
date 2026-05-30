from pathlib import Path

import pandas as pd
import requests, io

DATA_MONTHLY_XLSX = "CMO-Historical-Data-Monthly.xlsx"
URL = (
        "https://thedocs.worldbank.org/en/doc/"
        "18675ac081f0d6cf6e50a00db2ac2afc-0050012024/"
        "original/CMO-Historical-Data-Monthly.xlsx"
    )

def download_data_file():
    response = requests.get(URL, timeout=60)
    response.raise_for_status()
    xls = pd.ExcelFile(io.BytesIO(response.content))

    output_path = Path(__file__).parent / "data" / DATA_MONTHLY_XLSX
    with open(output_path, "wb") as f:
        f.write(response.content)

def parse_world_bank_dates(index):
    return pd.to_datetime(
        index.astype(str).str.replace(r'M', '-', regex=False),
        format="%Y-%m",
        errors="coerce"
    )

def get_by_ticker(column_name: str, file_name: str, start: str, end: str):

    df_raw = pd.read_excel(
        Path(__file__).parent / "data" / DATA_MONTHLY_XLSX,
        sheet_name="Monthly Prices",
        header=4,
        index_col=0
    )

    rice = df_raw[column_name].copy()
    rice.index = parse_world_bank_dates(df_raw.index)
    rice = rice[rice.index.notna()]
    rice = rice.astype(float)
    rice.name = "rice_thai5_usd_mt"

    rice = rice.loc[start : end]
    rice = rice.resample("MS").mean()

    output_file_path = Path(__file__).parent / "data" / file_name
    rice.to_csv(output_file_path, header=True)
    return rice

