from typing import Union

from aqt import mw
from aqt.operations import QueryOp
from aqt.utils import showWarning
import markdown

from .resources import addon_ver, addon_dir
from .utils import read_github_file, read_local_file, compare_files, write_local_file
from .gui_entities import UpdateNotificationWindow
from .pyobj.error_handler import show_warning_with_traceback
from .pyobj.help_window import HelpWindow

update_infos_md = addon_dir / "updateinfos.md"


def download_changelog():
    try:
        github_url = f"https://raw.githubusercontent.com/h0tp-ftw/ankimon/refs/heads/main/assets/changelogs/{addon_ver}.md"
        github_content = read_github_file(github_url)
        if github_content is None:
            github_url = "https://raw.githubusercontent.com/h0tp-ftw/ankimon/refs/heads/main/assets/changelogs/unknown.md"
            github_content = read_github_file(github_url)
        return github_content
    except Exception as e:
        return e


def check_and_show_changelog(online_connectivity: bool, ssh: bool, no_more_news: bool):
    if not (online_connectivity and ssh):
        return

    def done(result: Union[Exception, str, None]):
        if isinstance(result, Exception):
            show_warning_with_traceback(
                parent=mw, exception=result, message="Error connecting to GitHub:"
            )
            return
        if result is None:
            showWarning("Failed to retrieve Ankimon content from GitHub.")
            return
        local_content = read_local_file(update_infos_md)
        if not compare_files(local_content, result):
            write_local_file(update_infos_md, result)
            dialog = UpdateNotificationWindow(markdown.markdown(result))
            if not no_more_news:
                dialog.exec()

    QueryOp(
        parent=mw,
        op=lambda _col: download_changelog(),
        success=done,
    ).without_collection().run_in_background()


def open_help_window(online_connectivity):
    try:
        help_dialog = HelpWindow(online_connectivity)
        help_dialog.exec()
    except Exception as e:
        show_warning_with_traceback(
            parent=mw, exception=e, message="Error in opening Help Guide:"
        )


def check_branch_update(online_connectivity: bool, ssh: bool):
    from .singletons import logger
    logger.log("info", f"check_branch_update triggered: online_connectivity={online_connectivity}, ssh={ssh}")
    if not ssh:
        logger.log("info", "check_branch_update exited early: ssh is False")
        return

    from .pyobj.update_manager import read_update_state

    state = read_update_state()
    logger.log("info", f"check_branch_update: read_update_state={state}")
    if not state:
        logger.log("info", "check_branch_update exited early: state is None")
        return

    import time
    skip_until = state.get("skip_until")
    logger.log("info", f"check_branch_update: skip_until={skip_until}, current_time={time.time()}")
    if skip_until and time.time() < skip_until:
        logger.log("info", "check_branch_update exited early: skip_until active")
        return

    source_type = state.get("source_type")
    source_name = state.get("source_name")
    local_sha = state.get("commit_sha")
    logger.log("info", f"check_branch_update: source_type={source_type}, source_name={source_name}, local_sha={local_sha}")

    if source_type != "branch" or source_name != "BRRRR_Experimental":
        logger.log("info", "check_branch_update exited early: source_type/name mismatch")
        return

    def bg(_col):
        try:
            from .pyobj.update_manager import fetch_branch_sha, fetch_branch_commits
            remote_sha = fetch_branch_sha("BRRRR_Experimental")
            commits = []
            if remote_sha and local_sha != remote_sha:
                commits = fetch_branch_commits("BRRRR_Experimental", local_sha)
            return remote_sha, commits
        except Exception as e:
            return e

    def done(result):
        if isinstance(result, Exception) or not result:
            return

        remote_sha, commits = result
        if not remote_sha:
            return

        if local_sha != remote_sha:
            from .pyobj.update_dialog import show_branch_update_prompt
            show_branch_update_prompt("BRRRR_Experimental", remote_sha, commits)

    QueryOp(
        parent=mw,
        op=bg,
        success=done,
    ).without_collection().run_in_background()
