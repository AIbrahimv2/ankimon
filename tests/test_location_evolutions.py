import pytest
import os
import sys
import json
from unittest.mock import MagicMock
from datetime import datetime

# Restore correct resources to prevent test pollution
import aqt
import Ankimon.resources as resources
import Ankimon.functions.pokedex_functions as pf
import Ankimon.functions.friendship_evolution as fe

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
actual_pokedex_path = os.path.join(base_dir, "src", "Ankimon", "data_files", "pokedex.json")
actual_items_path = os.path.join(base_dir, "src", "Ankimon", "data_files", "items.csv")

# Setup dynamic mock environment
@pytest.fixture(autouse=True)
def setup_mock_environment(monkeypatch):
    # Restore actual resource paths to prevent test pollution
    monkeypatch.setattr(resources, "pokedex_path", actual_pokedex_path)
    monkeypatch.setattr(pf, "pokedex_path", actual_pokedex_path)
    monkeypatch.setattr(resources, "csv_file_items_cost", actual_items_path)
    monkeypatch.setattr(pf, "csv_file_items_cost", actual_items_path)
    
    # Reset pokedex cache and lru_caches
    pf._pokedex_cache = None
    pf._pokedex_id_index = None
    fe.get_level_evolutions_for_species.cache_clear()
    fe.get_friendship_evolutions_for_species.cache_clear()
    
    # Mock settings cleanly without breaking other settings
    mock_settings = MagicMock()
    mock_settings.active_region_val = "No Region"
    
    def get_setting(key, default=None):
        if key == "misc.active_region":
            return mock_settings.active_region_val
        if key == "evolution.day_start_hour":
            return 6
        if key == "evolution.night_start_hour":
            return 18
        return default
        
    mock_settings.get.side_effect = get_setting
    
    # Mock database
    mock_db = MagicMock()
    mock_db.get_pokemon.return_value = {
        "id": 234, # Stantler
        "attacks": ["Psyshield Bash", "Tackle"]
    }
    
    # Mock main window (mw)
    mock_mw = MagicMock()
    mock_mw.settings_obj = mock_settings
    mock_mw.ankimon_db = mock_db
    
    # Set sys.modules["aqt"].mw directly to bypass mock overrides
    if "aqt" in sys.modules:
        monkeypatch.setattr(sys.modules["aqt"], "mw", mock_mw)
    monkeypatch.setattr(aqt, "mw", mock_mw)
    monkeypatch.setattr(pf, "mw", mock_mw)
    
    return mock_mw

def test_pikachu_evolution_by_active_region():
    # Pikachu is ID 25, Thunder Stone is item ID 83
    # Under "No Region", should evolve into standard Raichu (ID 26)
    pf.mw.settings_obj.active_region_val = "No Region"
    evo_id = pf.check_evolution_by_item(25, 83)
    assert evo_id == 26

    # Under "Alola", should evolve into Alolan Raichu (ID 10100)
    pf.mw.settings_obj.active_region_val = "Alola"
    evo_id = pf.check_evolution_by_item(25, 83)
    assert evo_id == 10100

    # Under "Galar", should evolve into standard Raichu (ID 26)
    pf.mw.settings_obj.active_region_val = "Galar"
    evo_id = pf.check_evolution_by_item(25, 83)
    assert evo_id == 26

def test_exeggcute_evolution_by_active_region():
    # Exeggcute is ID 102, Leaf Stone is item ID 85
    # Under "No Region", should evolve into standard Exeggutor (ID 103)
    pf.mw.settings_obj.active_region_val = "No Region"
    evo_id = pf.check_evolution_by_item(102, 85)
    assert evo_id == 103

    # Under "Alola", should evolve into Alolan Exeggutor (ID 10114)
    pf.mw.settings_obj.active_region_val = "Alola"
    evo_id = pf.check_evolution_by_item(102, 85)
    assert evo_id == 10114

def test_koffing_evolution_by_active_region():
    # Koffing is ID 109
    # Level-up checking mocks
    mock_evo_window = MagicMock()
    
    # Under "No Region" at Level 35, should evolve into standard Weezing (ID 110)
    pf.mw.settings_obj.active_region_val = "No Region"
    evo_id = pf.check_evolution_for_pokemon("p1", 109, 35, mock_evo_window)
    assert evo_id == 110
    mock_evo_window.ask_pokemon_evo.assert_called_with("p1", 109, 110)
    
    # Under "Galar" at Level 35, should evolve into Galarian Weezing (ID 10167)
    mock_evo_window.reset_mock()
    pf.mw.settings_obj.active_region_val = "Galar"
    evo_id = pf.check_evolution_for_pokemon("p2", 109, 35, mock_evo_window)
    assert evo_id == 10167
    mock_evo_window.ask_pokemon_evo.assert_called_with("p2", 109, 10167)

def test_dartrix_evolution_by_active_region():
    # Dartrix is ID 723
    mock_evo_window = MagicMock()
    
    # Under "No Region" at Level 36, should evolve into Decidueye (ID 724)
    pf.mw.settings_obj.active_region_val = "No Region"
    evo_id = pf.check_evolution_for_pokemon("p1", 723, 36, mock_evo_window)
    assert evo_id == 724
    
    # Under "Hisui" at Level 36, should evolve into Hisuian Decidueye (ID 10244)
    pf.mw.settings_obj.active_region_val = "Hisui"
    evo_id = pf.check_evolution_for_pokemon("p2", 723, 36, mock_evo_window)
    assert evo_id == 10244

