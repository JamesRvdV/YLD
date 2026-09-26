from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


def build_model(numeric, categorical):
    preprocessing = ColumnTransformer([
        ('numeric', SimpleImputer(strategy='median', keep_empty_features=True), numeric),
        ('category', OneHotEncoder(handle_unknown='ignore'), categorical),
    ])
    return Pipeline([
        ('features', preprocessing),
        ('model', RandomForestRegressor(n_estimators=80, min_samples_leaf=5,
                                        max_depth=16, random_state=42, n_jobs=-1)),
    ])
