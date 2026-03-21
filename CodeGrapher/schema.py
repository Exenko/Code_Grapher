"""
schema.py — Single source of truth for node/edge types and ID generation.

Reusable across any Python project. No project-specific logic here.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import re


class NodeType(str, Enum):
    FILE = "file"
    SYMBOL = "symbol"
    TYPE = "type"
    DIRECTORY = "directory"
    REPO = "repo"


class EdgeRelation(str, Enum):
    DEFINES = "defines"
    IMPORTS = "imports"
    CALLS = "calls"
    USES_TYPE = "uses_type"
    CONTAINS = "contains"
    DEPENDS_ON = "depends_on"
    ENTRY_OF = "entry_of"
    PRODUCES = "produces"
    CONSUMES = "consumes"
    MODIFIES = "modifies"
    TYPEDEF_OF = "typedef_of"
    MAPS_TO = "maps_to"


@dataclass
class Node:
    id: str
    type: NodeType
    label: str
    file: Optional[str]       # relative path from project root
    line: Optional[int]
    language: str = "python"
    is_dataclass: bool = False
    is_test: bool = False
    ref: Optional[str] = None
    count: Optional[int] = None
    annotation: Optional[str] = None  # type annotation text for field nodes (e.g. "List[Tuple[str,str]]")

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "type": self.type.value,
            "label": self.label,
            "file": self.file,
            "line": self.line,
            "language": self.language,
        }
        if self.is_dataclass:
            d["is_dataclass"] = True
        if self.is_test:
            d["is_test"] = True
        if self.ref is not None:
            d["ref"] = self.ref
        if self.count is not None:
            d["count"] = self.count
        if self.annotation is not None:
            d["annotation"] = self.annotation
        return d


@dataclass
class Edge:
    from_id: str
    to_id: str
    relation: EdgeRelation
    unresolved: bool = False
    count: Optional[int] = None
    # produces edge metadata
    via: Optional[str] = None       # "return_value" | "param_mutation"
    relay: Optional[bool] = None    # True = symbol did not originate this value
    # consumes edge metadata
    role: Optional[str] = None      # "data" | "control"
    # contains edge metadata
    ptr_depth: Optional[int] = None # 0=direct, 1=pointer, 2=pointer-to-pointer
    # sequencing metadata (body analysis)
    seq: Optional[int] = None       # relative call order within parent function body

    def to_dict(self) -> dict:
        d = {
            "from": self.from_id,
            "to": self.to_id,
            "relation": self.relation.value,
        }
        if self.unresolved:
            d["unresolved"] = True
        if self.count is not None:
            d["count"] = self.count
        if self.via is not None:
            d["via"] = self.via
        if self.relay is not None:
            d["relay"] = self.relay
        if self.role is not None:
            d["role"] = self.role
        if self.ptr_depth is not None:
            d["ptr_depth"] = self.ptr_depth
        if self.seq is not None:
            d["seq"] = self.seq
        return d

    def key(self) -> tuple:
        return (self.from_id, self.to_id, self.relation)


# ---------------------------------------------------------------------------
# ID factory functions — deterministic, file-path-scoped
# ---------------------------------------------------------------------------

def _normalize_path(rel_path: str) -> str:
    """Normalize path separators to forward slashes."""
    return rel_path.replace("\\", "/")


def file_id(feature: str, rel_path: str) -> str:
    """ID for a file node. e.g. autofill::Client_Side/utils/autofill_engine.py"""
    return f"{feature}::{_normalize_path(rel_path)}"


def symbol_id(feature: str, rel_path: str, name: str) -> str:
    """ID for a function/method symbol. e.g. autofill::Client_Side/utils/autofill_engine.py::score_recipe_for_session"""
    return f"{feature}::{_normalize_path(rel_path)}::{name}"


def type_id(feature: str, module_name: str, class_name: str) -> str:
    """ID for a class/type node (shared bridge node). e.g. autofill::autofill_engine::RecipeScore"""
    return f"{feature}::{module_name}::{class_name}"


def stdlib_module_id(module_name: str) -> str:
    """ID for a stdlib or third-party module import target."""
    return f"stdlib::{module_name}"


def is_test_file(rel_path: str) -> bool:
    """Returns True if the file is a test file based on naming convention."""
    name = rel_path.replace("\\", "/").split("/")[-1]
    return name.startswith("test_") or name == "conftest.py"


def dir_id(feature: str, rel_dir: str) -> str:
    """ID for a directory node. e.g. autofill::dir::Client_Side/utils"""
    return f"{feature}::dir::{_normalize_path(rel_dir)}"


def repo_id(feature: str, name: str) -> str:
    """ID for a repository/root node. e.g. autofill::repo::SmartRecipeApp"""
    return f"{feature}::repo::{name}"
