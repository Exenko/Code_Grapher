# Ground Truth — Server_Side/api/app.py

**Diagram type:** sequenceDiagram — Shows temporal flow of HTTP request through FastAPI routing, dependency injection, database operations, and response serialization.

**Key files read:** Server_Side/api/app.py, Server_Side/api/routes/sync.py, Server_Side/api/routes/ingredients.py, Server_Side/db/database_utility.py

```mermaid
sequenceDiagram
    participant Client
    participant FastAPI as FastAPI<br/>app.py
    participant Router as Router<br/>(sync/ingredients)
    participant Middleware as CORS<br/>Middleware
    participant Depends as Depends<br/>get_db()
    participant DB as DatabaseUtility<br/>(pg_database_utility)
    participant Database as PostgreSQL/<br/>SQLite DB

    Client->>FastAPI: HTTP Request<br/>(GET/POST)
    FastAPI->>Middleware: passes through
    Middleware->>FastAPI: CORS validated
    FastAPI->>Router: route matching

    alt Routing Decision
        Router->>Router: match endpoint path
    end

    Router->>Depends: invoke dependency
    Depends->>DB: get_database()
    DB->>Database: connect()<br/>(SQLite only)
    Database-->>DB: connection
    DB-->>Depends: DatabaseUtility instance
    Depends-->>Router: injection complete

    alt Account/Query Endpoints
        Router->>Database: execute(SQL query)
        Database-->>Router: fetchone()/fetchall()
        Router->>Router: build response models
    end

    alt Sync/Ingredients Routes
        Router->>Database: execute(DataVersions/MasterIngredients)
        Database-->>Router: JSON-serializable rows
        Router->>Router: parse JSON, build DTO
    end

    Router->>Database: commit()/close()
    Database-->>Router: transaction finalized

    Router->>FastAPI: return dict/model
    FastAPI->>Client: HTTP Response<br/>(JSON)
```

**Nodes:** Client, FastAPI app.py, Router (sync/ingredients), CORS Middleware, Depends (get_db), DatabaseUtility, PostgreSQL/SQLite DB

**Edges:**
- Client --HTTP GET/POST--> FastAPI
- FastAPI --passes through--> CORS Middleware
- CORS Middleware --CORS validated--> FastAPI
- FastAPI --route matching--> Router
- Router --dependency invoke--> Depends
- Depends --get_database()--> DatabaseUtility
- DatabaseUtility --connect(SQLite only)--> Database
- Database --connection--> DatabaseUtility
- DatabaseUtility --injection complete--> Depends
- Depends --return instance--> Router
- Router --execute(SQL)--> Database
- Database --fetchone()/fetchall()--> Router
- Router --build response models--> Router
- Router --commit()/close()--> Database
- Database --transaction finalized--> Router
- Router --return dict/model--> FastAPI
- FastAPI --HTTP Response (JSON)--> Client
