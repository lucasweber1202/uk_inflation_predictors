# Point-in-time semantics

The purpose of this repository is that a backtest run against it can be told,
honestly, what was knowable at a past instant. This document states exactly what
that guarantee covers and where it stops.

## Why `vintage_date` is not enough

`time_series.vintage_date` records when *this collector* stored a version of an
observation. On a historical backfill every row is stamped with the collection
day, so twenty-three years of road fuel prices all carry the same
`vintage_date`. A naive as-of query over `time_series` alone would conclude that
the entire history became available at once, which is false, and would happily
serve a 2003 observation to a query asking what was known in 2003 — or refuse
every observation in a query asking what was known last month.

`availability` exists to answer the separate question: **when did this stored
vintage actually become knowable from the source, and how do we know?**

## `availability_basis`

One row per `(series_id, reference_date, vintage_date)`, carrying
`release_date`, `available_at`, `availability_basis` and `source_snapshot_id`.
The basis vocabulary is closed and ordered from strongest to weakest evidence:

| Basis | Meaning | Point-in-time? |
|---|---|---|
| `official_timestamp` | The source stamped a machine-readable publication timestamp this observation is attributable to. | **Yes** |
| `official_date` | The source published a release date, but only to day precision. | **Yes** |
| `archived_release` | Recovered from an archived copy of the release rather than the live source. | **Yes** |
| `first_seen` | Not published with a release date, but this collector watched the observation appear between two runs, so `available_at` is a true upper bound. | **Yes** (conservative) |
| `inferred` | Derived from the source's *observed* release rule, not from anything the source published. | **No** |
| `unknown` | No defensible basis exists. | **No** |

**A historical availability date is never invented.** Where the source does not
let availability be established, that is recorded as `inferred` or `unknown`
rather than dressed up as a release date.

`inferred` and `unknown` are **excluded by default** from `get_series_as_of`.
Including them requires passing an explicit `bases` argument, so reconstructed
availability can never be mistaken for evidence by accident. `unknown` also
carries `available_at` far in the future, so even an explicit query with a
permissive basis set will not admit it before an as-of instant in this century.

## How a release is attributed

Both v0.1 sources are GOV.UK pages carrying an official change history: a list
of timestamps at which the page was updated. Every change-history entry dated
after a reference period describes a page state that **contained** that period,
so the earliest such entry is the earliest instant the observation can be
*proven* to have been available.

Where the change history is sparse, that proof lands on a later release than the
true one. The recorded availability is then **late rather than early**. This
understates the information set, which is the safe direction: it can make a
backtest look slightly less informed than reality, but it can never leak a
look-ahead.

Attribution is bounded by `min_lag_days` and `max_lag_days` per source, so a
reference period from before the change history began is not attached to the
first surviving entry years later. Beyond that bound the source's observed
release rule produces an `inferred` instant.

## Measured coverage of the v0.1 sources

| Source | `official_timestamp` | `inferred` | Notes |
|---|---|---|---|
| `defra_fruit_veg` | 17,171 (100%) | 0 | The page's change history begins 2017-01-05, before the first observation on 2017-11-03, so every observation is attributable. |
| `desnz_road_fuels` | 1,566 (21%) | 5,724 (79%) | The change history reaches back only to 2013-09-23, while the data starts 2003-06-09. |

### The DESNZ limitation, stated plainly

DESNZ road fuel prices have **no usable point-in-time history before
2013-09-23**, and coverage between 2013 and 2021 is partial rather than
complete: GOV.UK's change history does not list every weekly update, so weeks
with no release entry within the attribution window also fall back to
`inferred`.

The inferred rule used is the source's observed schedule — published the day
after the Monday reference date, stamped at 12:00 UTC to avoid claiming
pre-publication timing. **This is a reconstruction, not evidence.** A backtest
that needs genuine point-in-time fidelity for road fuels should either restrict
itself to the default evidence-backed set (which starts in 2013 and is patchy
until the collector's own `first_seen` observations accumulate) or treat the
pre-2013 period as non-point-in-time and say so.

Two routes would improve this and are deferred to a later round: recovering
release dates from the UK Government Web Archive (which would qualify as
`archived_release`), and simply accumulating `first_seen` evidence as the
collector runs forward week by week.

## Snapshots

Both sources replace their published file in place; nothing in either URL
distinguishes one edition from the next. Each downloaded file is therefore
hashed, and the SHA256 **is** the snapshot identity. Every availability row
names the snapshot its observation was parsed from.

A source that silently rewrites its own history appears as a **new snapshot row
next to the old one**, never as an overwrite, so the substitution is visible
after the fact. Raw files are written to a gitignored local directory and are
never committed; the table records the path and digest, so relocating the bytes
to object storage later changes `raw_path` only. No cloud-storage solution is
imposed at this stage.

## The guarantee, and its test

`get_series_as_of(series_id, as_of)` may never return an observation or vintage
whose `available_at` is later than `as_of`. The availability filter is applied
*before* the latest-vintage ranking, so a later revision of a period cannot leak
in and mask the vintage that was actually current at `as_of`. The result is
re-checked in Python before it is returned, because a silent look-ahead is the
one failure this repository must not ship.

This is covered by explicit tests in `tests/test_as_of.py`, including a
revision-leak test and a test that `inferred` and `unknown` do not answer by
default.
