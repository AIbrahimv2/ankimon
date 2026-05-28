import sys
import os
import types
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

_src = Path(__file__).parent.parent / "src"

class MockQWidget:
    def __init__(self, *args, **kwargs):
        pass
    def setStyleSheet(self, *args): pass
    def setMaximumWidth(self, *args): pass
    def setMaximumHeight(self, *args): pass
    def layout(self): return MagicMock()
    def setLayout(self, *args): pass
    def close(self): pass
    def show(self): pass

def setup_mocks():
    # 1. Register packages with __path__ so relative imports resolve
    for _pkg in ("Ankimon", "Ankimon.functions", "Ankimon.pyobj"):
        if _pkg not in sys.modules or isinstance(sys.modules[_pkg], MagicMock):
            _mod = types.ModuleType(_pkg)
            _mod.__path__ = [str(_src / _pkg.replace(".", "/"))]
            _mod.__package__ = _pkg
            sys.modules[_pkg] = _mod

    # 2. Mock external dependencies and imported submodules defensively
    for name in [
        "aqt", "aqt.utils", "aqt.gui_hooks", "aqt.operations", 
        "aqt.reviewer", "aqt.webview", "aqt.main", "aqt.theme",
        "anki", "anki.hooks", "anki.collection",
        "Ankimon.singletons",
        "Ankimon.pyobj.error_handler",
        "Ankimon.pyobj.attack_dialog",
        "Ankimon.pyobj.settings",
        "Ankimon.pyobj.pokemon_obj",
        "Ankimon.pyobj.InfoLogger",
        "Ankimon.pyobj.translator",
        "Ankimon.pyobj.test_window",
        "Ankimon.pyobj.reviewer_obj",
        "Ankimon.resources",
        "Ankimon.business",
        "Ankimon.utils",
        "Ankimon.functions.pokedex_functions",
        "Ankimon.functions.pokemon_functions",
        "Ankimon.functions.battle_functions",
        "Ankimon.functions.update_main_pokemon",
        "Ankimon.functions.badges_functions",
    ]:
        if name not in sys.modules or isinstance(sys.modules[name], MagicMock):
            sys.modules[name] = MagicMock()

    # Stub aqt.qt specifically if not already stubbed or if it's a MagicMock
    if "aqt.qt" not in sys.modules or isinstance(sys.modules["aqt.qt"], MagicMock):
        aqt_qt = MagicMock()
        aqt_qt.QWidget = MockQWidget
        aqt_qt.QDialog = MockQWidget
        sys.modules["aqt.qt"] = aqt_qt

setup_mocks()

# Dynamically load evolution_window.py (only if not already loaded or reload to apply our stubbed module-level variables)
_spec = importlib.util.spec_from_file_location(
    "Ankimon.pyobj.evolution_window",
    _src / "Ankimon" / "pyobj" / "evolution_window.py",
)
_evo_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _evo_mod
_spec.loader.exec_module(_evo_mod)

# Retrieve the real EvoWindow class directly from sys.modules to bypass package mock attribute lookup
EvoWindow = sys.modules["Ankimon.pyobj.evolution_window"].EvoWindow

# Create a test subclass to bypass QWidget and __init__ side effects
class MockEvoWindow(EvoWindow):
    def __init__(self):
        self.logger = MagicMock()
        self.translator = MagicMock()
        self.reviewer_obj = MagicMock()
        self.test_window = MagicMock()
        self.achievements = {}

def test_evolve_pokemon_consumes_stone():
    evo_win_module = sys.modules["Ankimon.pyobj.evolution_window"]
    mock_db = MagicMock()
    
    # Directly attach our mock database to whatever mw object the loaded module is referencing
    evo_win_module.mw.ankimon_db = mock_db
    
    with patch("Ankimon.pyobj.evolution_window.search_pokedex") as mock_search, \
         patch("Ankimon.pyobj.evolution_window.get_random_moves_for_pokemon") as mock_moves, \
         patch("Ankimon.pyobj.evolution_window.calculate_hp") as mock_hp, \
         patch("Ankimon.pyobj.evolution_window.get_growth_rate") as mock_growth, \
         patch("Ankimon.pyobj.evolution_window.get_base_experience") as mock_base_exp, \
         patch("Ankimon.pyobj.evolution_window.calculate_cp_from_dict") as mock_cp, \
         patch("Ankimon.pyobj.evolution_window.update_main_pokemon") as mock_update_main, \
         patch("Ankimon.pyobj.evolution_window.check_for_badge") as mock_badge, \
         patch("Ankimon.pyobj.evolution_window.is_alive", return_value=False):
         
         evo_win = MockEvoWindow()
         evo_win.display_evo_complete = MagicMock()
         
         mock_db.get_pokemon.return_value = {
             "id": 133,
             "name": "Eevee",
             "level": 20,
             "attacks": [],
             "iv": {},
             "ev": {},
             "xp": 100,
         }
         
         mock_search.side_effect = lambda name, key: ["Fire"] if key == "types" else {"hp": 50} if key == "baseStats" else {}
         mock_moves.return_value = []
         mock_hp.return_value = 100
         mock_growth.return_value = "medium"
         mock_base_exp.return_value = 100
         mock_cp.return_value = 500
         mock_update_main.return_value = (None, None)
         mock_badge.return_value = True
         
         evo_win.evolve_pokemon(
             individual_id="some-uuid",
             prevo_id=133,
             prevo_name="eevee",
             evo_id=136,
             evo_name="flareon",
             main_pokemon=None,
             item_name="fire-stone"
         )
         
         mock_db.update_item_quantity.assert_called_once_with("fire-stone", -1)

