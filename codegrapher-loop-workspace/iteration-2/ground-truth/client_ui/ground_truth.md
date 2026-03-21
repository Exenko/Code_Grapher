# Ground Truth — Client_Side/ui_new/run_ui.py

**Diagram type:** flowchart LR — Linear startup sequence showing QApplication instantiation, MainWindow initialization with theme manager loading, view registration, and then sequential view activation and display.

**Key files read:** Client_Side/ui_new/run_ui.py, Client_Side/ui_new/main_window.py, Client_Side/ui_new/views/__init__.py, Client_Side/ui_new/components/__init__.py, Client_Side/ui_new/components/navigation_header.py, Client_Side/ui_new/styles/theme_manager.py

```mermaid
flowchart LR
    A["main()"]
    B["QApplication<br/>sys.argv"]
    C["set app name"]
    D["MainWindow<br/>app_controller=None"]
    E["__init__<br/>MainWindow"]
    F["get_theme_manager<br/>singleton"]
    G["on_theme_changed<br/>callback register"]
    H["_setup_window"]
    I["_setup_ui<br/>central widget"]
    J["NavigationHeader<br/>create"]
    K["QStackedWidget<br/>create"]
    L["_load_theme_preference"]
    M["_apply_theme"]
    N["register_view<br/>LoginView"]
    O["register_view<br/>DashboardView"]
    P["register_view<br/>CalendarView"]
    Q["register_view<br/>PreferencesView"]
    R["register_view<br/>RecipeEntryView"]
    S["switch_view<br/>login"]
    T["_get_or_create_view"]
    U["LoginView<br/>instantiate"]
    V["_stacked_widget.setCurrentWidget"]
    W["view.on_view_activated<br/>if exists"]
    X["window.show"]
    Y["app.exec<br/>event loop"]
    Z["sys.exit"]

    A -->|calls| B
    B -->|produces| C
    C -->|calls| D
    D -->|produces| E
    E -->|calls| F
    E -->|calls| G
    E -->|calls| H
    E -->|calls| I
    I -->|produces| J
    I -->|produces| K
    E -->|calls| L
    E -->|calls| M
    A -->|calls| N
    N -->|consumes| O
    O -->|consumes| P
    P -->|consumes| Q
    Q -->|consumes| R
    A -->|calls| S
    S -->|calls| T
    T -->|produces| U
    U -->|relay| V
    T -->|calls| W
    A -->|calls| X
    A -->|calls| Y
    Y -->|produces| Z
```

**Nodes:** main, QApplication, set app name, MainWindow, __init__ MainWindow, get_theme_manager, on_theme_changed callback register, _setup_window, _setup_ui central widget, NavigationHeader create, QStackedWidget create, _load_theme_preference, _apply_theme, register_view LoginView, register_view DashboardView, register_view CalendarView, register_view PreferencesView, register_view RecipeEntryView, switch_view login, _get_or_create_view, LoginView instantiate, _stacked_widget.setCurrentWidget, view.on_view_activated if exists, window.show, app.exec event loop, sys.exit

**Edges:**
- main --calls--> QApplication
- QApplication --produces--> set app name
- set app name --calls--> MainWindow
- MainWindow --produces--> __init__ MainWindow
- __init__ MainWindow --calls--> get_theme_manager
- __init__ MainWindow --calls--> on_theme_changed callback register
- __init__ MainWindow --calls--> _setup_window
- __init__ MainWindow --calls--> _setup_ui central widget
- _setup_ui central widget --produces--> NavigationHeader create
- _setup_ui central widget --produces--> QStackedWidget create
- __init__ MainWindow --calls--> _load_theme_preference
- __init__ MainWindow --calls--> _apply_theme
- main --calls--> register_view LoginView
- register_view LoginView --consumes--> register_view DashboardView
- register_view DashboardView --consumes--> register_view CalendarView
- register_view CalendarView --consumes--> register_view PreferencesView
- register_view PreferencesView --consumes--> register_view RecipeEntryView
- main --calls--> switch_view login
- switch_view login --calls--> _get_or_create_view
- _get_or_create_view --produces--> LoginView instantiate
- LoginView instantiate --relay--> _stacked_widget.setCurrentWidget
- _get_or_create_view --calls--> view.on_view_activated if exists
- main --calls--> window.show
- main --calls--> app.exec event loop
- app.exec event loop --produces--> sys.exit
