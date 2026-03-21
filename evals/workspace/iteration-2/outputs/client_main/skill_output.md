# Skill Output — Client_Side/main.py

**Diagram type:** stateDiagram-v2 — Represents SmartRecipeApp authentication state machine with transitions between UNINITIALIZED, AUTHENTICATING, AUTHENTICATED, and UNAUTHENTICATED states

**Graph files read:** toc.json, sub/main_Client_Side_main.json

```mermaid
stateDiagram-v2
    [*] --> UNINITIALIZED: SmartRecipeApp.__init__

    UNINITIALIZED --> INITIALIZED: check_first_run<br/>initialize_fresh_database<br/>run_migrations

    INITIALIZED --> AUTHENTICATING: run()<br/>check_authentication

    AUTHENTICATING --> AUTHENTICATED: on_login_success<br/>set_current_user
    AUTHENTICATING --> UNAUTHENTICATED: auth_failed

    AUTHENTICATED --> DASHBOARD: dashboard_view

    DASHBOARD --> AUTHENTICATED: dashboard_operations<br/>meal_plan_manager<br/>seasonal_calculator<br/>local_recommender<br/>preference_compiler

    AUTHENTICATED --> LOGOUT: on_logout<br/>get_current_user

    LOGOUT --> UNAUTHENTICATED: clear_user_state

    UNAUTHENTICATED --> AUTHENTICATING: retry_auth<br/>check_authentication
```

**Nodes:** UNINITIALIZED, INITIALIZED, AUTHENTICATING, AUTHENTICATED, UNAUTHENTICATED, DASHBOARD, LOGOUT

**Edges:**
- SmartRecipeApp.__init__ --calls--> check_first_run
- check_first_run --calls--> initialize_fresh_database
- check_first_run --calls--> run_migrations
- SmartRecipeApp.run --calls--> check_authentication
- check_authentication --produces--> AUTHENTICATED_state or UNAUTHENTICATED_state
- on_login_success --calls--> set_current_user
- on_logout --calls--> get_current_user (clear state)
- SmartRecipeApp --contains--> on_login_success
- SmartRecipeApp --contains--> on_logout
- SmartRecipeApp.run --contains--> check_authentication
- SmartRecipeApp.__init__ --contains--> check_first_run
