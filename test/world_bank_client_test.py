from src.repository.world_bank_client import get_by_ticker

def test():
    START = "2019-01-01"
    END = "2024-12-31"
    rice_thai5 = get_by_ticker("Rice, Thai 5% ", 'rice_thai5.csv', START, END)
    print(rice_thai5)
