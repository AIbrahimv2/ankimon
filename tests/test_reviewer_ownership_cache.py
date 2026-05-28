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
_orig_modules = {}

def setup_mocks():
    # Mock aqt/anki namespaces
    for name in [
        "aqt", "aqt.qt", "aqt.utils", "aqt.gui_hooks", "aqt.operations", 
        "aqt.reviewer", "aqt.webview", "aqt.main",
        "anki", "anki.hooks", "anki.collection", "anki.models", "anki.notes", "anki.template", "anki.buildinfo"
    ]:
        sys.modules[name] = MagicMock()
    
    # Define a mock for resources
    class MockResources:
        user_path = Path("/tmp")
        csv_file_items_cost = Path("/tmp/items.csv")
        items_path = Path("/tmp/items.json")
        badges_path = Path("/tmp/badges.json")
        mypokemon_path = Path("/tmp/mypokemon.json")
        mainpokemon_path = Path("/tmp/mainpokemon.json")
        def __getattr__(self, name): return Path("/tmp") / name

    # Setup parent packages using correct paths for relative imports to work
    for _pkg in ("Ankimon", "Ankimon.functions", "Ankimon.pyobj"):
        _mod = types.ModuleType(_pkg)
        _mod.__path__ = [str(_src / _pkg.replace(".", "/"))]
        _mod.__package__ = _pkg
        sys.modules[_pkg] = _mod

    sys.modules["Ankimon.resources"] = MockResources()
    
    # Setup Ankimon.singletons as a proper module with mocked singleton attributes
    mock_singletons = types.ModuleType("Ankimon.singletons")
    mock_singletons.main_pokemon = MagicMock()
    mock_singletons.main_pokemon.level = 50
    mock_singletons.ankimon_tracker_obj = MagicMock()
    mock_singletons.trainer_card = MagicMock()
    mock_singletons.trainer_card.level = 5
    mock_singletons.settings_obj = MagicMock()
    mock_singletons.settings_obj.get.return_value = 100
    mock_singletons.translator = MagicMock()
    mock_singletons.ankimon_db = MagicMock()
    mock_singletons.pokemon_pc = MagicMock()
    sys.modules["Ankimon.singletons"] = mock_singletons

    # Specific submodules mocked
    for sub in [
        "Ankimon.pyobj.ankimon_tracker", "Ankimon.pyobj.pokemon_obj", 
        "Ankimon.pyobj.reviewer_obj", "Ankimon.pyobj.test_window", 
        "Ankimon.pyobj.trainer_card", "Ankimon.pyobj.InfoLogger", 
        "Ankimon.pyobj.evolution_window", "Ankimon.pyobj.attack_dialog",
        "Ankimon.pyobj.translator", "Ankimon.pyobj.error_handler",
        "Ankimon.functions.pokemon_functions", "Ankimon.functions.pokedex_functions",
        "Ankimon.functions.trainer_functions", "Ankimon.functions.badges_functions",
        "Ankimon.functions.drawing_utils", "Ankimon.functions.friendship_evolution",
        "Ankimon.utils", "Ankimon.business", "Ankimon.const"
    ]:
        sys.modules[sub] = MagicMock()

def setup_module():
    global _orig_modules
    _orig_modules = sys.modules.copy()
    setup_mocks()

def teardown_module():
    # Remove any newly added modules
    to_delete = [k for k in sys.modules if k not in _orig_modules]
    for k in to_delete:
        del sys.modules[k]
    # Restore original modules
    sys.modules.update(_orig_modules)

# Setup a clean DB for local tests
from Ankimon.pyobj.database_manager import AnkimonDB

class MockLogger:
    def log(self, level, msg): pass
    def log_and_showinfo(self, level, msg): pass
    def _log(self, level, msg): pass

class MockReviewerManager:
    def __init__(self):
        self._ownership_cache = {}
        self._last_state = None
        
    def update_life_bar(self, reviewer, ease, card):
        pass

@pytest.fixture
def temp_env(tmp_path):
    """Setup a temporary environment for the DB."""
    # Dynamically locate DB spec using our newly stubbed modules
    spec_db = importlib.util.spec_from_file_location(
        "Ankimon.pyobj.database_manager",
        _src / "Ankimon" / "pyobj" / "database_manager.py",
    )
    db_mod = importlib.util.module_from_spec(spec_db)
    sys.modules[spec_db.name] = db_mod
    spec_db.loader.exec_module(db_mod)

    with patch.object(db_mod, "user_path", tmp_path), \
         patch.object(db_mod, "csv_file_items_cost", str(tmp_path / "items.csv")), \
         patch.object(db_mod, "items_path", tmp_path / "items_mig.json"), \
         patch.object(db_mod, "badges_path", tmp_path / "badges_mig.json"):
        
        db = db_mod.AnkimonDB(MockLogger())
        yield db, tmp_path

