import sys
import types
from unittest.mock import MagicMock, patch
import pytest
from pathlib import Path

class DynamicMockModule(types.ModuleType):
    """A module stub that dynamically returns MagicMocks for any attribute requests,
    preventing PyQt/Anki module import and lookup errors."""
    def __getattr__(self, name):
        mock = MagicMock()
        setattr(self, name, mock)
        return mock

@pytest.fixture
def tracker_class():
    """Locally imports and provides the AnkimonTracker class using direct file loading with temporary stubs in sys.modules,
    fully restoring the module namespace afterward to prevent side effects."""
    original_modules = dict(sys.modules)

    mocks = {
        "aqt": DynamicMockModule("aqt"),
        "aqt.qt": DynamicMockModule("aqt.qt"),
        "aqt.utils": DynamicMockModule("aqt.utils"),
        "PyQt6": DynamicMockModule("PyQt6"),
        "PyQt6.QtWidgets": DynamicMockModule("PyQt6.QtWidgets"),
        "PyQt6.QtCore": DynamicMockModule("PyQt6.QtCore"),
        "PyQt6.QtMultimedia": DynamicMockModule("PyQt6.QtMultimedia"),
        "anki": DynamicMockModule("anki"),
        "anki.buildinfo": DynamicMockModule("anki.buildinfo"),
    }

    # Temporarily patch sys.modules to isolate our mocks to the import block
    with patch.dict(sys.modules, mocks):
        import importlib.util
        _src = Path(__file__).parent.parent / "src"
        
        spec = importlib.util.spec_from_file_location(
            "Ankimon.pyobj.ankimon_tracker",
            _src / "Ankimon" / "pyobj" / "ankimon_tracker.py"
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["Ankimon.pyobj.ankimon_tracker"] = mod
        spec.loader.exec_module(mod)
        
        tracker_cls = mod.AnkimonTracker
        yield tracker_cls

    # Restore sys.modules to EXACTLY its pre-test state, resolving test suite side effects
    for key in list(sys.modules):
        if key not in original_modules:
            del sys.modules[key]
        else:
            sys.modules[key] = original_modules[key]


def test_get_total_reviews_database_success(tracker_class):
    """Test that get_total_reviews queries the database and returns the result."""
    trainer_card = MagicMock()
    tracker = tracker_class(trainer_card)

    mock_col = MagicMock()
    mock_col.sched.day_cutoff = 1716800000
    mock_col.db.scalar.return_value = 42

    with patch("Ankimon.pyobj.ankimon_tracker.mw") as mock_mw:
        mock_mw.col = mock_col
        reviews = tracker.get_total_reviews()
        assert reviews == 42
        mock_col.db.scalar.assert_called_once_with(
            "SELECT count() FROM revlog WHERE id > ?", (1716800000 - 86400) * 1000
        )

def test_get_total_reviews_database_failure_fallback_english(tracker_class):
    """Test that get_total_reviews falls back to regex parsing when the database query fails."""
    trainer_card = MagicMock()
    tracker = tracker_class(trainer_card)

    mock_col = MagicMock()
    mock_col.sched.day_cutoff = 1716800000
    mock_col.db.scalar.side_effect = Exception("Database is locked")
    mock_col.studied_today.return_value = "Studied 15 cards in 3.2 minutes today."

    with patch("Ankimon.pyobj.ankimon_tracker.mw") as mock_mw:
        mock_mw.col = mock_col
        reviews = tracker.get_total_reviews()
        assert reviews == 15
        mock_col.studied_today.assert_called_once()

def test_get_total_reviews_database_failure_fallback_localized(tracker_class):
    """Test that get_total_reviews falls back to extracting the first number when database query fails on localized strings."""
    trainer_card = MagicMock()
    tracker = tracker_class(trainer_card)

    mock_col = MagicMock()
    mock_col.sched.day_cutoff = 1716800000
    mock_col.db.scalar.side_effect = Exception("Database is locked")
    mock_col.studied_today.return_value = "Heute 27 Karten in 5.4 Minuten gelernt."

    with patch("Ankimon.pyobj.ankimon_tracker.mw") as mock_mw:
        mock_mw.col = mock_col
        reviews = tracker.get_total_reviews()
        assert reviews == 27

def test_get_total_reviews_no_collection(tracker_class):
    """Test that get_total_reviews returns 0 when mw.col is None."""
    trainer_card = MagicMock()
    tracker = tracker_class(trainer_card)

    with patch("Ankimon.pyobj.ankimon_tracker.mw") as mock_mw:
        mock_mw.col = None
        reviews = tracker.get_total_reviews()
        assert reviews == 0
