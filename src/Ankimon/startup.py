import json
import random

from aqt import mw

from .resources import (
    pkmnimgfolder,
    sound_list_path,
)
from .utils import (
    check_folders_exist,
    get_main_pokemon_data,
    load_collected_pokemon_ids,
    count_items_and_rewrite,
)
from .functions.encounter_functions import generate_random_pokemon
from .functions.badges_functions import get_achieved_badges
from .functions.rate_addon_functions import rate_this_addon
from .gui_entities import CheckFiles
from .pyobj.download_sprites import show_agreement_and_download_dialog
from .pyobj.backup_files import run_backup
from .pyobj.backup_manager import BackupManager
from .pyobj.error_handler import show_warning_with_traceback
from .singletons import (
    logger,
    translator,
    settings_obj,
    ankimon_tracker_obj,
    main_pokemon,
    enemy_pokemon,
    ankimon_db,
)


def run_startup_background_checks():
    # 1. Run backup
    backup_error = None
    try:
        run_backup()
    except Exception as e:
        backup_error = e

    # Instantiate BackupManager and run dev auto-backup
    try:
        backup_mgr = BackupManager(logger, settings_obj)
        if settings_obj.get("misc.developer_mode"):
            backup_mgr.create_backup(manual=False)
    except Exception as e:
        print(f"Error in background backup creation: {e}")

    # Check database migration status (read-only DB check)
    is_migrated = ankimon_db.is_migrated()

    # Load collected Pokémon IDs
    collected_pokemon_ids = load_collected_pokemon_ids()

    # 2. Config Migrations
    old_catch_special = settings_obj.get("battle.automatic_catch_special", None)
    if old_catch_special is not None:
        new_keys = [
            "battle.auto_catch_legendary",
            "battle.auto_catch_mythical",
            "battle.auto_catch_ultra",
            "battle.auto_catch_starter",
            "battle.auto_catch_mega",
            "battle.auto_catch_gmax",
            "battle.auto_catch_regional",
        ]
        for nk in new_keys:
            if nk not in settings_obj.config:
                settings_obj.set(nk, bool(old_catch_special))
        settings_obj.set("battle.automatic_catch_special", None)

    # Check assets (disk operations)
    database_complete = _check_assets_background()

    # If assets are complete, generate first enemy and check starter/badge conditions
    enemy_info = None
    needs_starter = False
    needs_rating = False

    if database_complete:
        enemy_info = _init_first_enemy_background()

        # Check if starter is needed
        if ankimon_db.get_pokemon_count() == 0:
            needs_starter = True

        # Check if rating prompt is needed
        badge_list = get_achieved_badges()
        if len(badge_list) > 1:
            db_rate_this = ankimon_db.get_user_data("rate_this")
            if db_rate_this is not True:
                needs_rating = True

    # Aggregating items count (DB operations, safe for background thread)
    try:
        count_items_and_rewrite()
    except Exception as e:
        print(f"Error in count_items_and_rewrite: {e}")

    return {
        "backup_error": backup_error,
        "is_migrated": is_migrated,
        "collected_pokemon_ids": collected_pokemon_ids,
        "database_complete": database_complete,
        "enemy_info": enemy_info,
        "needs_starter": needs_starter,
        "needs_rating": needs_rating,
    }


def run_startup_ui_callbacks(results):
    # Log and show start
    logger.log_and_showinfo("game", translator.translate("startup"))
    logger.log_and_showinfo("game", translator.translate("backing_up_files"))

    # Show backup error if any occurred
    if results.get("backup_error"):
        show_warning_with_traceback(
            parent=mw, exception=results["backup_error"], message="Backup error:"
        )

    # Database migration
    if not results["is_migrated"]:
        from .pyobj.migration_dialog import show_migration_dialog_if_needed
        from .resources import (
            mypokemon_path,
            mainpokemon_path,
            itembag_path,
            badgebag_path,
            team_pokemon_path,
            pokemon_history_path,
            user_path_credentials,
            rate_path,
        )

        show_migration_dialog_if_needed(
            ankimon_db,
            mypokemon_path,
            mainpokemon_path,
            itembag_path,
            badgebag_path,
            mw,
            team_pokemon_path,
            pokemon_history_path,
            user_path_credentials,
            rate_path,
        )

    # Assets download check
    if not results["database_complete"]:
        show_agreement_and_download_dialog(force_download=True)
        # Store as attribute on mw so it doesn't get garbage-collected
        mw.ankimon_file_checker = CheckFiles()
        mw.ankimon_file_checker.show()

    # Initializing first enemy stats on the main thread (thread-safety for GUI bindings/updates)
    if results["database_complete"] and results["enemy_info"]:
        (
            name,
            id,
            level,
            ability,
            type,
            base_stats,
            enemy_attacks,
            base_experience,
            growth_rate,
            ev,
            iv,
            gender,
            battle_status,
            battle_stats,
            tier,
            ev_yield,
            shiny,
            nature,
        ) = results["enemy_info"]

        enemy_pokemon.update_stats(
            name=name,
            id=id,
            level=level,
            ability=ability,
            type=type,
            base_stats=base_stats,
            attacks=enemy_attacks,
            base_experience=base_experience,
            growth_rate=growth_rate,
            ev=ev,
            iv=iv,
            gender=gender,
            nature=nature,
            battle_status=battle_status,
            battle_stats=battle_stats,
            tier=tier,
            ev_yield=ev_yield,
            shiny=shiny,
        )
        max_hp = enemy_pokemon.calculate_max_hp()
        enemy_pokemon.current_hp = max_hp
        enemy_pokemon.hp = max_hp
        enemy_pokemon.max_hp = max_hp
        ankimon_tracker_obj.randomize_battle_scene()

    # Check starter
    if results["database_complete"] and results["needs_starter"]:
        from .singletons import get_starter_window

        get_starter_window().display_starter_pokemon()

    # Rate dialog
    if results["database_complete"] and results["needs_rating"]:
        rate_this_addon()

    # Reset tracker counter
    ankimon_tracker_obj.pokemon_encounter = 0

    return results["database_complete"]


def _check_assets_background():
    back_sprites = check_folders_exist(pkmnimgfolder, "back_default")
    back_default_gif = check_folders_exist(pkmnimgfolder, "back_default_gif")
    front_sprites = check_folders_exist(pkmnimgfolder, "front_default")
    front_default_gif = check_folders_exist(pkmnimgfolder, "front_default_gif")
    item_sprites = check_folders_exist(pkmnimgfolder, "items")
    badges_sprites = check_folders_exist(pkmnimgfolder, "badges")

    return all(
        [
            back_sprites,
            front_sprites,
            front_default_gif,
            back_default_gif,
            item_sprites,
            badges_sprites,
        ]
    )


def _init_first_enemy_background():
    try:
        get_main_pokemon_data()
    except Exception:
        pass

    # Read from main_pokemon singleton (on main thread, it defaults to Dittos/DB-saved main)
    main_pokemon_level = main_pokemon.level if hasattr(main_pokemon, "level") else 5

    # Run generation
    try:
        enemy_data = generate_random_pokemon(main_pokemon_level, ankimon_tracker_obj)
        return enemy_data
    except Exception as e:
        print(f"Error in _init_first_enemy_background: {e}")
        return None