def test_cache_invalidation_helper(temp_env):
    db, _ = temp_env
    mock_reviewer = MockReviewerManager()
    mock_reviewer._ownership_cache[4] = False
    
    mock_mw = MagicMock()
    mock_mw.reviewer_obj = mock_reviewer
    
    with patch("aqt.mw", mock_mw):
        db._clear_reviewer_ownership_cache()
        assert len(mock_reviewer._ownership_cache) == 0

def test_save_pokemon_invalidates_cache(temp_env):
    db, _ = temp_env
    mock_reviewer = MockReviewerManager()
    mock_reviewer._ownership_cache[25] = False
    
    mock_mw = MagicMock()
    mock_mw.reviewer_obj = mock_reviewer
    mock_mw.ankimon_db = db
    
    with patch("aqt.mw", mock_mw):
        pokemon_data = {
            "individual_id": "test-uuid-1",
            "id": 25,
            "name": "Pikachu",
            "shiny": False,
            "level": 5
        }
        db.save_pokemon(pokemon_data)
        assert len(mock_reviewer._ownership_cache) == 0

def test_delete_pokemon_invalidates_cache(temp_env):
    db, _ = temp_env
    mock_reviewer = MockReviewerManager()
    mock_reviewer._ownership_cache[25] = True
    
    mock_mw = MagicMock()
    mock_mw.reviewer_obj = mock_reviewer
    mock_mw.ankimon_db = db
    
    with patch("aqt.mw", mock_mw):
        pokemon_data = {
            "individual_id": "test-uuid-1",
            "id": 25,
            "name": "Pikachu",
            "shiny": False,
            "level": 5
        }
        db.save_pokemon(pokemon_data)
        mock_reviewer._ownership_cache[25] = True
        
        db.delete_pokemon("test-uuid-1")
        assert len(mock_reviewer._ownership_cache) == 0

def test_replace_pokemon_invalidates_cache(temp_env):
    db, _ = temp_env
    mock_reviewer = MockReviewerManager()
    mock_reviewer._ownership_cache[25] = True
    
    mock_mw = MagicMock()
    mock_mw.reviewer_obj = mock_reviewer
    mock_mw.ankimon_db = db
    
    with patch("aqt.mw", mock_mw):
        p1 = {
            "individual_id": "uuid-1",
            "id": 25,
            "name": "Pikachu",
            "shiny": False,
            "level": 5
        }
        p2 = {
            "individual_id": "uuid-2",
            "id": 26,
            "name": "Raichu",
            "shiny": False,
            "level": 36
        }
        db.save_pokemon(p1)
        mock_reviewer._ownership_cache[25] = True
        
        db.replace_pokemon(p2, "uuid-1")
        assert len(mock_reviewer._ownership_cache) == 0

def test_save_main_pokemon_invalidates_cache(temp_env):
    db, _ = temp_env
    mock_reviewer = MockReviewerManager()
    mock_reviewer._ownership_cache[25] = True
    
    mock_mw = MagicMock()
    mock_mw.reviewer_obj = mock_reviewer
    mock_mw.ankimon_db = db
    
    with patch("aqt.mw", mock_mw):
        p = {
            "individual_id": "uuid-main",
            "id": 25,
            "name": "Pikachu",
            "shiny": False,
            "level": 5
        }
        db.save_main_pokemon(p)
        assert len(mock_reviewer._ownership_cache) == 0

def test_new_pokemon_invalidates_cache():
    # Setup singletons mock
    mock_singletons = sys.modules["Ankimon.singletons"]
    
    # Dynamically load encounter_functions
    spec_ef = importlib.util.spec_from_file_location(
        "Ankimon.functions.encounter_functions",
        _src / "Ankimon" / "functions" / "encounter_functions.py",
    )
    ef_mod = importlib.util.module_from_spec(spec_ef)
    sys.modules[spec_ef.name] = ef_mod
    
    # Pre-patch singletons & functions so load doesn't fail
    ef_mod.main_pokemon = mock_singletons.main_pokemon
    ef_mod.settings_obj = mock_singletons.settings_obj
    ef_mod.ankimon_tracker_obj = MagicMock()
    ef_mod.trainer_card = mock_singletons.trainer_card
    ef_mod.search_pokedex_by_id = MagicMock(return_value="Pikachu")
    ef_mod.search_pokedex = MagicMock(return_value=1)
    ef_mod.check_id_ok = MagicMock(return_value=True)
    ef_mod.check_min_generate_level = MagicMock(return_value=1)
    ef_mod._meets_prerequisites = MagicMock(return_value=True)
    ef_mod._percentages_cache = {}
    
    # Run mock loaders
    with patch("Ankimon.utils.load_collected_pokemon_ids", return_value=set()):
        spec_ef.loader.exec_module(ef_mod)
    
    # Setup mocks for arguments
    enemy_pokemon = MagicMock()
    enemy_pokemon.name = "Pikachu"
    enemy_pokemon.id = 25
    
    mock_tracker = MagicMock()
    mock_reviewer = MockReviewerManager()
    mock_reviewer._ownership_cache[25] = False
    
    # Call new_pokemon
    with patch("random.randint", return_value=5), \
         patch("random.choice", return_value=25), \
         patch.object(ef_mod, "get_tier", return_value="Normal"), \
         patch.object(ef_mod, "get_all_pokemon_in_tier", return_value=[25]):
        
        ef_mod.new_pokemon(enemy_pokemon, MagicMock(), mock_tracker, mock_reviewer)
    
    # Verify cache got cleared inside new_pokemon
    assert len(mock_reviewer._ownership_cache) == 0

