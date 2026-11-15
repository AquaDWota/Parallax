# Parallax analysis limitations

Prepared November 14, 2026. This document describes the current local real-data analysis, not every possible future app run. Counts and results must be refreshed if the database, filters, imagery, or outcome rules change.

## Version scope update

The limitations and numerical findings below describe the original baseline analysis. A separate notebook section now evaluates pinned main commit `600aa82143d127833bdd0cc724cfa31646febac4` using the existing car-count measurements. That updated-code run retains 548 renewal events; its occupancy estimate is 2.59 (95% interval 0.45 to 4.73; see the saved report for exact values) and its 20-shuffle occupancy placebo passes. The renewal regression still does not converge, and temporal prediction AUC with parking is 0.477. These updated results must not be mixed with baseline sample counts. The new CV detector has not been applied to the existing measurements in this comparison. See the notebook's versioned rerun section and reports under `data/results/version-comparisons/`.

## What the original baseline evidence supports

The notebook reproduces the default dashboard calculations and audits their inputs. Reproducibility does not establish that the labels are correct, that an association is causal, or that a model predicts future renewals reliably.

The current evidence suggests a possible parking-occupancy association worth investigating. It does not establish reliable lease-renewal prediction. The original full renewal regression did not converge and should not be interpreted as a validated inferential model.

## 1. Only a selected subset enters the statistical analysis

The findings do not use every supplied property or tenancy. These populations have different units and cannot be treated as one continuous row-level funnel.

| Population | Count | What it represents |
|---|---:|---|
| Raw CoStar properties | 3,339 | Selected properties in the Houston and Los Angeles research markets |
| Raw tenancy records | 74,093 | Current and historical occupancies, including those without a lease deal |
| Tenancies containing lease deals | 41,781 | Recorded deal information, often incomplete |
| Properties with recorded lease deals | 1,697 | Not every property has a deal |
| Prepared properties with a resolved location | 2,843 | Location resolved through the preparation script's company-address joins |
| Prepared expiry events with inferred outcomes | 4,314 | Events passing date, location, and classification rules |
| Properties selected for Vexcel collection | 211 | Imaging candidates; not a random sample of the 3,339 properties |
| Properties in the app database | 209 | Two selected properties returned no matching collections |
| Expiry events initially in the app's analysis window | 1,686 | Events at retained properties, before the parking/usage exclusions below |
| Eligible renewal-model events | 515 | Events with the required parking eligibility and prior usage |
| Occupancy-model observations | 854 across 92 buildings | Building/capture observations, not 854 independent buildings |

For the 1,686 expiry events, the pipeline excludes 871 under its parking/unmeasurable classification and 300 without usable prior usage, leaving 515. The parking exclusion includes a low-car-count heuristic; it does not independently prove that a property has garage parking.

The imaging selection favors measurable parking and excludes apartment properties from imaging. Properties without located tenant records, observable surface parking, baseline imagery, or usable historical observations are underrepresented. Counts therefore describe a selected sample, not either entire metropolitan market or all leases in the kit. The direction and size of selection bias have not been quantified.

## 2. Renewal outcomes are inferred rather than contract-verified

The preparation script combines occupancy end dates, expiration-reason codes, follow-on occupancy records, and area changes. It does not directly observe every signed renewal contract.

Confirmed findings in the 4,314 prepared events:

- All 4,314 labels were reproduced using the existing rules. This validates implementation agreement only.
- 399 events are labeled renewed because their occupancy end date is missing.
- 1,685 events have unknown tenant identifiers.
- 110 events use a follow-on match involving an unknown tenant ID. Unknown IDs can match other unknown tenants in the same building.

Matching searches can include starts before or after the earlier occupancy end, and the first matching record in file order is used. A follow-on record can therefore be ambiguous. The app counts renewed and expanded as success but downsized as failure: this is closer to retention of all recorded space than a general tenant-retention rate.

**Needed:** manually inspect examples, distinguish explicit evidence from assumptions, and repeat analyses with uncertain labels excluded and downsizing counted as retention. No reasonable relabeling should be selected solely because it strengthens the desired hypothesis.

## 3. The snapshot is not a complete historical panel

