# Skill Output v2 — Client_Side/ui_new/run_ui.py

**Diagram type:** flowchart LR — Linear startup call chain from run_ui.py main() entry point through MainWindow initialization, view registration, and application launch

**Graph files read:** sub/main_Client_Side_ui_new_run_ui.json, tier_symbol.json

```mermaid
flowchart LR
    A["main()"] --> B["QApplication<br/>sys.argv"]
    B --> C["app.setApplicationName<br/>SmartRecipeApp"]
    C --> D["app.setApplicationDisplayName<br/>SmartRecipeApp"]
    D --> E["MainWindow<br/>instantiate"]

    E --> E1["MainWindow.__init__"]
    E1 --> F["get_theme_manager"]
    F --> G["_theme_manager.on_theme_changed"]
    G --> H["_setup_window"]

    H --> I["_setup_ui"]
    I --> I1["QWidget central"]
    I1 --> I2["QVBoxLayout"]
    I2 --> I3["NavigationHeader"]
    I3 --> I4["QStackedWidget"]
    I4 --> I5["setCentralWidget"]

    E1 --> J["_load_theme_preference"]
    E1 --> K["_apply_theme"]
    K --> K1["generate_qss"]
    K1 --> K2["setStyleSheet"]

    A --> L["register_view<br/>login, LoginView"]
    A --> M["register_view<br/>dashboard, DashboardView"]
    A --> N["register_view<br/>calendar, CalendarView"]
    A --> O["register_view<br/>preferences, PreferencesView"]
    A --> P["register_view<br/>recipe_entry, RecipeEntryView"]

    A --> Q["switch_view<br/>login"]
    Q --> Q1["_get_or_create_view"]
    Q1 --> Q2["LoginView instantiate"]
    Q2 --> Q3["stacked_widget.addWidget"]
    Q3 --> Q4["setCurrentWidget"]
    Q4 --> Q5["on_view_activated"]

    A --> R["window.show"]
    R --> S["app.exec"]
    S --> T["sys.exit"]
```

**Nodes:** main, QApplication, setApplicationName, setApplicationDisplayName, MainWindow, MainWindow.__init__, get_theme_manager, on_theme_changed, _setup_window, _setup_ui, QWidget, QVBoxLayout, NavigationHeader, QStackedWidget, setCentralWidget, _load_theme_preference, _apply_theme, generate_qss, setStyleSheet, register_view LoginView, register_view DashboardView, register_view CalendarView, register_view PreferencesView, register_view RecipeEntryView, switch_view, _get_or_create_view, LoginView instantiate, addWidget, setCurrentWidget, on_view_activated, window.show, app.exec, sys.exit

**Edges:**
- main --calls--> QApplication
- main --calls--> setApplicationName
- main --calls--> setApplicationDisplayName
- main --calls--> MainWindow
- MainWindow.__init__ --calls--> get_theme_manager
- MainWindow.__init__ --calls--> on_theme_changed
- MainWindow.__init__ --calls--> _setup_window
- MainWindow.__init__ --calls--> _setup_ui
- MainWindow.__init__ --calls--> _load_theme_preference
- MainWindow.__init__ --calls--> _apply_theme
- _setup_ui --calls--> QWidget
- _setup_ui --calls--> QVBoxLayout
- _setup_ui --calls--> NavigationHeader
- _setup_ui --calls--> QStackedWidget
- _setup_ui --calls--> setCentralWidget
- _apply_theme --calls--> generate_qss
- _apply_theme --calls--> setStyleSheet
- main --calls--> register_view (5x)
- main --calls--> switch_view
- switch_view --calls--> _get_or_create_view
- _get_or_create_view --calls--> LoginView instantiate
- _get_or_create_view --calls--> addWidget
- _get_or_create_view --calls--> setCurrentWidget
- switch_view --calls--> on_view_activated
- main --calls--> window.show
- main --calls--> app.exec
- main --calls--> sys.exit
