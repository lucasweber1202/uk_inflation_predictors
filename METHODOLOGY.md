# Methodology

## Question

Every experiment asks whether one predictor feature adds pseudo-out-of-sample
information beyond the target's own dynamics. In-sample correlation is
exploratory evidence only and is never labelled predictive performance.

## Targets

The primary dependent variable is monthly CPI inflation by opening, computed
from the official ONS index level. Year-on-year inflation is an optional
robustness target. `target_registry.csv` records the native ONS identifier and
verification status. Pending targets are skipped, never guessed.

## Information sets

For target month `m`, the forecast instant is the first persisted official CPI
release timestamp for `m` less 10, 5 or 1 calendar days. This creates T-10,
T-5 and T-1 information sets without inventing a fixed day of month. The
feature builder first filters raw vintages at that instant and only then
aggregates them.

## Features

Transformations are selected for the economic nature of each source:

- DESNZ pump prices: monthly mean/last, MTD, trailing 7/14/21-day mean, MoM and YoY;
- DEFRA wholesale food: monthly mean/median and coherent product groups;
- DEFRA milk/API and HMRC: last known monthly level, MoM and YoY, respecting release lag;
- DfT: last known quarterly value/change; it is primarily explanatory/validation evidence;
- Elexon: provider-specific daily mean/median/min/max/volatility followed by monthly or MTD aggregation.

Elexon APX, N2EX and combined specifications remain distinct. A weighted price
is `sum(price_sp * volume_sp) / sum(volume_sp)` within provider/day. It is used
only with non-negative reported volume. Sparse N2EX observations are not given
the same implicit weight as a complete APX day.

## Benchmarks and model

Mandatory benchmarks are historical mean, last observation, and AR orders 1,
2, 3, 6 and 12. The first predictor model is AR(p) plus exactly one predictor
feature, with predictor lags 0–3. Ordinary least squares includes an intercept.

Evaluation uses an expanding window. Predictor, feature, lag, AR order, cutoff
and PIT mode remain explicit experiment dimensions. Minimum train and OOS
thresholds are configured before the run. A configuration with too little data
does not receive a ranking.

## Metrics

The engine reports RMSE, MAE, bias and directional accuracy. Incremental value
is reported as `1 - model_metric / benchmark_metric`; positive is improvement,
negative is deterioration. Full results are retained—never only a winning row.

## Limitations

Alcohol starts in August 2023 and cannot support strong conclusions yet.
Strict Elexon history is tiny because the upstream API supplies no historical
publication timestamp. DfT is released with a long lag. These are data/sample
constraints, not reasons to relax PIT rules.
