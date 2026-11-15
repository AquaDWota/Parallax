# Optional dated context for the Kelly model

Real context inputs go in `data/kelly-context.json`, a JSON list. No example numbers or fictional observations are supplied or fitted.

Each record needs:

- `building_id`: existing identifier such as P838391, assigned to the correct geography using a verified geographic crosswalk.
- `reference_date`: ISO date identifying the end of the measured period.
- `available_date`: actual public release date, not the reference period. Must be on/before the prediction date.
- `source_url`: supporting primary-source URL.
- Optional `employment_growth_yoy`: year-on-year employment growth, in percentage points (e.g. a reported 2% growth is encoded as 2, not 0.02).
- Optional `net_domestic_migration_per_1000`: domestic in-movers minus out-movers, divided by population and multiplied by 1,000.

Include the geography name and geographic level as extra fields for review. Do not use CoStar countyId as Census FIPS. Revisions and historical release vintages need review to avoid future-information leakage. Annual migration is broad context, not direct evidence of a tenant departure.

A feature is fitted only when at least 10 training events have a real, eligible value. Missing test values use training-based preprocessing. The model reports which external variables were actually fitted. A single regional observation copied to many buildings is still one contextual observation, not many independent samples.
