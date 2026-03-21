# Skill Output v2 — Server_Side/api/app.py

**Diagram type:** sequenceDiagram — Shows the complete request/response flow through FastAPI endpoints with multiple handler types interacting with database dependencies.

**Graph files read:** toc.json, sub/main_Server_Side_api_app.json

```mermaid
sequenceDiagram
    actor Client
    participant FastAPI as FastAPI App
    participant CORS as CORS Middleware
    participant Router as Route Handler
    participant GetDB as get_db<br/>(Dependency)
    participant DB as Database<br/>(Session)
    participant Response as Response Builder

    Client->>FastAPI: HTTP Request
    FastAPI->>CORS: Process Request
    CORS->>Router: Route to Handler

    alt Health Check Endpoint
        Router->>GetDB: health_check() calls get_db()
        GetDB->>DB: Session(engine)
        DB-->>GetDB: db connection
        GetDB-->>Router: Connected
        Router->>Response: HealthCheckResponse(status, message, database_connected)
        Response-->>Client: 200 OK + JSON
    else Create Anonymous Account
        Router->>GetDB: create_anonymous_account() needs get_db()
        GetDB->>DB: Session(engine)
        DB-->>GetDB: db connection
        Router->>Response: AnonymousAccountResponse(account_id, subscription_tier, token_balance, message)
        Response-->>Client: 200 OK + JSON
    else Recipe Query (Anonymous)
        Client->>Router: anonymous_recipe_query(AnonymousQueryRequest)
        Router->>GetDB: Dependency injection get_db()
        GetDB->>DB: Session(engine)
        DB-->>GetDB: db connection
        Router->>Response: AnonymousQueryResponse(recipes: List[RecipeSummary], tokens_deducted, query_id)
        Response-->>Client: 200 OK + JSON
    else Advanced Search
        Client->>Router: advanced_recipe_search(AdvancedSearchRequest)
        Router->>GetDB: Dependency injection get_db()
        GetDB->>DB: Session(engine)
        DB-->>GetDB: db connection
        Router->>Response: AdvancedSearchResponse(recipes: List[RecipeSearchResult], count, filters_applied)
        Response-->>Client: 200 OK + JSON
    else Token Management
        Router->>GetDB: get_token_balance()/consume_tokens()
        GetDB->>DB: Query/Update tokens
        DB-->>GetDB: balance/new_balance
        Router->>Response: TokenTransactionResponse
        Response-->>Client: 200 OK + JSON
    else Recipe Submission
        Client->>Router: submit_recipe(RecipeSubmissionRequest)
        Router->>GetDB: Dependency injection get_db()
        GetDB->>DB: Session(engine)
        DB-->>GetDB: db connection
        Router->>Response: RecipeSubmissionResponse(submission_id, status, message, estimated_tokens)
        Response-->>Client: 200 OK + JSON
    else Error Response
        Router-->>Response: Exception/Validation Error
        Response-->>Client: 4xx/5xx + ErrorResponse(error, details)
    end
```

**Nodes:** Client, FastAPI App, CORS Middleware, Router Handler, get_db (Dependency), Database Session, Response Builder, health_check, create_anonymous_account, anonymous_recipe_query, advanced_recipe_search, get_token_balance, consume_tokens, submit_recipe, HealthCheckResponse, AnonymousAccountResponse, AnonymousQueryRequest, AnonymousQueryResponse, RecipeSummary, AdvancedSearchRequest, AdvancedSearchResponse, RecipeSearchResult, TokenTransactionResponse, RecipeSubmissionRequest, RecipeSubmissionResponse

**Edges:**
- Client --HTTP Request--> FastAPI
- FastAPI --Process Request--> CORS Middleware
- CORS Middleware --Route to Handler--> Router
- Router --calls get_db()--> GetDB
- GetDB --Session(engine)--> Database
- Database --connection--> GetDB
- GetDB --injection--> Router
- Router --return model--> Response
- Response --HTTP Response--> Client
- anonymous_recipe_query --consumes--> AnonymousQueryRequest
- anonymous_recipe_query --calls--> RecipeSummary
- advanced_recipe_search --consumes--> AdvancedSearchRequest
- advanced_recipe_search --calls--> AdvancedSearchResponse
- advanced_recipe_search --calls--> RecipeSearchResult
- submit_recipe --consumes--> RecipeSubmissionRequest
- submit_recipe --calls--> calculate_submission_tokens
