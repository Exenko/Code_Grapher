# Ground Truth: key_manager.py — classDiagram

## Metadata
- GT node count: 1
- GT edge count: 0
- Source: Client_Side/utils/key_manager.py

## Mermaid diagram
```mermaid
classDiagram
  class HouseholdKeyManager {
    +db_path: str
    +__init__(db_path)
    +_ensure_schema()
    +generate_keypair(household_id, master_password) str
    +get_public_key(household_id) str
    +load_private_key(household_id, master_password)
    +has_keypair(household_id) bool
    +rotate_keypair(household_id, old_password, new_password) str
    +_derive_encryption_key(password) bytes
    +export_public_key_for_server(household_id) dict
  }
```

## Notes
Single class: HouseholdKeyManager.

No structural edges:
- Only field is `db_path: str` — built-in primitive, no custom class
- Cryptography objects (RSA keys, Fernet) are instantiated and used locally within methods — never stored as instance fields
- No other custom classes defined in this file

Zero-edge diagrams are valid: the rule is field-type declarations only, and none exist here.
