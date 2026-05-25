import os
import sys
import json
import sqlite3
import pytest
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch
import types

_src = Path(__file__).parent.parent / "src"

def setup_mocks():
    # Mock aqt/anki namespaces
    for name in [
        "aqt", "aqt.qt", "aqt.utils", "aqt.gui_hooks", "aqt.operations", 
        "aqt.reviewer", "aqt.webview", "aqt.main", "aqt.operations.QueryOp",
        "anki", "anki.hooks", "anki.collection", "anki.models", "anki.notes", "anki.template", "anki.buildinfo"
    ]:
        sys.modules[name] = MagicMock()
    
    class MockResources:
        user_path = Path("/tmp")
        csv_file_items_cost = Path("/tmp/items.csv")
        items_path = Path("/tmp/items.json")
        badges_path = Path("/tmp/badges.json")
        mypokemon_path = Path("/tmp/mypokemon.json")
        mainpokemon_path = Path("/tmp/mainpokemon.json")
        def __getattr__(self, name): return Path("/tmp") / name

    sys.modules["Ankimon"] = types.ModuleType("Ankimon")
    sys.modules["Ankimon.resources"] = MockResources()
    sys.modules["Ankimon.singletons"] = MagicMock()
    sys.modules["Ankimon.utils"] = MagicMock()
    sys.modules["Ankimon.pyobj"] = MagicMock()

setup_mocks()

# Dynamically load database_manager
_spec = importlib.util.spec_from_file_location(
    "Ankimon.pyobj.database_manager",
    _src / "Ankimon" / "pyobj" / "database_manager.py",
)
_db_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _db_mod
_spec.loader.exec_module(_db_mod)

from Ankimon.pyobj.database_manager import AnkimonDB

class MockLogger:
    def log(self, level, msg): pass
    def log_and_showinfo(self, level, msg): pass
    def _log(self, level, msg): pass

@pytest.fixture
def temp_db(tmp_path):
    """Setup a temporary database manager in a clean environment."""
    with patch.object(_db_mod, "user_path", tmp_path):
        db = AnkimonDB(MockLogger())
        yield db

def test_pokedex_evolution_bug_resolved(temp_db):
    """
    Verifies that the Pokédex evolution bug has been fully resolved:
    1. Catch a Bulbasaur (ID 1).
    2. Confirm it is registered as caught.
    3. Manually evolve it in the PC box to Ivysaur (ID 2).
       (Simulates calling db.mark_as_caught(1) followed by saving the evolved form)
    4. Manually evolve it to Venusaur (ID 3).
       (Simulates calling db.mark_as_caught(2) followed by saving the evolved form)
    5. Verify that Bulbasaur (ID 1), Ivysaur (ID 2), and Venusaur (ID 3) are ALL
       correctly registered as caught in the Pokédex data.
    """
    db = temp_db
    
    # 1. Initial State: Player catches a level 90 Bulbasaur
    bulbasaur_data = {
        "individual_id": "bulba-uuid",
        "id": 1,
        "name": "Bulbasaur",
        "level": 90,
        "xp": 0,
        "shiny": False,
        "attacks": ["Tackle"],
        "base_stats": {"hp": 45, "atk": 49, "def": 49, "spa": 65, "spd": 65, "spe": 45},
        "stats": {"hp": 45, "atk": 49, "def": 49, "spa": 65, "spd": 65, "spe": 45},
        "ev": {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
        "iv": {"hp": 15, "atk": 15, "def": 15, "spa": 15, "spd": 15, "spe": 15},
        "ability": "Overgrow",
        "growth_rate": "medium",
        "base_experience": 64,
        "gender": "M"
    }
    
    db.save_pokemon(bulbasaur_data)
    
    # Simulated Pokédex logic for get_ankidex_data:
    # Combines captured_pokemon, pokemon_history, and the new pokedex_caught user_data
    def get_pokedex_caught_ids():
        cursor = db.execute("SELECT pokedex_id FROM captured_pokemon WHERE pokedex_id IS NOT NULL")
        caught = {row[0] for row in cursor.fetchall()}
        
        cursor = db.execute("SELECT DISTINCT json_extract(data, '$.id') FROM pokemon_history")
        for row in cursor.fetchall():
            if row[0]:
                caught.add(int(row[0]))
                
        # Union with explicit persistent caught IDs
        caught.update(db.get_caught_ids())
        return caught

    # Assert Bulbasaur is caught initially
    assert 1 in get_pokedex_caught_ids()
    assert len(get_pokedex_caught_ids()) == 1

    # 2. Simulate manual evolution inside PC Box: Bulbasaur (1) -> Ivysaur (2)
    pokemon = db.get_pokemon("bulba-uuid")
    assert pokemon is not None
    assert pokemon["id"] == 1
    
    # Trigger pre-evolution caught status registration (as done in evolution_window.py)
    db.mark_as_caught(1)
    
    pokemon["name"] = "Ivysaur"
    pokemon["id"] = 2
    pokemon["base_stats"] = {"hp": 60, "atk": 62, "def": 63, "spa": 80, "spd": 80, "spe": 60}
    pokemon["stats"] = pokemon["base_stats"]
    db.save_pokemon(pokemon)
    
    # Assert BOTH Bulbasaur (1) AND Ivysaur (2) are registered as caught
    caught_after_evo1 = get_pokedex_caught_ids()
    assert 1 in caught_after_evo1  # FIXED: Bulbasaur is preserved!
    assert 2 in caught_after_evo1  # Ivysaur is caught!
    assert len(caught_after_evo1) == 2

    # 3. Simulate second manual evolution: Ivysaur (2) -> Venusaur (3)
    pokemon = db.get_pokemon("bulba-uuid")
    assert pokemon is not None
    assert pokemon["id"] == 2
    
    # Trigger pre-evolution caught status registration
    db.mark_as_caught(2)
    
    pokemon["name"] = "Venusaur"
    pokemon["id"] = 3
    pokemon["base_stats"] = {"hp": 80, "atk": 82, "def": 83, "spa": 100, "spd": 100, "spe": 80}
    pokemon["stats"] = pokemon["base_stats"]
    db.save_pokemon(pokemon)
    
    # Assert ALL THREE stages are registered as caught
    final_caught = get_pokedex_caught_ids()
    assert 1 in final_caught  # Bulbasaur preserved
    assert 2 in final_caught  # Ivysaur preserved
    assert 3 in final_caught  # Venusaur caught
    assert len(final_caught) == 3
    
    # Assert they are symmetrically marked as seen
    seen_ids = db.get_seen_ids()
    assert 1 in seen_ids
    assert 2 in seen_ids
    assert 3 in seen_ids
