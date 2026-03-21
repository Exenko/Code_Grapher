# ingredients_routes — Skill Agent v1 Output

**Version:** v1
**Graph sources used:** cross_file edges to db_factory, files_touched
**Approach:** Two separate flows from two cross-file edge pairs. Validation alt-block for climate_zone per skill rules. DataVersions version-hash query appended to each route.

## Diagram

```mermaid
sequenceDiagram
    participant Client
    participant IngredientsRouter as IngredientsRouter
    participant db_factory as db_factory
    participant Database

    Note over IngredientsRouter: GET /api/ingredients/master

    Client ->> IngredientsRouter: GET /api/ingredients/master
    activate IngredientsRouter
    IngredientsRouter ->> db_factory: get_database()
    activate db_factory
    db_factory -->> IngredientsRouter: db connection
    deactivate db_factory
    IngredientsRouter ->> Database: SELECT * FROM MasterIngredients
    activate Database
    Database -->> IngredientsRouter: ingredient rows
    deactivate Database
    IngredientsRouter ->> Database: SELECT version_hash FROM DataVersions WHERE table_name='MasterIngredients'
    activate Database
    Database -->> IngredientsRouter: version hash
    deactivate Database
    IngredientsRouter -->> Client: 200 JSON {data: [...], version: hash}
    deactivate IngredientsRouter

    Note over IngredientsRouter: GET /api/ingredients/seasonality/{zone}

    Client ->> IngredientsRouter: GET /api/ingredients/seasonality/{climate_zone}
    activate IngredientsRouter
    alt climate_zone is invalid
        IngredientsRouter -->> Client: 400 Bad Request
    else climate_zone is valid
        IngredientsRouter ->> db_factory: get_database()
        activate db_factory
        db_factory -->> IngredientsRouter: db connection
        deactivate db_factory
        IngredientsRouter ->> Database: SELECT * FROM IngredientSeasonality WHERE climate_zone = ?
        activate Database
        Database -->> IngredientsRouter: seasonality rows
        deactivate Database
        IngredientsRouter ->> Database: SELECT version_hash FROM DataVersions WHERE table_name='IngredientSeasonality'
        activate Database
        Database -->> IngredientsRouter: version hash
        deactivate Database
        IngredientsRouter -->> Client: 200 JSON {data: [...], version: hash}
    end
    deactivate IngredientsRouter
```

## Counts
- **Actor count:** 4 (Client, IngredientsRouter, db_factory, Database)
- **Message count:** 19 total arrows
