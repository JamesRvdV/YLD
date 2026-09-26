import numpy as np
import pandas as pd

QUANTITIES = ['food_sold_kg', 'food_prepared_kg', 'food_waste_kg']


def load_data(path):
    df = pd.read_csv(path, dtype={'restaurant_id': str})
    required = ['date', 'restaurant_id', *QUANTITIES]
    missing = set(required) - set(df.columns)
    if missing:
        raise ValueError(f'Missing columns: {sorted(missing)}')
    if df[required].isna().any().any():
        raise ValueError('Required fields contain missing values.')
    df['date'] = pd.to_datetime(df['date'], errors='raise').dt.normalize()
    if df.empty or df['date'].isna().any():
        raise ValueError('Empty data or invalid dates.')
    if df.duplicated(['restaurant_id', 'date']).any():
        raise ValueError('Expected one row per restaurant and date; duplicate keys found.')
    if 'restaurant_name' in df.columns:
        df['restaurant_name'] = df.restaurant_name.fillna('').astype(str).str.strip()
        names_per_id = df[df.restaurant_name != ''].groupby('restaurant_id').restaurant_name.nunique()
        if (names_per_id > 1).any():
            raise ValueError('Each restaurant_id must map to one restaurant_name.')
    for col in QUANTITIES:
        df[col] = pd.to_numeric(df[col], errors='raise')
        if not np.isfinite(df[col]).all() or (df[col] < 0).any():
            raise ValueError(f'{col} must contain finite nonnegative numbers.')
    if (df.food_sold_kg > df.food_prepared_kg + 0.02).any():
        raise ValueError('Sold quantities exceed prepared quantities.')
    df = df.sort_values(['restaurant_id', 'date']).reset_index(drop=True)
    gaps = df.groupby('restaurant_id').date.diff().dt.days.dropna()
    report = {
        'rows': len(df), 'restaurants': df.restaurant_id.nunique(),
        'unique_dates': df.date.nunique(), 'start': str(df.date.min().date()),
        'end': str(df.date.max().date()),
        'gap_days_counts': {str(k): int(v) for k, v in gaps.value_counts().items()},
        'balance_mismatch_rows': int(((df.food_prepared_kg - df.food_sold_kg - df.food_waste_kg).abs() > 0.03).sum()),
        'possible_censored_rows': int((df.food_prepared_kg - df.food_sold_kg <= 0.02).sum()),
        'categories': {c: sorted(df[c].dropna().astype(str).unique().tolist()) for c in
                       ['center_type', 'dominant_category', 'dominant_cuisine'] if c in df},
    }
    return df, report


def restaurant_labels(df):
    """Readable selector labels, retaining IDs to distinguish locations."""
    labels = {}
    for restaurant_id, group in df.groupby('restaurant_id', sort=True):
        row = group.iloc[0]
        name = row.get('restaurant_name', '')
        if isinstance(name, str) and name.strip():
            display = name.strip()
        else:
            details = []
            for column, prefix in [('center_type', ''), ('city_code', 'City '),
                                   ('dominant_cuisine', '')]:
                value = row.get(column)
                if pd.notna(value) and str(value).strip():
                    details.append(f'{prefix}{value}')
            display = ' · '.join(details) or 'Restaurant'
        labels[f'{display} (ID {restaurant_id})'] = restaurant_id
    return labels