The supplied files combine historical records with information current at export time. They do not provide an independently observed annual record of every building or tenant. A missing event is not evidence that no event happened.

Preparation fixes its reference date at November 1, 2026, accepts expirations from January 1, 2016, and requires at least 90 days since expiry. The renewal analysis further filters expirations from March 1, 2019 inclusive to October 1, 2026 exclusive. Preparation makes the effective latest date earlier. Older signing dates and future contractual end dates do not define a uniform observation period.

Open records can be stale. Newer expirations have less follow-up, and recent years are partial. Changes in observed annual renewal rates can reflect reporting, composition, or outcome-label rules rather than true changes in the market.

## 4. Occupancy measures have numerator and denominator problems

Occupancy is calculated as the sum of active tenancy square feet divided by the app's building area. It is not a separately verified vacancy/occupancy survey.

- All 854 independently recalculated occupancy values matched the app.
- 122 observations exceed 100% before capping; 71 exceed 120%.
- The app caps occupancy at 120%, which changes extreme values without resolving their causes.
- 1,133 known-tenant records at retained buildings overlap an earlier record for the same tenant/building. These are review flags, not automatically duplicate leases; legitimate multiple spaces can overlap.
- The building-area denominator can be reported rentable area, maximum tenant area, or a 50,000-square-foot fallback. Their meanings differ.

**Needed:** inspect extreme cases, distinguish concurrent suites from duplicate or renewal records, reconcile area definitions, and report sensitivity to denominator choices and capping. Do not interpret values over 100% as literal physical occupancy.

## 5. Rent controls contain missingness and inconsistent units

In the 515 eligible model events, 398 have missing or nonpositive recorded contract rent before the loader's filling step. The loader substitutes a median or fallback. Complete-looking model fields do not mean complete source measurements.

The processed rent CSV does not retain the original rate-basis and amount-type information alongside the rate. Monthly/yearly, per-area/total, currency, and expense-service terms must be checked in the original records before comparisons. The regression's rent-ratio control inherits these concerns.

**Needed:** recover and normalize source units, retain missingness indicators, and compare fits with and without the rent control. The current processed rent column is not a validated lease-price time series.

## 6. The original full renewal regression did not converge

The direct statsmodels refit returned `converged=False` and a maximum-likelihood optimization warning. Four industry categories contain only one or two events with a single outcome, which are possible contributors to separation. This is not a complete diagnosis.

Although the reproduced usage odds ratio is approximately 0.993, its reported confidence interval and p-value are not validated inference while the fit has not converged. Matching the dashboard's estimates does not remove this problem. Building-clustered standard errors do not repair nonconvergence.

**Needed:** diagnose separation and specification, justify any rare-category grouping, evaluate a simpler prespecified model or regularization, and verify convergence. Changes should target stable estimation, not a desired significance level.

## 7. Current prediction performance does not establish useful prediction

The original temporal test trains on 314 events from 2019-2022 and tests on 201 events from 2023-2026. Test AUC is 0.435 for the building-attribute baseline and 0.481 after adding parking. Both are below the 0.5 chance-ranking reference. A positive lift over a weak baseline is not enough to establish predictive usefulness.

The separate regularized diagnostic model with parking has test AUC about 0.494. Its Brier score and log loss are worse than the constant training-rate baseline in this run. These alternative models are not the original dashboard model.

Additional confirmed limitations:

- 45 buildings and 9 known tenant-location IDs appear in both train and test. This is a later-event test, not a new-building test.
- The observed success rate changes from about 24.2% in training to 41.8% in testing.
- Retrospectively prepared usage features, label inference, and eligibility are reused. This is not a complete point-in-time backtest.
- Choosing the best lead time using test AUC would use the test set for selection. A separate final holdout is needed.
- Performance confidence intervals and externally collected validation data are not yet provided.

**Needed:** point-in-time feature reconstruction, appropriate temporal and building-disjoint tests, probability calibration, performance uncertainty, and comparison with strong lease-only and simple constant baselines. Do not deploy these probabilities as validated renewal forecasts.

## 8. Occupancy evidence and placebo checks are inconclusive

