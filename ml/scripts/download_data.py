from pathlib import Path
from urllib.request import urlretrieve

URL = 'https://raw.githubusercontent.com/mehedinaeem/restaurant-food-management-ml/main/data/processed/restaurant_food_waste_final_dataset.csv'

if __name__ == '__main__':
    path = Path('data/raw/restaurant_data.csv')
    path.parent.mkdir(parents=True, exist_ok=True)
    urlretrieve(URL, path)
    print(f'Saved {path}')
