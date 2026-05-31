import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

# Make sure src is in sys.path
_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

class DummyBase:
    pass

# Define minimal mock of aqt/PyQt6
def _install_aqt_stubs():
    # Clean up previous modules if any, but preserve top-level conftest package stubs
    for mod_name in list(sys.modules):
        if (mod_name.startswith("Ankimon.") and not mod_name.startswith("Ankimon.functions")) or \
           mod_name in ("aqt", "aqt.qt", "aqt.utils", "anki", "anki.buildinfo"):
            sys.modules.pop(mod_name, None)

    aqt_stub = types.ModuleType("aqt")
    aqt_stub.mw = MagicMock()
    aqt_stub.QDialog = DummyBase
    aqt_stub.QVBoxLayout = DummyBase
    aqt_stub.QWebEngineView = DummyBase
    sys.modules["aqt"] = aqt_stub

    aqt_utils = MagicMock()
    sys.modules["aqt.utils"] = aqt_utils

    aqt_qt = MagicMock()
    sys.modules["aqt.qt"] = aqt_qt

    # Stub anki
    sys.modules["anki"] = MagicMock()
    anki_buildinfo = MagicMock()
    anki_buildinfo.version = "2.1.66"
    sys.modules["anki.buildinfo"] = anki_buildinfo

    sys.modules["PyQt6"] = MagicMock()

    for sub in ("QtCore", "QtGui", "QtWebChannel", "QtWidgets", "QtMultimedia"):
        mod = MagicMock()
        # pyqtSlot must be a real function returning decorator
        mod.pyqtSlot = lambda *a, **k: (lambda f: f)
        mod.QObject = DummyBase
        sys.modules[f"PyQt6.{sub}"] = mod

def test_wishlist_serialization():
    _install_aqt_stubs()

    from Ankimon.ankimon_items_web.shop_obj import AnkimonItemsWeb

    # We want to test _serialize_setting for the battle.auto_catch_wishlist key
    key = "battle.auto_catch_wishlist"
    friendly = "Always Catch Wishlist"
    name_map = {}
    desc_map = {key: "Always catch these Pokemon"}
    value = [25, 133, 9999] # Pikachu, Eevee, and unknown/bad ID

    entry = AnkimonItemsWeb._serialize_setting(key, friendly, name_map, desc_map, value)

    assert entry["key"] == key
    assert entry["type"] == "wishlist"
    assert entry["value"] == value
    assert "names" in entry
    
    names = entry["names"]
    # Check that standard names are correctly resolved
    assert names[25] == "Pikachu"
    assert names[133] == "Eevee"
    # Check fallback for unknown/bad ID
    assert names[9999] == "Pokémon not found"
