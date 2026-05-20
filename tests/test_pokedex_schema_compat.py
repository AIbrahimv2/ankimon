"""
Regression tests for the pokedex schema migration (Nov 2025).

`pokedex.json` was changed from `"num"` to `"species_id"` + `"actual_id"`.
Because the file lived under `user_files/` (which Anki preserves across
updates), every old user kept their legacy file and crashed with
`KeyError: 'species_id'` in `search_pokedex_by_id` on startup.

These tests verify that both `search_pokedex` and `search_pokedex_by_id`
tolerate the legacy schema by falling back to `"num"`.
"""
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_src = Path(__file__).parent.parent / "src"

# --- Stub Anki and addon internals so pokedex_functions can be imported -----
mock_aqt = MagicMock()
sys.modules["aqt"] = mock_aqt
sys.modules["aqt.utils"] = mock_aqt.utils
sys.modules["aqt.qt"] = MagicMock()


class _MockResources:
    pokedex_path = "/dev/null"  # never actually opened; json.load is patched

    def __getattr__(self, name):
        return "dummy"


sys.modules["Ankimon.resources"] = _MockResources()
sys.modules["Ankimon.singletons"] = MagicMock()
sys.modules["Ankimon.utils"] = MagicMock()
_mock_pyobj = MagicMock()
sys.modules["Ankimon.pyobj"] = _mock_pyobj
sys.modules["Ankimon.pyobj.error_handler"] = _mock_pyobj.error_handler

_spec = importlib.util.spec_from_file_location(
    "Ankimon.functions.pokedex_functions",
    _src / "Ankimon" / "functions" / "pokedex_functions.py",
)
_pf = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _pf
_spec.loader.exec_module(_pf)


# --- Fixtures ---------------------------------------------------------------
# Minimal legacy dex (pre-Nov-2025 schema): uses "num" instead of species_id/actual_id.
LEGACY_DEX = {
    "bulbasaur": {"num": 1, "name": "Bulbasaur", "types": ["Grass", "Poison"]},
    "charizard": {"num": 6, "name": "Charizard", "types": ["Fire", "Flying"]},
    "charizardmegax": {
        "num": 6,
        "name": "Charizard-Mega-X",
        "types": ["Fire", "Dragon"],
    },
}

# Minimal current dex with the new keys plus form-disambiguating actual_id.
CURRENT_DEX = {
    "bulbasaur": {
        "species_id": 1, "actual_id": 1,
        "name": "Bulbasaur", "types": ["Grass", "Poison"],
    },
    "charizard": {
        "species_id": 6, "actual_id": 6,
        "name": "Charizard", "types": ["Fire", "Flying"],
    },
    "charizardmegax": {
        "species_id": 6, "actual_id": 10034,
        "name": "Charizard-Mega-X", "types": ["Fire", "Dragon"],
    },
}


def _with_dex(dex):
    """Context for running a pokedex_functions call against a fixed dex."""
    return patch.multiple(
        _pf,
        json=MagicMock(load=lambda *a, **k: dex),
    )


# --- search_pokedex_by_id: legacy schema ------------------------------------
def test_search_by_id_legacy_resolves_via_num():
    with _with_dex(LEGACY_DEX), patch("builtins.open"):
        assert _pf.search_pokedex_by_id(1) == "bulbasaur"
        assert _pf.search_pokedex_by_id(6) == "charizard"


def test_search_by_id_legacy_returns_not_found_for_missing():
    with _with_dex(LEGACY_DEX), patch("builtins.open"):
        assert _pf.search_pokedex_by_id(99999) == "Pokémon not found"


# --- search_pokedex_by_id: current schema -----------------------------------
def test_search_by_id_current_schema():
    with _with_dex(CURRENT_DEX), patch("builtins.open"):
        assert _pf.search_pokedex_by_id(1) == "bulbasaur"
        assert _pf.search_pokedex_by_id(6) == "charizard"


# --- search_pokedex: legacy schema ------------------------------------------
def test_search_pokedex_legacy_species_id_falls_back_to_num():
    with _with_dex(LEGACY_DEX), patch("builtins.open"):
        assert _pf.search_pokedex("bulbasaur", "species_id") == 1


def test_search_pokedex_legacy_actual_id_falls_back_to_num():
    # Forms can't be disambiguated from legacy data, but we should at least
    # return the species number rather than crash or return None.
    with _with_dex(LEGACY_DEX), patch("builtins.open"):
        assert _pf.search_pokedex("charizard", "actual_id") == 6


def test_search_pokedex_legacy_other_keys_unaffected():
    with _with_dex(LEGACY_DEX), patch("builtins.open"):
        assert _pf.search_pokedex("bulbasaur", "name") == "Bulbasaur"


# --- search_pokedex: current schema (no regression) -------------------------
def test_search_pokedex_current_species_id():
    with _with_dex(CURRENT_DEX), patch("builtins.open"):
        assert _pf.search_pokedex("bulbasaur", "species_id") == 1
        assert _pf.search_pokedex("charizardmegax", "species_id") == 6


def test_search_pokedex_current_actual_id_disambiguates_forms():
    with _with_dex(CURRENT_DEX), patch("builtins.open"):
        # The mega form must return its own actual_id, not the species id.
        assert _pf.search_pokedex("charizardmegax", "actual_id") == 10034
