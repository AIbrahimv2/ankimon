# -*- coding: utf-8 -*-

# Ankimon
# Copyright (C) 2024 Unlucky-Life

# This program is free software: you can redistribute it and/or modify
# by the Free Software Foundation
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# Important - If you redistribute it and/or modify this addon - must give contribution in Title and Code
# aswell as ask for permission to modify / redistribute this addon or the code itself

try:
    from .debug_console import show_ankimon_dev_console
except ModuleNotFoundError:
    pass

import aqt
from aqt import gui_hooks, mw
from aqt.gui_hooks import webview_will_set_content
from aqt.webview import WebContent

from .resources import ensure_ankimon_infrastructure, user_path, addon_dir
ensure_ankimon_infrastructure(addon_dir, user_path)

from .singletons import (
    settings_obj,
    logger,
    translator,
    reviewer_obj,
    ankimon_tracker_obj,
    shop_manager,
    trainer_card,
)
from .functions.url_functions import (
    open_team_builder,
    rate_addon_url,
    report_bug,
    join_discord_url,
    open_leaderboard_url,
)
from .functions.pokemon_showdown_functions import (
    export_to_pkmn_showdown,
    export_all_pkmn_showdown,
    flex_pokemon_collection,
)
from .utils import test_online_connectivity
from .menu_buttons import create_menu_actions
from .hooks import setupHooks
from .pyobj.error_handler import show_warning_with_traceback

# --- Register singletons on mw for global access ---
mw.settings_ankimon = None
mw.logger = logger
mw.translator = translator
mw.settings_obj = settings_obj

from .gui_classes import overview_team

# --- Startup: asynchronous & thread-safe ---
mw.ankimon_startup_finished = False

# Import hooks early at module level
from .hook_registry import (
    CatchPokemonHook,
    DefeatPokemonHook,
    add_catch_pokemon_hook,
    add_defeat_pokemon_hook,
)

def start_asynchronous_startup():
    from aqt.operations import QueryOp
    from .startup import run_startup_background_checks, run_startup_ui_callbacks

    def on_startup_complete(results):
        # 1. Run UI callbacks (migration dialog, sprite downloader, first enemy update, starter window, rate prompt)
        database_complete = run_startup_ui_callbacks(results)
        collected_pokemon_ids = results["collected_pokemon_ids"]

        # 2. Update battle loop state
        from .battle_loop import init_battle_state
        init_battle_state(collected_pokemon_ids)

        # 3. Update reviewer ids
        from .reviewer_ui import set_collected_ids
        set_collected_ids(collected_pokemon_ids)

        # 4. Create BackupManager
        from .pyobj.backup_manager import BackupManager
        backup_manager = BackupManager(logger, settings_obj)

        # 5. Create Menu Actions
        create_menu_actions(
            database_complete,
            online_connectivity,
            None, # item_window
            None, # test_window
            None, # achievement_bag
            open_team_builder,
            export_to_pkmn_showdown,
            export_all_pkmn_showdown,
            flex_pokemon_collection,
            None, # eff_chart
            None, # gen_id_chart
            None, # nature_chart
            None, # credits
            None, # license
            open_help_window,
            report_bug,
            rate_addon_url,
            None, # version_dialog
            trainer_card,
            None, # ankimon_tracker_window
            logger,
            None, # settings_window
            shop_manager,
            settings_obj.get("controls.key_for_opening_closing_ankimon"),
            join_discord_url,
            open_leaderboard_url,
            settings_obj,
            addon_dir,
            None, # pokemon_pc
            backup_manager,
        )

        # 6. Register Profile Hooks
        from .profile_hooks import register_profile_hooks
        register_profile_hooks(
            online_connectivity,
            backup_manager,
            CatchPokemonHook,
            DefeatPokemonHook,
            add_catch_pokemon_hook,
            add_defeat_pokemon_hook,
            collected_pokemon_ids,
        )

        # 7. Update collected IDs in HUD and register reviewer ui shortcuts
        from .reviewer_ui import setup_reviewer_ui
        setup_reviewer_ui(
            settings_obj.get("controls.catch_key"),
            settings_obj.get("controls.defeat_key"),
            settings_obj.get("controls.pokemon_buttons"),
            settings_obj.get("controls.team_cycle_key", "9"),
        )

        # 8. Set startup finished flag
        mw.ankimon_startup_finished = True

        # 9. Force redraw of the reviewer bottom bar if active
        if getattr(mw, "state", None) == "review" and getattr(mw, "reviewer", None):
            try:
                mw.reviewer.bottom.draw()
            except Exception:
                pass

    QueryOp(
        parent=mw,
        op=lambda _col: run_startup_background_checks(),
        success=on_startup_complete,
    ).without_collection().run_in_background()

# --- Web exports for reviewer UI ---
mw.addonManager.setWebExports(
    __name__, r"(web|user_files)/.*\.(css|js|jpg|gif|html|ttf|png|mp3)"
)

def on_webview_will_set_content(web_content: WebContent, context) -> None:
    if not isinstance(context, aqt.reviewer.Reviewer):
        return
    ankimon_package = mw.addonManager.addonFromModule(__name__)
    web_content.js.append(
        f"/_addons/{ankimon_package}/web/ankimon_hud_portal.js"
    )

webview_will_set_content.append(on_webview_will_set_content)

# --- Card timer and answer hooks ---
from .card_hooks import register_card_hooks
register_card_hooks()

setupHooks(None, ankimon_tracker_obj)

# --- Changelog & Update checks (Asynchronous) ---
online_connectivity = False
mw.online_connectivity = False
from .changelog import open_help_window

# --- Battle loop proxy ---
def _ankimon_review_proxy(*args, **kwargs):
    """Persistent proxy that always calls the current battle loop."""
    from .battle_loop import on_review_card
    return on_review_card(*args, **kwargs)

# Register the proxy only once on mw to prevent duplicates across reloads
if not hasattr(mw, "_ankimon_review_proxy"):
    mw._ankimon_review_proxy = _ankimon_review_proxy
    gui_hooks.reviewer_did_answer_card.append(mw._ankimon_review_proxy)

# --- Discord Integration ---
from .discord_integration import setup_discord_hooks
setup_discord_hooks()

# Start background loading process
start_asynchronous_startup()

