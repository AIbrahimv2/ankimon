import sys
import unittest.mock as mock
from pathlib import Path
import importlib.util

# Mock necessary modules
sys.modules["aqt"] = mock.MagicMock()
sys.modules["aqt.qt"] = mock.MagicMock()
sys.modules["aqt.utils"] = mock.MagicMock()

# Mock internal dependencies of encounter_functions
for module in [
    "Ankimon.pyobj.ankimon_tracker", "Ankimon.pyobj.pokemon_obj", 
    "Ankimon.pyobj.reviewer_obj", "Ankimon.pyobj.test_window", 
    "Ankimon.pyobj.trainer_card", "Ankimon.pyobj.InfoLogger", 
    "Ankimon.pyobj.evolution_window", "Ankimon.pyobj.attack_dialog",
    "Ankimon.pyobj.translator", "Ankimon.pyobj.error_handler",
    "Ankimon.functions.pokemon_functions", "Ankimon.functions.pokedex_functions",
    "Ankimon.functions.trainer_functions", "Ankimon.functions.badges_functions",
    "Ankimon.functions.drawing_utils", "Ankimon.utils", "Ankimon.business", 
    "Ankimon.const", "Ankimon.singletons", "Ankimon.resources"
]:
    sys.modules[module] = mock.MagicMock()

# Import the module under test
_src = Path(__file__).parent.parent / "src"
spec = importlib.util.spec_from_file_location(
    "Ankimon.functions.encounter_functions",
    _src / "Ankimon" / "functions" / "encounter_functions.py",
)
ef = importlib.util.module_from_spec(spec)
# Pre-patch singletons used in the module
ef.main_pokemon = mock.MagicMock()
ef.settings_obj = mock.MagicMock()
ef.ankimon_tracker_obj = mock.MagicMock()
ef.trainer_card = mock.MagicMock()

# Execute the module
spec.loader.exec_module(ef)

def test_modify_percentages_does_not_raise_nameerror():
    # Setup mocks
    ef.main_pokemon.level = 50
    
    # This should NOT raise NameError if fixed
    try:
        res = ef.modify_percentages(total_reviews=100, daily_average=50, trainer_level=20)
        assert isinstance(res, dict)
        assert sum(res.values()) > 99.9  # Normalized to 100
    except NameError as e:
        import pytest
        pytest.fail(f"NameError raised: {e}")

def test_get_tier_calls_modify_percentages_correctly():
    # Setup mocks
    ef.settings_obj.get.return_value = 100  # daily_average
    
    # This should NOT raise NameError if fixed
    try:
        tier = ef.get_tier(total_reviews=150, trainer_level=25)
        assert isinstance(tier, str)
    except NameError as e:
        import pytest
        pytest.fail(f"NameError raised in get_tier: {e}")

