from src.repository.yf_client import download_tickers


def test_yf_client():
    start = "2019-01-01"
    end = "2024-12-31"

    fx_tickers = {
        "EURUSD=X": "eur_usd",
        "EURGBP=X": "eur_gbp",
    }
    result = download_tickers(fx_tickers, start, end)
    print(result)