def test_hisuian_item_evolutions_enriched():
    # Scyther (ID 123) + Black Augurite (item ID 10001) in Hisui -> Kleavor (ID 900)
    pf.mw.settings_obj.active_region_val = "Hisui"
    evo_id = pf.check_evolution_by_item(123, 10001)
    assert evo_id == 900
    
    # Outside Hisui, should not evolve using Black Augurite
    pf.mw.settings_obj.active_region_val = "No Region"
    evo_id = pf.check_evolution_by_item(123, 10001)
    assert evo_id is None
    
    # Ursaring (ID 217) + Peat Block (item ID 10002) in Hisui -> Ursaluna (ID 901)
    pf.mw.settings_obj.active_region_val = "Hisui"
    evo_id = pf.check_evolution_by_item(217, 10002)
    assert evo_id == 901

def test_stantler_wyrdeer_move_based_evolution():
    # Stantler (ID 234) level-up knowing move "Psyshield Bash"
    mock_evo_window = MagicMock()
    
    # 1. Knowing the move, under Hisui -> Wyrdeer (ID 899)
    pf.mw.settings_obj.active_region_val = "Hisui"
    pf.mw.ankimon_db.get_pokemon.return_value = {
        "id": 234,
        "attacks": ["Psyshield Bash", "Tackle"]
    }
    evo_id = pf.check_evolution_for_pokemon("p1", 234, 30, mock_evo_window)
    assert evo_id == 899
    
    # 2. Knowing the move, outside Hisui -> None
    pf.mw.settings_obj.active_region_val = "No Region"
    evo_id = pf.check_evolution_for_pokemon("p1", 234, 30, mock_evo_window)
    assert evo_id is None
    
    # 3. Not knowing the move -> None
    pf.mw.settings_obj.active_region_val = "Hisui"
    pf.mw.ankimon_db.get_pokemon.return_value = {
        "id": 234,
        "attacks": ["Tackle", "Growl"]
    }
    evo_id = pf.check_evolution_for_pokemon("p1", 234, 30, mock_evo_window)
    assert evo_id is None

def test_manual_readiness_filtering_cubone():
    # Cubone is ID 104, has level evolution
    # Under "No Region", Cubone at Level 28 should be ready for standard Marowak (ID 105)
    pf.mw.settings_obj.active_region_val = "No Region"
    result = fe.evolution_readiness({"id": 104, "level": 28}, now=datetime(2026, 1, 1, 12, 0))
    assert result["evolvable"] is True
    assert result["evo_id"] == 105
    assert "Marowak" in result["evo_name"]
    assert "Alola" not in result["evo_name"]

    # Under "Alola", Cubone at Level 28 at night should be ready for Marowak-Alola (ID 10115)
    pf.mw.settings_obj.active_region_val = "Alola"
    result = fe.evolution_readiness({"id": 104, "level": 28}, now=datetime(2026, 1, 1, 23, 0))
    assert result["evolvable"] is True
    assert result["evo_id"] == 10115
    assert "Alola" in result["evo_name"]

def test_mimejr_manual_evolution_readiness():
    # Mime Jr. is ID 439
    # 1. Under "No Region" knowing Mimic, Mime Jr. should be ready to evolve into Mr. Mime (ID 122)
    pf.mw.settings_obj.active_region_val = "No Region"
    result = fe.evolution_readiness({
        "id": 439,
        "level": 32,
        "attacks": ["Mimic", "Confusion"],
        "everstone": False,
        "evolution_rejected": False
    }, now=datetime(2026, 1, 1, 12, 0))
    assert result["evolvable"] is True
    assert result["ready"] is True
    assert result["evo_id"] == 122
    assert "Mr. Mime" in result["evo_name"]
    assert "Galar" not in result["evo_name"]

    # 2. Under "No Region" NOT knowing Mimic, Mime Jr. should NOT be ready, evolvable is True (shows in list), ready is False, and status_text mentions Mimic
    result = fe.evolution_readiness({
        "id": 439,
        "level": 32,
        "attacks": ["Confusion", "Tackle"],
        "everstone": False,
        "evolution_rejected": False
    }, now=datetime(2026, 1, 1, 12, 0))
    assert result["evolvable"] is True
    assert result["ready"] is False
    assert "Needs to learn Mimic" in result["status_text"]

def test_mrmime_evolution_distinction():
    # 1. Kantonian Mr. Mime (ID 122) has no evolutions in pokedex.json (should not evolve to Mr. Rime)
    result_normal = fe.evolution_readiness({
        "id": 122,
        "level": 50,
        "attacks": ["Mimic"],
        "everstone": False,
        "evolution_rejected": False
    }, now=datetime(2026, 1, 1, 12, 0))
    assert result_normal["evolvable"] is False
    assert result_normal["ready"] is False

    # 2. Galarian Mr. Mime (actual_id 10168) has evo Mr. Rime (ID 866) in pokedex.json
    # It should be ready at level 42+
    result_galar = fe.evolution_readiness({
        "id": 10168,
        "level": 42,
        "attacks": ["Mimic"],
        "everstone": False,
        "evolution_rejected": False
    }, now=datetime(2026, 1, 1, 12, 0))
    assert result_galar["evolvable"] is True
    assert result_galar["ready"] is True
    assert result_galar["evo_id"] == 866
    assert "Mr. Rime" in result_galar["evo_name"]