def test_get_all_pokemon_ids_caching(temp_env):
    db, _ = temp_env
    
    p = {
        "individual_id": "uuid-test-cache",
        "id": 150,
        "name": "Mewtwo",
        "shiny": False,
        "level": 70
    }
    
    # Cache should be None initially
    assert db._all_pokemon_ids_cache is None
    
    # 1. Fetching first time populates cache
    ids = db.get_all_pokemon_ids()
    assert 150 not in ids
    assert db._all_pokemon_ids_cache is not None
    assert 150 not in db._all_pokemon_ids_cache
    
    # Manually poison the cache to verify it is retrieved directly
    db._all_pokemon_ids_cache.add(9999)
    assert 9999 in db.get_all_pokemon_ids()
    
    # 2. Saving a pokemon should invalidate the cache
    db.save_pokemon(p)
    assert db._all_pokemon_ids_cache is None
    
    # Fetching again repopulates
    ids2 = db.get_all_pokemon_ids()
    assert 150 in ids2
    assert 9999 not in ids2
    assert db._all_pokemon_ids_cache is not None
    
    # 3. History changes invalidate the cache
    db._all_pokemon_ids_cache = {150}
    db.add_to_history(p)
    assert db._all_pokemon_ids_cache is None
    
    # 4. mark_as_caught invalidates the cache
    db._all_pokemon_ids_cache = {150}
    db.mark_as_caught(151)
    assert db._all_pokemon_ids_cache is None
    
    # 5. switch_database invalidates the cache
    db._all_pokemon_ids_cache = {150}
    db.switch_database("ankimonDEV.db")
    assert db._all_pokemon_ids_cache is None

def test_hotkey_0_updates_life_bar():
    # Setup mocks
    mock_singletons = sys.modules["Ankimon.singletons"]
    
    spec_ui = importlib.util.spec_from_file_location(
        "Ankimon.reviewer_ui",
        _src / "Ankimon" / "reviewer_ui.py",
    )
    ui_mod = importlib.util.module_from_spec(spec_ui)
    sys.modules[spec_ui.name] = ui_mod
    
    # Set up mocks for singletons used in test_encounter_shortcut_function
    mock_singletons.enemy_pokemon = MagicMock()
    mock_singletons.get_test_window = MagicMock()
    mock_singletons.get_evo_window = MagicMock()
    mock_singletons.logger = MagicMock()
    mock_singletons.achievements = MagicMock()
    mock_singletons.reviewer_obj = MagicMock()

    ui_mod.enemy_pokemon = mock_singletons.main_pokemon
    ui_mod.ankimon_tracker_obj = mock_singletons.ankimon_tracker_obj
    ui_mod.reviewer_obj = MagicMock()
    
    mock_mw = MagicMock()
    mock_mw.reviewer.web = MagicMock()
    ui_mod.mw = mock_mw
    
    spec_ui.loader.exec_module(ui_mod)
    
    with patch.object(ui_mod, "is_dev_mode", return_value=True), \
         patch.object(ui_mod, "new_pokemon") as mock_new_pokemon, \
         patch.object(ui_mod, "tooltip") as mock_tooltip:
         
        # Trigger hotkey 0 function
        ui_mod.test_encounter_shortcut_function()
        
        # Verify new_pokemon got called
        mock_new_pokemon.assert_called_once_with(
            ui_mod.enemy_pokemon,
            ui_mod.get_test_window(),
            ui_mod.ankimon_tracker_obj,
            ui_mod.reviewer_obj
        )
        
        # Verify update_life_bar got called
        ui_mod.reviewer_obj.update_life_bar.assert_called_once()
        args, kwargs = ui_mod.reviewer_obj.update_life_bar.call_args
        assert args[1] == 0
        assert args[2] == 0


