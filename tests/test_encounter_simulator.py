import sys
import unittest.mock as mock
from pathlib import Path
import importlib.util
import pytest

# 1. Back up sys.modules to prevent pollution
orig_modules = dict(sys.modules)

# 2. Mock PyQt6 and other external modules before import
sys.modules["aqt"] = mock.MagicMock()
sys.modules["aqt.qt"] = mock.MagicMock()
sys.modules["aqt.utils"] = mock.MagicMock()

# Mock dependencies
for module in [
    "Ankimon.functions.encounter_functions",
    "Ankimon.functions.pokedex_functions",
    "Ankimon.business",
    "Ankimon.singletons",
    "Ankimon.resources",
    "PyQt6.QtWebEngineWidgets",
    "PyQt6.QtWebChannel"
]:
    sys.modules[module] = mock.MagicMock()

# 3. Import the module under test dynamically
_src = Path(__file__).parent.parent / "src"
spec = importlib.util.spec_from_file_location(
    "Ankimon.pyobj.encounter_simulator_dialog",
    _src / "Ankimon" / "pyobj" / "encounter_simulator_dialog.py",
)
esd = importlib.util.module_from_spec(spec)

# Mock required module-level imports
esd.QDialog = mock.MagicMock
esd.QVBoxLayout = mock.MagicMock
esd.QWebEngineView = mock.MagicMock
esd.QWebChannel = mock.MagicMock
esd.QObject = mock.MagicMock

spec.loader.exec_module(esd)

# 4. Restore sys.modules immediately after executing the module loader
sys.modules.clear()
sys.modules.update(orig_modules)

def test_calculate_rates_mocked():
    """
    Verifies that calculate_rates runs without exceptions when given slider states,
    and returns a structured output containing live, overhaul, legacy, ep, and locks.
    """
    # Create the dialog instance with a mocked Path
    dialog = mock.MagicMock()
    
    # Configure mock calculation outputs from encounter_functions
    esd.ef.modify_percentages = mock.MagicMock(return_value={
        "Normal": 90.0, "Baby": 10.0, "Ultra": 0.0, "Gmax": 0.0,
        "Starter": 0.0, "Mega": 0.0, "Legendary": 0.0, "Mythical": 0.0
    })
    esd.ef.USE_OVERHAUL_ENCOUNTER_SYSTEM = False
    esd.ef.TRAINER_LEVEL_CAP = 50.0
    esd.ef.CORE_TEAM_POWER_CAP = 16000.0
    esd.ef.EP_WEIGHT_TRAINER_LEVEL = 0.25
    esd.ef.EP_WEIGHT_DEX_COMPLETION = 0.25
    esd.ef.EP_WEIGHT_SESSION_PROGRESS = 0.25
    esd.ef.EP_WEIGHT_CORE_TEAM_POWER = 0.25
    esd.ef.OVERHAUL_LEVEL_THRESHOLDS = {
        "Starter": 30,
        "Ultra": 30,
        "Legendary": 50,
        "Mega": 60,
        "Gmax": 65,
        "Mythical": 75,
    }
    
    esd.main_pokemon = mock.MagicMock()
    esd.main_pokemon.level = 50
    esd.trainer_card = mock.MagicMock()
    esd.trainer_card.level = 20
    esd.ankimon_tracker_obj = mock.MagicMock()
    esd.ankimon_tracker_obj.get_total_reviews.return_value = 100
    esd.settings_obj = mock.MagicMock()
    esd.settings_obj.get.return_value = 100

    # Define standard slider input state
    slider_state = {
        "trainer_level": 25,
        "dex_completion": 50.0,
        "reviews_done": 120,
        "daily_goal": 100,
        "avg_cp": 1500,
        "main_level": 45
    }

    # Call calculate_rates via class method directly to test logic
    result = esd.EncounterSimulatorDialog.calculate_rates(dialog, slider_state)
    
    # Assert return structure
    assert "live_overhaul" in result
    assert "live_legacy" in result
    assert "overhaul" in result
    assert "legacy" in result
    assert "ep" in result
    assert "locks" in result
    
    # Verify calculated EP matches formula under the new weights/caps:
    # t_norm = min((25 / 50.0) * 100.0, 100.0) = 50.0 -> 0.25 * 50 = 12.5
    # d_norm = 50.0 -> 0.25 * 50 = 12.5
    # s_norm = min((120 / 100.0) * 100.0, 100.0) = 100.0 -> 0.25 * 100 = 25.0
    # c_norm = min((1500 / 16000.0) * 100.0, 100.0) = 9.375 -> 0.25 * 9.375 = 2.34375
    # ep = 12.5 + 12.5 + 25.0 + 2.34375 = 52.34375
    assert abs(result["ep"] - 52.34375) < 0.001
    
    # Verify lock states at main_level = 45:
    # "Legendary" gating limit is 50, so locked = True
    # "Ultra" gating limit is 30, so locked = False
    assert result["locks"]["Legendary"] is True
    assert result["locks"]["Ultra"] is False