def test_handle_enemy_faint_auto_catch_regional_enabled():
    # Save original globals
    orig_settings = ef.settings_obj
    orig_data = ef.encounter_data
    orig_tracker = ef.ankimon_tracker_obj
    orig_catch = ef.catch_pokemon
    orig_new = ef.new_pokemon
    orig_kill = ef.kill_pokemon
    
    try:
        # Create mock objects
        mock_settings = mock.MagicMock()
        mock_data = mock.MagicMock()
        mock_tracker = mock.MagicMock()
        mock_catch = mock.MagicMock()
        mock_new = mock.MagicMock()
        mock_kill = mock.MagicMock()
        
        # Setup settings mock
        def mock_get(key, default=None):
            if key == "battle.automatic_battle":
                return 3
            if key == "battle.auto_catch_regional":
                return True
            if key.startswith("battle.auto_catch_"):
                return False
            return default
        mock_settings.get = mock_get
        
        # Setup tracker mock
        mock_tracker.faint_processed = False
        
        # Setup encounter_data mocks
        mock_data.MEGA = []
        mock_data.GMAX = []
        mock_data.REGIONAL_FORM_REGION = {10091: "alola"}
        
        # Assign mock objects to ef
        ef.settings_obj = mock_settings
        ef.encounter_data = mock_data
        ef.ankimon_tracker_obj = mock_tracker
        ef.catch_pokemon = mock_catch
        ef.new_pokemon = mock_new
        ef.kill_pokemon = mock_kill
        
        # Setup main / enemy mock pokemon
        main_pokemon = mock.MagicMock()
        enemy_pokemon = mock.MagicMock()
        enemy_pokemon.id = 10091
        enemy_pokemon.tier = "Normal"
        enemy_pokemon.name = "Rattata-Alola"
        enemy_pokemon.shiny = False
        
        collected_pokemon_ids = {10091}
        test_window = mock.MagicMock()
        evo_window = mock.MagicMock()
        reviewer_obj = mock.MagicMock()
        logger = mock.MagicMock()
        achievements = {}
        
        # Execute
        ef.handle_enemy_faint(
            main_pokemon,
            enemy_pokemon,
            collected_pokemon_ids,
            test_window,
            evo_window,
            reviewer_obj,
            logger,
            achievements
        )
        
        # Verify
        mock_catch.assert_called_once()
        mock_new.assert_called_once()
        mock_kill.assert_not_called()
        assert mock_tracker.faint_processed is True
        
    finally:
        # Restore original globals
        ef.settings_obj = orig_settings
        ef.encounter_data = orig_data
        ef.ankimon_tracker_obj = orig_tracker
        ef.catch_pokemon = orig_catch
        ef.new_pokemon = orig_new
        ef.kill_pokemon = orig_kill

def test_handle_enemy_faint_auto_catch_regional_disabled():
    # Save original globals
    orig_settings = ef.settings_obj
    orig_data = ef.encounter_data
    orig_tracker = ef.ankimon_tracker_obj
    orig_catch = ef.catch_pokemon
    orig_new = ef.new_pokemon
    orig_kill = ef.kill_pokemon
    
    try:
        # Create mock objects
        mock_settings = mock.MagicMock()
        mock_data = mock.MagicMock()
        mock_tracker = mock.MagicMock()
        mock_catch = mock.MagicMock()
        mock_new = mock.MagicMock()
        mock_kill = mock.MagicMock()
        
        # Setup settings mock
        def mock_get(key, default=None):
            if key == "battle.automatic_battle":
                return 3
            if key == "battle.auto_catch_regional":
                return False
            if key.startswith("battle.auto_catch_"):
                return False
            return default
        mock_settings.get = mock_get
        
        # Setup tracker mock
        mock_tracker.faint_processed = False
        
        # Setup encounter_data mocks
        mock_data.MEGA = []
        mock_data.GMAX = []
        mock_data.REGIONAL_FORM_REGION = {10091: "alola"}
        
        # Assign mock objects to ef
        ef.settings_obj = mock_settings
        ef.encounter_data = mock_data
        ef.ankimon_tracker_obj = mock_tracker
        ef.catch_pokemon = mock_catch
        ef.new_pokemon = mock_new
        ef.kill_pokemon = mock_kill
        
        # Setup main / enemy mock pokemon
        main_pokemon = mock.MagicMock()
        enemy_pokemon = mock.MagicMock()
        enemy_pokemon.id = 10091
        enemy_pokemon.tier = "Normal"
        enemy_pokemon.name = "Rattata-Alola"
        enemy_pokemon.shiny = False
        
        collected_pokemon_ids = {10091}
        test_window = mock.MagicMock()
        evo_window = mock.MagicMock()
        reviewer_obj = mock.MagicMock()
        logger = mock.MagicMock()
        achievements = {}
        
        # Execute
        ef.handle_enemy_faint(
            main_pokemon,
            enemy_pokemon,
            collected_pokemon_ids,
            test_window,
            evo_window,
            reviewer_obj,
            logger,
            achievements
        )
        
        # Verify
        mock_kill.assert_called_once()
        mock_catch.assert_not_called()
        mock_new.assert_called_once()
        assert mock_tracker.faint_processed is True
        
    finally:
        # Restore original globals
        ef.settings_obj = orig_settings
        ef.encounter_data = orig_data
        ef.ankimon_tracker_obj = orig_tracker
        ef.catch_pokemon = orig_catch
        ef.new_pokemon = orig_new
        ef.kill_pokemon = orig_kill