def test_evolve_pokemon_nickname_update():
    evo_win_module = sys.modules["Ankimon.pyobj.evolution_window"]
    mock_db = MagicMock()
    evo_win_module.mw.ankimon_db = mock_db
    
    with patch("Ankimon.pyobj.evolution_window.search_pokedex") as mock_search, \
         patch("Ankimon.pyobj.evolution_window.get_random_moves_for_pokemon") as mock_moves, \
         patch("Ankimon.pyobj.evolution_window.calculate_hp") as mock_hp, \
         patch("Ankimon.pyobj.evolution_window.get_growth_rate") as mock_growth, \
         patch("Ankimon.pyobj.evolution_window.get_base_experience") as mock_base_exp, \
         patch("Ankimon.pyobj.evolution_window.calculate_cp_from_dict") as mock_cp, \
         patch("Ankimon.pyobj.evolution_window.update_main_pokemon") as mock_update_main, \
         patch("Ankimon.pyobj.evolution_window.check_for_badge") as mock_badge, \
         patch("Ankimon.pyobj.evolution_window.is_alive", return_value=False):
         
         evo_win = MockEvoWindow()
         evo_win.display_evo_complete = MagicMock()
         
         mock_search.side_effect = lambda name, key: ["Psychic"] if key == "types" else {"hp": 40} if key == "baseStats" else {}
         mock_moves.return_value = []
         mock_hp.return_value = 80
         mock_growth.return_value = "medium"
         mock_base_exp.return_value = 100
         mock_cp.return_value = 400
         mock_update_main.return_value = (None, None)
         mock_badge.return_value = True
         
         # Mock pretty name translation function directly on pokedex_functions module
         pokedex_funcs = sys.modules["Ankimon.functions.pokedex_functions"]
         def get_pretty_name_mock(sid):
             if sid == 439:
                 return "Mime Jr."
             if sid == 122:
                 return "Mr. Mime"
             return "Unknown"
         pokedex_funcs.get_pretty_name_for_id = get_pretty_name_mock

         # Case 1: Nickname matches pretty prevo name ("Mime Jr.") or CSV identifier ("mime-jr")
         # Both should be evolved to the pretty name of the evolved form ("Mr. Mime")
         pokemon_data = {
             "id": 439,
             "name": "Mime Jr.",
             "nickname": "Mime Jr.",
             "level": 32,
             "attacks": ["Mimic"],
             "iv": {},
             "ev": {},
             "xp": 100,
         }
         mock_db.get_pokemon.return_value = pokemon_data
         
         evo_win.evolve_pokemon(
             individual_id="some-uuid",
             prevo_id=439,
             prevo_name="mime-jr",
             evo_id=122,
             evo_name="mr-mime",
             main_pokemon=None
         )
         
         # Should update nickname to the pretty name
         mock_db.save_pokemon.assert_called_with(pokemon_data)
         assert pokemon_data["nickname"] == "Mr. Mime"
         
         # Case 2: Custom Nickname ("Sparky") should be preserved
         pokemon_data_custom = {
             "id": 439,
             "name": "Mime Jr.",
             "nickname": "Sparky",
             "level": 32,
             "attacks": ["Mimic"],
             "iv": {},
             "ev": {},
             "xp": 100,
         }
         mock_db.get_pokemon.return_value = pokemon_data_custom
         
         evo_win.evolve_pokemon(
             individual_id="some-uuid",
             prevo_id=439,
             prevo_name="mime-jr",
             evo_id=122,
             evo_name="mr-mime",
             main_pokemon=None
         )
         
         assert pokemon_data_custom["nickname"] == "Sparky"
