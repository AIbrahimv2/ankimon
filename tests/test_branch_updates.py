import os
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Mock aqt/anki namespaces if not already mocked by conftest
for name in [
    "aqt", "aqt.qt", "aqt.utils", "aqt.gui_hooks", "aqt.operations", 
    "aqt.reviewer", "aqt.webview", "aqt.main",
    "anki", "anki.hooks", "anki.collection", "anki.models", "anki.notes", "anki.template", "anki.buildinfo"
]:
    if name not in sys.modules:
        sys.modules[name] = MagicMock()

# Ensure QueryOp mock is set up for operations
if "aqt.operations" in sys.modules:
    sys.modules["aqt.operations"].QueryOp = MagicMock()

# Add the 'src' directory to sys.path to resolve absolute package imports
ANKIMON_SRC_PARENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src")
)
if ANKIMON_SRC_PARENT_DIR not in sys.path:
    sys.path.insert(0, ANKIMON_SRC_PARENT_DIR)

# Import the actual modules under test
from Ankimon.pyobj import update_manager
from Ankimon import changelog


def test_update_state_read_write(tmp_path):
    """Test saving and reading the update state to update_state.json."""
    state_file = tmp_path / "update_state.json"
    
    with patch.object(update_manager, "get_update_state_path", return_value=state_file):
        # When file doesn't exist, read_update_state should return None
        assert update_manager.read_update_state() is None
        
        # Save state
        update_manager.save_update_state("branch", "BRRRR_Experimental", "c0ffee12345", skip_until=999999.9)
        
        # Verify it exists and matches
        assert state_file.exists()
        state = update_manager.read_update_state()
        assert state is not None
        assert state["source_type"] == "branch"
        assert state["source_name"] == "BRRRR_Experimental"
        assert state["commit_sha"] == "c0ffee12345"
        assert state["skip_until"] == 999999.9

        # Test set_update_skip_until
        update_manager.set_update_skip_until(888888.8)
        state = update_manager.read_update_state()
        assert state["skip_until"] == 888888.8


@patch("Ankimon.pyobj.update_manager._api_get")
def test_fetch_branch_sha(mock_api_get):
    """Test fetching branch commit SHA from GitHub API."""
    mock_api_get.return_value = {
        "name": "BRRRR_Experimental",
        "commit": {
            "sha": "a1b2c3d4e5f6"
        }
    }
    sha = update_manager.fetch_branch_sha("BRRRR_Experimental")
    assert sha == "a1b2c3d4e5f6"
    mock_api_get.assert_called_with("branches/BRRRR_Experimental")


@patch("Ankimon.pyobj.update_manager._api_get")
def test_fetch_commit_date(mock_api_get):
    """Test fetching commit date from GitHub API."""
    mock_api_get.return_value = {
        "sha": "a1b2c3d4e5f6",
        "commit": {
            "committer": {
                "date": "2026-05-24T12:00:00Z"
            }
        }
    }
    date = update_manager.fetch_commit_date("a1b2c3d4e5f6")
    assert date == "2026-05-24T12:00:00Z"
    mock_api_get.assert_called_with("commits/a1b2c3d4e5f6")
    
    # Test invalid SHA
    assert update_manager.fetch_commit_date("") is None
    assert update_manager.fetch_commit_date("not-a-sha") is None


@patch("Ankimon.changelog.QueryOp")
@patch("Ankimon.pyobj.update_manager.read_update_state")
def test_check_branch_update_no_state(mock_read_state, mock_query_op):
    """Test check_branch_update does nothing if no update state exists."""
    mock_read_state.return_value = None
    changelog.check_branch_update(True, True)
    mock_query_op.assert_not_called()


@patch("Ankimon.changelog.QueryOp")
@patch("Ankimon.pyobj.update_manager.read_update_state")
def test_check_branch_update_not_experimental_branch(mock_read_state, mock_query_op):
    """Test check_branch_update does nothing if not on BRRRR_Experimental."""
    mock_read_state.return_value = {
        "source_type": "branch",
        "source_name": "main",
        "commit_sha": "abc1234"
    }
    changelog.check_branch_update(True, True)
    mock_query_op.assert_not_called()