The current occupancy model estimates about 2.23 parking-index points per 10 percentage points of occupancy, with a 95% confidence interval of approximately -0.18 to 4.64. The interval includes zero. The occupancy placebo check fails in both the saved app overview and the notebook rerun; their shuffled summaries differ because the app uses 20 shuffles and the notebook uses 30.

The renewal placebo passes its implemented heuristic, but this does not override nonconvergence, weak prediction, or uncertain labels. The placebo shuffles usage and trend separately within submarkets at the event level, rather than preserving complete building histories.

Lead-time, subgroup, COVID-exclusion and sharp-drop analyses are exploratory. They can use different samples, encounter sparse groups or fitting failures, and involve multiple comparisons without a multiple-testing adjustment.

## 9. Additional limitations to investigate with the imagery/model teammates

These are plausible risks requiring further checks; the audit has not measured their magnitude.

| Potential limitation | Why it matters | Suggested check |
|---|---|---|
| Parking-lot geometry and tenant attribution | A shared lot may serve several buildings or businesses | Manually inspect matched parcels, entrances, lots and neighboring uses |
| Detection error | Missed cars, false detections, shadows, occlusion and image quality affect counts | Label a representative image sample; measure count error by condition |
| Capture timing | Time of day, weekday, holidays and season change parking independently of tenants | Inspect actual capture times and restrict/adjust comparable observations |
| Sparse or irregular captures | Annual or uneven imagery cannot resolve monthly lease events accurately | Report capture gaps and sensitivity to predictor windows |
| Building versus tenant scale | A small tenant may have little influence on building-wide parking | Compare tenant-area-share groups using prespecified, sufficiently large samples |
| Parking capacity estimates | Estimated stalls and changing lot configurations affect normalization | Validate capacity against imagery and known counts across dates |
| Peer and baseline construction | Neighbor selection and baseline years can change the usage index | Test reasonable alternative peers/baselines without test-set tuning |
| Confounding | Industry, working patterns, location, building quality and economic conditions can affect both measures | Specify plausible confounders and distinguish association from causation |
| Repeat-event dependence and geographic clustering | Repeated tenants/buildings and nearby properties reduce independent information | Use suitable clustering/resampling and grouped validation |
| Label and feature availability at prediction time | Facts learned later can inflate apparent forecast performance | Record when each input would have been known; audit leakage |
| Source refresh and research coverage | A recent export can still contain stale or unevenly researched records | Inspect freshness/verification fields where available |

## Recommended presentation wording

> We evaluated relationships between aerial parking activity, estimated occupancy, and inferred lease-renewal outcomes in a selected Houston/Los Angeles sample. We reproduced the dashboard calculations. The occupancy association is suggestive but inconclusive, and the current models do not establish useful renewal prediction. Outcome-label assumptions, sample selection, occupancy measurement issues, and nonconvergence limit stronger conclusions.

## Priorities before strengthening the claims

1. Manually review renewal labels and problematic occupancy records against the source data.
2. Validate parking boundaries, car counts, and capture comparability with the imagery teammate.
3. Correct rent units/missingness treatment and obtain a converged, defensible model.
4. Rebuild a point-in-time evaluation with simple baselines, grouped tests, and uncertainty estimates.
5. Refresh dashboard text to show the sample sizes, exclusions and model status accurately.

## Evidence and reproducibility

- [Lease Analysis notebook](costar-hackathon-kit/Lease%20Analysis.ipynb): source audits, EDA, arithmetic checks, model refits and predictions.
- [Extended validation results](data/results/lease-validation/extended-validation-results.json): current saved statistical diagnostics.
- [Occupancy audit](data/results/lease-validation/occupancy-audit.csv): per-observation numerator, denominator and agreement checks.
- [Prediction metrics](data/results/lease-validation/prediction-metrics.csv): alternative-model and constant-baseline comparison.
- [Earlier run summary](data/real/run_summary.json) and timestamped files under `data/results/`: historical reproduced outputs.
- [Preparation rules](backend/scripts/prepare_costar.py), [event selection](backend/parallax/events.py), [model calculations](backend/parallax/analysis.py), and [occupancy calculations](backend/parallax/occupancy.py).

This document does not change any models, labels, dashboard outputs or source records. Raw datasets and generated result files may not be included in a Git checkout; links to local evidence require those files to be shared separately.
