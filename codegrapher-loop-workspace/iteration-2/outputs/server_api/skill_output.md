# Skill Output — Server_Side/api/app.py

**Diagram type:** sequenceDiagram — FastAPI request routing flow with dependency injection and database operations

**Graph files read:** toc.json, sub/main_Server_Side_api_app.json

```mermaid
sequenceDiagram
    actor Client
    participant FastAPI as FastAPI<br/>Routing
    participant CORS as CORS<br/>Middleware
    participant Router as Router<br/>Handler
    participant DepInjection as Dependency<br/>Injection
    participant get_db as get_db()
    participant DatabaseUtil as DatabaseUtility
    participant DB as PostgreSQL<br/>Database
    participant Response as Response<br/>Handler

    Client->>FastAPI: HTTP Request
    FastAPI->>CORS: Check CORS policy
    CORS->>FastAPI: Allow request
    FastAPI->>Router: Match route + get handler

    alt Health Check Endpoint
        Router->>DepInjection: health_check()
        DepInjection->>get_db: Request DB session
        get_db->>DatabaseUtil: Create connection
        DatabaseUtil->>DB: Ping/Query
        DB-->>DatabaseUtil: Response
        DatabaseUtil-->>get_db: Session ready
        get_db-->>DepInjection: Session injected
        DepInjection-->>Router: Return HealthCheckResponse
    else Recipe Query Endpoint
        Router->>DepInjection: anonymous_recipe_query()
        DepInjection->>get_db: Request DB session
        get_db->>DatabaseUtil: Create connection
        DatabaseUtil->>DB: Query recipes
        DB-->>DatabaseUtil: Recipe results
        DatabaseUtil-->>get_db: Data returned
        get_db-->>DepInjection: Session injected
        DepInjection->>Router: Process AnonymousQueryRequest
        Router->>Router: Consumes AnonymousQueryRequest
        Router->>Response: Build RecipeSummary list
        Response->>Response: Build AnonymousQueryResponse
    else Advanced Search Endpoint
        Router->>DepInjection: advanced_recipe_search()
        DepInjection->>get_db: Request DB session
        get_db->>DatabaseUtil: Create connection
        DatabaseUtil->>DB: Execute advanced query
        DB-->>DatabaseUtil: Filtered results
        DatabaseUtil-->>get_db: Data returned
        get_db-->>DepInjection: Session injected
        DepInjection->>Router: Process AdvancedSearchRequest
        Router->>Response: Build RecipeSearchResult list
        Response->>Response: Build AdvancedSearchResponse
    else Token Management Endpoint
        Router->>DepInjection: consume_tokens/get_token_balance()
        DepInjection->>get_db: Request DB session
        get_db->>DatabaseUtil: Create connection
        DatabaseUtil->>DB: Query/Update tokens
        DB-->>DatabaseUtil: Transaction result
        DatabaseUtil-->>get_db: Session closed
        get_db-->>DepInjection: Session injected
        DepInjection->>Response: Return TokenTransactionResponse
    else Recipe Submission Endpoint
        Router->>DepInjection: submit_recipe()
        DepInjection->>get_db: Request DB session
        get_db->>DatabaseUtil: Create connection
        DatabaseUtil->>DB: Insert recipe + validate
        DB-->>DatabaseUtil: Insertion result
        DatabaseUtil-->>get_db: Session closed
        get_db-->>DepInjection: Session injected
        DepInjection->>Router: Call calculate_submission_tokens()
        Router->>Response: Build RecipeSubmissionResponse
    end

    Response-->>FastAPI: JSON response
    FastAPI-->>Client: HTTP 200/Error response
```

**Nodes:** Client, FastAPI, CORS Middleware, Router Handler, Dependency Injection, get_db, DatabaseUtility, PostgreSQL Database, Response Handler, health_check, anonymous_recipe_query, advanced_recipe_search, consume_tokens, get_token_balance, submit_recipe, calculate_submission_tokens, HealthCheckResponse, AnonymousQueryRequest, AnonymousQueryResponse, RecipeSummary, AdvancedSearchRequest, AdvancedSearchResponse, RecipeSearchResult, TokenTransactionResponse, RecipeSubmissionRequest, RecipeSubmissionResponse

**Edges:**
- health_check --defines--> get_db
- get_db --calls--> DatabaseUtility.connect
- DatabaseUtility --calls--> PostgreSQL.query
- anonymous_recipe_query --consumes--> AnonymousQueryRequest
- anonymous_recipe_query --calls--> RecipeSummary
- advanced_recipe_search --consumes--> AdvancedSearchRequest
- advanced_recipe_search --calls--> AdvancedSearchResponse
- advanced_recipe_search --calls--> RecipeSearchResult
- consume_tokens --calls--> DatabaseUtility.update
- get_token_balance --calls--> DatabaseUtility.query
- submit_recipe --consumes--> RecipeSubmissionRequest
- submit_recipe --calls--> calculate_submission_tokens
- calculate_submission_tokens --consumes--> RecipeSubmissionRequest