@patch("Ankimon.changelog.QueryOp")
@patch("Ankimon.pyobj.update_manager.read_update_state")
def test_check_branch_update_on_experimental_branch(mock_read_state, mock_query_op):
    """Test check_branch_update starts QueryOp if on BRRRR_Experimental."""
    mock_read_state.return_value = {
        "source_type": "branch",
        "source_name": "BRRRR_Experimental",
        "commit_sha": "abc1234"
    }
    changelog.check_branch_update(True, True)
    mock_query_op.assert_called_once()


@patch("Ankimon.pyobj.update_manager._api_get")
def test_fetch_branch_commits_compare(mock_api_get):
    """Test fetching branch commits using the compare API."""
    mock_api_get.return_value = {
        "commits": [
            {
                "sha": "abcdef123456",
                "commit": {
                    "message": "First commit message\nSome detail"
                }
            },
            {
                "sha": "789012345678",
                "commit": {
                    "message": "Second commit message"
                }
            }
        ]
    }
    commits = update_manager.fetch_branch_commits("BRRRR_Experimental", "abc1234")
    assert len(commits) == 2
    # Commits are in reversed order (newest first)
    assert commits[0]["sha"] == "7890123"
    assert commits[0]["message"] == "Second commit message"
    assert commits[1]["sha"] == "abcdef1"
    assert commits[1]["message"] == "First commit message"
    mock_api_get.assert_called_with("compare/abc1234...BRRRR_Experimental")


@patch("Ankimon.pyobj.update_manager._api_get")
def test_fetch_branch_commits_fallback(mock_api_get):
    """Test fetching branch commits using the fallback commits list API."""
    mock_api_get.return_value = [
        {
            "sha": "111111122222",
            "commit": {
                "message": "Fallback commit message 1"
            }
        },
        {
            "sha": "333333344444",
            "commit": {
                "message": "Fallback commit message 2\nWith some details"
            }
        }
    ]
    # No local_sha passed, should fallback to commits endpoint
    commits = update_manager.fetch_branch_commits("BRRRR_Experimental")
    assert len(commits) == 2
    assert commits[0]["sha"] == "1111111"
    assert commits[0]["message"] == "Fallback commit message 1"
    assert commits[1]["sha"] == "3333333"
    assert commits[1]["message"] == "Fallback commit message 2"
    mock_api_get.assert_called_with("commits?sha=BRRRR_Experimental&per_page=5")


@patch("Ankimon.changelog.QueryOp")
@patch("Ankimon.pyobj.update_manager.read_update_state")
@patch("Ankimon.pyobj.update_manager.fetch_branch_sha")
@patch("Ankimon.pyobj.update_manager.fetch_branch_commits")
def test_check_branch_update_bg_op(mock_fetch_commits, mock_fetch_sha, mock_read_state, mock_query_op):
    """Test that the background operation in check_branch_update fetches SHA and commits."""
    mock_read_state.return_value = {
        "source_type": "branch",
        "source_name": "BRRRR_Experimental",
        "commit_sha": "local_sha_123"
    }
    mock_fetch_sha.return_value = "remote_sha_456"
    mock_fetch_commits.return_value = [{"sha": "7890123", "message": "Commit message"}]
    
    changelog.check_branch_update(True, True)
    
    # Get the background operation function passed to QueryOp
    mock_query_op.assert_called_once()
    kwargs = mock_query_op.call_args[1]
    bg_func = kwargs.get("op") or mock_query_op.call_args[0][1]
    
    # Run the background function
    res_sha, res_commits = bg_func(None)
    
    assert res_sha == "remote_sha_456"
    assert res_commits == [{"sha": "7890123", "message": "Commit message"}]
    mock_fetch_sha.assert_called_once_with("BRRRR_Experimental")
    mock_fetch_commits.assert_called_once_with("BRRRR_Experimental", "local_sha_123")


@patch("Ankimon.changelog.QueryOp")
@patch("Ankimon.pyobj.update_manager.read_update_state")
def test_check_branch_update_skipped(mock_read_state, mock_query_op):
    """Test check_branch_update does nothing if skip_until is in the future."""
    import time
    mock_read_state.return_value = {
        "source_type": "branch",
        "source_name": "BRRRR_Experimental",
        "commit_sha": "abc1234",
        "skip_until": time.time() + 3600  # 1 hour in the future
    }
    changelog.check_branch_update(True, True)
    mock_query_op.assert_not_called()

