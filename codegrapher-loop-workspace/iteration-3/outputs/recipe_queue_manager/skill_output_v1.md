# recipe_queue_manager — Skill Agent v1 Output

**Version:** v1
**Graph sources used:** symbol names + calls edges (intra-file state machine inference)
**Approach:** Method names mapped to lifecycle states. Composite states used for REJECTED (TEMPORARY/PERMANENT) and ENQUEUED (AVAILABLE/FAVORITED). Read-only methods shown as notes.

## Diagram

```mermaid
stateDiagram-v2
    [*] --> ENQUEUED : add_recipes_to_queue

    state ENQUEUED {
        AVAILABLE --> FAVORITED : set_favorite
        FAVORITED --> AVAILABLE : set_favorite
    }

    ENQUEUED --> SERVED : mark_recipe_served
    ENQUEUED --> REJECTED : reject_recipe

    state REJECTED {
        TEMPORARY --> PERMANENT : change_rejection_type
        PERMANENT --> TEMPORARY : change_rejection_type
        TEMPORARY --> EXPIRED : cleanup_expired_rejections
        EXPIRED --> [*]
    }

    REJECTED --> [*] : un_reject_recipe

    note right of SERVED
        get_recent_served_recipes (read-only)
    end note

    note right of ENQUEUED
        get_next_recipe (read position=0)
        get_queue (read all)
    end note

    note right of REJECTED
        get_active_rejections (read-only)
    end note
```

## Counts
- **State count:** 9 (ENQUEUED, AVAILABLE, FAVORITED, SERVED, REJECTED, TEMPORARY, PERMANENT, EXPIRED, plus [*])
- **Edge count:** 10 transitions
