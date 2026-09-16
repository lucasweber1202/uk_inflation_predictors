# Point-in-time research policy

## Modes

`strict` admits only `official_timestamp`, `official_date`,
`archived_release`, and `first_seen`. `reconstructed` additionally admits
`inferred`. `unknown` is admitted by neither mode. Every output row carries
`pit_mode`; modes are ranked separately.

For each `(series_id, reference_date)`, selection first removes rows whose
`available_at` exceeds the forecast instant and then selects the latest
remaining vintage. Reversing those operations would leak a future revision.

## Feature safety

Aggregation follows PIT selection. Thus an April weekly observation published
after an April 10 cutoff cannot enter April MTD. The same rule applies to a
back-revised historical observation: it becomes eligible only at the revision's
own availability timestamp.

## Target release cutoffs

T-10/T-5/T-1 are calculated from the target's first persisted official release
timestamp. If the target extract cannot support a release calendar, the run
fails rather than substituting a convenient publication day.

## Forecast-origin execution

The runner iterates target months. For each month it derives T-10/T-5/T-1 from
the persisted first-release calendar, independently selects target and
predictor vintages at that timestamp, builds the requested feature, fits on the
then-available history, and emits the timestamp and cutoff on every forecast.
There is no global modern as-of reconstruction.

## Automated leakage tests

The suite contains adversarial rows for a future reference period, a future
vintage, a future revision of an old period, and an inferred historical row.
It also checks MTD and trailing windows at a mid-month cutoff. These tests are
intended to fail if filtering and vintage ranking are accidentally reordered.
