# Restaurant cover baseline

This experiment predicts the **next service's indoor covers** from its weekday and
previously recorded cover counts. It uses ridge regression with a fixed penalty of
20. The features are the weekday, last completed service, means of the last 7 and
28 completed services, and the mean of the last 4 services on the same weekday.
No sales, reservations, future weather, or target-day counts are used as inputs.

## Data

The source is Maksym Pazuniak's public [restaurant sales forecasting repository](https://github.com/maks-p/restaurant_sales_forecasting),
specifically [`rest_1_covers_new.csv`](https://github.com/maks-p/restaurant_sales_forecasting/blob/master/csv/rest_1_covers_new.csv).
The source describes a Brooklyn restaurant's aggregated POS and reservation records
from 2017 through June 2019. Its repository carries an [MIT license](https://github.com/maks-p/restaurant_sales_forecasting/blob/master/LICENSE);
the upstream notice is included in [data/LICENSE.upstream](data/LICENSE.upstream).

The checked-in [data/restaurant_covers.csv](data/restaurant_covers.csv) keeps only
`date` and `inside_covers`. Thirteen source rows with an empty cover count were
excluded rather than interpreted as zero demand. The resulting 897 observed
services span 2017-01-02 to 2019-06-30. The source CSV SHA-256 was
`d323db5b50434f3d2107245784783356a5b7151f32cfd20ac73f1ae13accc5b3`;
the processed file's SHA-256 is stored in the model artifact.

## Train and use

From the repository root, with Python 3.9 or newer:

```bash
python3 ml/cover_baseline.py
```

This writes [cover_baseline.json](cover_baseline.json). No third-party Python
packages or network access are required. To use another CSV with the same columns,
pass `--data path/to/file.csv --output path/to/model.json`.

For a next-day forecast on the source restaurant:

```python
import json
from datetime import date
from pathlib import Path
from ml.cover_baseline import features, load_services, predict

history = load_services(Path("ml/data/restaurant_covers.csv"))
model = json.loads(Path("ml/cover_baseline.json").read_text())
estimate = predict(model, features(history, date(2019, 7, 1)))
print(round(estimate))
```

## Evaluation

The first 717 services (through 2018-12-30) train the evaluation model. The
last 180 (2018-12-31 through 2019-06-30) are held out in time. After every
held-out service, its true count becomes available for the following day's
one-step-ahead forecast. Continuous feature scaling is fit on training data
only. The comparison predicts the mean of the last four completed services on
the same weekday.

| Forecast | MAE (covers) | RMSE (covers) |
| --- | ---: | ---: |
| Ridge model | 10.58 | 20.01 |
| Same weekday mean | 12.06 | 21.33 |

After evaluation, the saved coefficients are refit on all 897 observed services
for future forecasts. The JSON records the holdout metrics from the earlier
evaluation fit. This is evidence for one restaurant and one-step forecasting,
not a measured improvement for other kitchens or YLD's existing planner.

## Higher-capacity model

To compare three tree ensembles with the ridge baseline and train the selected
model, install [uv](https://docs.astral.sh/uv/getting-started/installation/) and
use Python 3.11 or 3.12:

```bash
uv run --project ml/cover --locked python ml/compare_cover_models.py
```

The script uses the first 70% of services for model fitting, the next 10% for
tree-model selection, and the final 20% for a one-step-ahead test. Model
selection uses validation MAE only. The selected Extra Trees model is refit on
the first 80% before testing, then refit on the full dataset for the saved
[model artifact](cover_tree_model.joblib). Results and split dates are recorded
in [cover_model_comparison.json](cover_model_comparison.json).

| Model | Validation MAE | Final holdout MAE | Final holdout RMSE |
| --- | ---: | ---: | ---: |
| Extra Trees | 10.46 | 10.33 | 19.83 |
| Ridge | 10.74 | 10.58 | 20.01 |

The Extra Trees advantage was **0.25 covers MAE**. A paired bootstrap that
resamples calendar weeks gave a 95% interval of **-0.10 to 0.63 covers** for
the ridge-minus-tree MAE difference. That interval includes zero, so this
single-restaurant result does not establish a reliable gain. The tree model
also needs substantially more than YLD's current 14-service minimum to train
per workspace.

To forecast with the saved model, load the artifact using the pinned
scikit-learn version in `ml/cover/pyproject.toml` and `ml/cover/uv.lock`:

```python
import joblib
from datetime import date
from pathlib import Path
from ml.cover_baseline import features, load_services

history = load_services(Path("ml/data/restaurant_covers.csv"))
bundle = joblib.load("ml/cover_tree_model.joblib")
estimate = bundle["estimator"].predict([features(history, date(2019, 7, 1))])[0]
print(round(max(0, estimate)))
```
