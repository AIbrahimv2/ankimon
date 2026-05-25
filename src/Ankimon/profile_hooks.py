from anki.hooks import addHook
from aqt import gui_hooks, mw

from .singletons import settings_obj, logger
from .pyobj.ankimon_sync import setup_ankimon_sync_hooks, check_and_sync_pokemon_data
from .pyobj.tip_of_the_day import show_tip_of_the_day
from .pyobj.pokemon_trade import check_and_award_monthly_pokemon
from .pyobj.error_handler import show_warning_with_traceback
from .functions.pokedex_functions import clear_pokedex_caches
from .functions.learnset_retrieval import clear_learnset_cache
from .functions.encounter_functions import clear_encounter_cache

sync_dialog = None


def _on_profile_did_open(online_connectivity=None):
    def handler():
        try:
            show_tip_of_the_day()
        except Exception as e:
            show_warning_with_traceback(
                parent=mw, exception=e, message="Error showing tip of the day:"
            )

        from aqt.operations import QueryOp
        from .utils import test_online_connectivity

        def run_conn_check():
            try:
                return test_online_connectivity()
            except Exception:
                return False

        def on_conn_done(connected: bool):
            mw.online_connectivity = connected
            
            if connected:
                try:
                    check_and_award_monthly_pokemon(logger)
                except Exception as e:
                    show_warning_with_traceback(
                        parent=mw, exception=e, message="Error awarding monthly pokemon:"
                    )
                
                # Check branch updates and changelogs safely now that UI is running
                try:
                    no_more_news = settings_obj.get("misc.YouShallNotPass_Ankimon_News")
                    ssh = settings_obj.get("misc.ssh")
                    from .changelog import check_and_show_changelog, check_branch_update
                    check_and_show_changelog(connected, ssh, no_more_news)
                    check_branch_update(connected, ssh)
                except Exception as e:
                    print(f"Error checking branch updates: {e}")
            else:
                logger.log(
                    "info",
                    "Skipping monthly pokemon check due to no internet connectivity.",
                )

            try:
                ankiweb_sync = settings_obj.get("misc.ankiweb_sync")
                if not ankiweb_sync:
                    logger.log(
                        "info",
                        "AnkiWeb sync is disabled in settings - skipping sync system initialization",
                    )
                    return

                setup_ankimon_sync_hooks(settings_obj, logger)

                if not connected:
                    logger.log(
                        "info", "No connection - AnkiWeb sync is disabled for this session"
                    )
                else:
                    global sync_dialog
                    sync_dialog = check_and_sync_pokemon_data(settings_obj, logger)
                    logger.log("info", "Ankimon sync system initialized successfully")
            except Exception as e:
                show_warning_with_traceback(
                    parent=mw, exception=e, message="Error setting up sync system:"
                )

        QueryOp(
            parent=mw,
            op=lambda _: run_conn_check(),
            success=on_conn_done
        ).without_collection().run_in_background()

    return handler

def _on_profile_close():
    """Clear all performance caches when Anki session ends"""
    try:
        clear_pokedex_caches()
        clear_learnset_cache()
        clear_encounter_cache()
    except Exception as e:
        print(f"Error clearing caches on profile close: {e}")

def register_profile_hooks(
    online_connectivity,
    backup_manager,
    CatchPokemonHook,
    DefeatPokemonHook,
    add_catch_pokemon_hook,
    add_defeat_pokemon_hook,
    collected_pokemon_ids,
):
    def on_profile_loaded():
        mw.defeatpokemon = DefeatPokemonHook
        mw.catchpokemon = lambda: CatchPokemonHook(collected_pokemon_ids)
        mw.add_catch_pokemon_hook = add_catch_pokemon_hook
        mw.add_defeat_pokemon_hook = add_defeat_pokemon_hook

    addHook("profileLoaded", on_profile_loaded)
    gui_hooks.profile_did_open.append(_on_profile_did_open(online_connectivity))
    gui_hooks.profile_will_close.append(backup_manager.on_anki_close)
    gui_hooks.profile_will_close.append(_on_profile_close)
