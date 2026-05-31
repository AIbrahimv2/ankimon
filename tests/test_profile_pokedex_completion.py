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
        "aqt",
        "aqt.qt",
        "aqt.utils",
        "aqt.gui_hooks",
        "aqt.operations",
        "aqt.reviewer",
        "aqt.webview",
        "aqt.main",
        "aqt.operations.QueryOp",
        "anki",
        "anki.hooks",
        "anki.collection",
        "anki.models",
        "anki.notes",
        "anki.template",
        "anki.buildinfo",
    ]:
        if name not in sys.modules:
            sys.modules[name] = MagicMock()

    class MockResources:
        user_path = Path("/tmp")
        csv_file_items_cost = Path("/tmp/items.csv")
        items_path = Path("/tmp/items.json")
        badges_path = Path("/tmp/badges.json")
        mypokemon_path = Path("/tmp/mypokemon.json")
        mainpokemon_path = Path("/tmp/mainpokemon.json")

        def __getattr__(self, name):
            return Path("/tmp") / name

    if "Ankimon" not in sys.modules:
        sys.modules["Ankimon"] = Ankimon = types.ModuleType("Ankimon")
    else:
        Ankimon = sys.modules["Ankimon"]

    sys.modules["Ankimon.resources"] = MockResources()
    sys.modules["Ankimon.singletons"] = MagicMock()
    sys.modules["Ankimon.utils"] = MagicMock()
    sys.modules["Ankimon.pyobj"] = MagicMock()

    # Wire subpackages as attributes on the Ankimon parent module
    sys.modules["Ankimon.ankimon_profile_web"] = ankimon_profile_web = types.ModuleType(
        "Ankimon.ankimon_profile_web"
    )
    Ankimon.ankimon_profile_web = ankimon_profile_web

    if "Ankimon.functions" not in sys.modules:
        sys.modules["Ankimon.functions"] = Ankimon_functions = types.ModuleType(
            "Ankimon.functions"
        )
    else:
        Ankimon_functions = sys.modules["Ankimon.functions"]
    Ankimon.functions = Ankimon_functions


setup_mocks()

# Dynamically load database_manager
_db_spec = importlib.util.spec_from_file_location(
    "Ankimon.pyobj.database_manager",
    _src / "Ankimon" / "pyobj" / "database_manager.py",
)
_db_mod = importlib.util.module_from_spec(_db_spec)
sys.modules[_db_spec.name] = _db_mod
_db_spec.loader.exec_module(_db_mod)

from Ankimon.pyobj.database_manager import AnkimonDB

# Dynamically load profile_data
_profile_spec = importlib.util.spec_from_file_location(
    "Ankimon.ankimon_profile_web.profile_data",
    _src / "Ankimon" / "ankimon_profile_web" / "profile_data.py",
)
_profile_mod = importlib.util.module_from_spec(_profile_spec)
sys.modules[_profile_spec.name] = _profile_mod
_profile_spec.loader.exec_module(_profile_mod)

# Attach profile_data module as an attribute to its package
sys.modules["Ankimon"].ankimon_profile_web.profile_data = _profile_mod

from Ankimon.ankimon_profile_web.profile_data import ProfileData


class MockLogger:
    def log(self, level, msg):
        pass

    def log_and_showinfo(self, level, msg):
        pass

    def _log(self, level, msg):
        pass


@pytest.fixture
def temp_db(tmp_path):
    """Setup a temporary database manager in a clean environment."""
    with patch.object(_db_mod, "user_path", tmp_path):
        db = AnkimonDB(MockLogger())
        yield db


def test_profile_pokedex_completion(temp_db):
    """
    Verifies that the Profile Pokédex count:
    1. Deduplicates special forms (Megas, regional variants) to their base species_id.
    2. Includes currently owned box Pokémon.
    3. Includes released Pokémon from history.
    4. Includes explicitly registered caught history.
    """
    db = temp_db

    # Mock aqt and mw namespaces
    import aqt

    mw = MagicMock()
    mw.ankimon_db = db
    mw.settings_obj = MagicMock()
    mw.settings_obj.get.return_value = "red"

    # Inject pokedex_functions module into sys.modules and wire it
    import Ankimon.functions.pokedex_functions as pf

    sys.modules["Ankimon"].functions.pokedex_functions = pf

    with (
        patch("Ankimon.ankimon_profile_web.profile_data.mw", mw),
        patch("Ankimon.functions.pokedex_functions.mw", mw),
    ):
        # Set up a miniature mock of the Pokedex caches in memory
        pf._pokedex_cache = {
            "charizard": {"species_id": 6, "actual_id": 3, "name": "Charizard"},
            "charizardmega": {
                "species_id": 6,
                "actual_id": 10091,
                "name": "Charizard-Mega-X",
            },
            "bulbasaur": {"species_id": 1, "actual_id": 1, "name": "Bulbasaur"},
            "vulpix": {"species_id": 37, "actual_id": 37, "name": "Vulpix"},
            "vulpixalola": {
                "species_id": 37,
                "actual_id": 10100,
                "name": "Vulpix-Alola",
            },
        }
        pf._pokedex_id_index = {
            3: "charizard",
            10091: "charizardmega",
            1: "bulbasaur",
            37: "vulpix",
            10100: "vulpixalola",
        }

        # 1. Currently Owned Pokémon in Box:
        # Regular Charizard (species_id 6)
        db.save_pokemon(
            {
                "individual_id": "c1",
                "id": 3,
                "name": "Charizard",
                "level": 50,
                "shiny": False,
            }
        )
        # Mega Charizard X (species_id 6) -> should be deduplicated to the same species!
        db.save_pokemon(
            {
                "individual_id": "c2",
                "id": 10091,
                "name": "Charizard-Mega-X",
                "level": 60,
                "shiny": False,
            }
        )

        # 2. Released Pokémon in History:
        # Bulbasaur (species_id 1)
        db.add_to_history(
            {"individual_id": "b1", "id": 1, "name": "Bulbasaur", "level": 15}
        )

        # 3. Explicitly Marked Caught (Evolutions/other logic):
        # Alolan Vulpix (species_id 37)
        db.mark_as_caught(10100)

        # 4. Instantiate ProfileData and fetch stats
        trainer_card = MagicMock()
        trainer_card.highest_pokemon_level.return_value = 60
        profile = ProfileData(
            addon_dir=Path("/tmp"),
            trainer_card=trainer_card,
            settings_obj=mw.settings_obj,
            logger=MagicMock(),
        )

        stats = profile._collection_stats()

        # Caught currently in box = 2 (Charizard + Mega Charizard)
        assert stats["caught"] == 2

        # Dex unique base species caught = 3 (Species 6 + Species 1 + Species 37)
        assert stats["dex_seen"] == 3

        # Check other stats are populated correctly
        assert stats["shinies"] == 0
        assert stats["highest_level"] == 60
