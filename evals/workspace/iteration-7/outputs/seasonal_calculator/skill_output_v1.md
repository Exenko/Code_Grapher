# Skill Output v1 — seasonal_calculator.py — classDiagram

## Analysis

**Classes found:** Hemisphere (Enum), SeasonalCalculator

**Field types analyzed:**
- Hemisphere: NORTHERN (str value) → NO EDGE (enum member, not a field type reference)
- Hemisphere: SOUTHERN (str value) → NO EDGE
- Hemisphere: BOTH (str value) → NO EDGE
- SeasonalCalculator: db_path: str → NO EDGE (primitive)
- SeasonalCalculator: server_url: str → NO EDGE (primitive)
- SeasonalCalculator: reference_data_max_age: int → NO EDGE (primitive)

**Edges identified:**
None. SeasonalCalculator has only primitive instance fields. The Hemisphere enum exists in the file but is not used as a declared field type in SeasonalCalculator. No local class appears as a top-level declared field type in any class.

## Diagram

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
        +get_reference_data_age() Optional~int~
        +get_stale_notification() Optional~str~
        +calculate_seasonal_bucket(climate_zone: str, date: Optional~datetime~) Optional~int~
        +get_seasonal_transition_dates(climate_zone: str) List~Dict~
        +get_next_seasonal_transition(climate_zone: str, date: Optional~datetime~) Optional~Dict~
        +compile_seasonal_buckets_for_query(household_id: int) List~int~
        +initialize_for_household(household_id: int, climate_zone: str) bool
        +update_seasonal_bucket(household_id: int) bool
        +get_bucket_name(bucket_id: int) Optional~str~
        +get_household_climate_zone(household_id: int) Optional~str~
        +get_household_seasonal_context(household_id: int) Optional~Dict~
    }
```

## Notes
- Hemisphere enum present but never referenced as a field type
- SeasonalCalculator is a stateless handler (all DB state retrieved via SQL; no local class instances stored as fields)
- 0-edge result is consistent with the file having two unrelated types (Enum + service class)
