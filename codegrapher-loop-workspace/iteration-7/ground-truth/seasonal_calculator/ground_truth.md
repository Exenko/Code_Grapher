# Ground Truth — seasonal_calculator.py — classDiagram

## Metadata
- GT node count: 2
- GT edge count: 0

## Mermaid Diagram

```mermaid
classDiagram
    class Hemisphere {
        <<enumeration>>
        NORTHERN
        SOUTHERN
        BOTH
    }

    class SeasonalCalculator {
        -db_path: str
        -server_url: str
        -reference_data_max_age: int
        +__init__(db_path: str, server_url: str)
        +_get_connection()
        +fetch_seasonal_buckets_from_server() bool
        +fetch_climate_seasonality_from_server() bool
        +cache_reference_data() bool
        +get_reference_data_age() Optional[int]
        +get_stale_notification() Optional[str]
        +calculate_seasonal_bucket(climate_zone: str, date: Optional[datetime]) Optional[int]
        +get_seasonal_transition_dates(climate_zone: str) List[Dict]
        +get_next_seasonal_transition(climate_zone: str, date: Optional[datetime]) Optional[Dict]
        +compile_seasonal_buckets_for_query(household_id: int) List[int]
        +initialize_for_household(household_id: int, climate_zone: str) bool
        +update_seasonal_bucket(household_id: int) bool
        +get_bucket_name(bucket_id: int) Optional[str]
        +get_household_climate_zone(household_id: int) Optional[str]
        +get_household_seasonal_context(household_id: int) Optional[Dict]
    }
```

## Class Definitions

**Hemisphere** (Enum): Three members — NORTHERN ("northern"), SOUTHERN ("southern"), BOTH ("both"). No locally-defined class fields.

**SeasonalCalculator**: Instance fields in `__init__`: `db_path: str`, `server_url: str`, `reference_data_max_age: int` (all primitives). The `Hemisphere` enum is defined in this file but never used as a declared field type.

## Edge Definitions

**None.**

- Hemisphere enum members have primitive string values — no local class references.
- SeasonalCalculator instance fields are all primitive types (str, int).
- `Hemisphere` is never used as a declared field type in SeasonalCalculator (only as a method annotation type if at all).
- No edges drawn: edge rule requires a field whose declared type IS the local class, not merely a related class used in methods.
