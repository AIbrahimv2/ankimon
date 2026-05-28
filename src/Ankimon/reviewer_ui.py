from anki.hooks import wrap
from aqt.reviewer import Reviewer
from aqt.utils import downArrow, tooltip, tr
from aqt import mw

from .singletons import (
    enemy_pokemon,
    main_pokemon,
    ankimon_tracker_obj,
    get_test_window,
    get_evo_window,
    logger,
    achievements,
    trainer_card,
    reviewer_obj,
)
from .functions.encounter_functions import (
    catch_pokemon,
    kill_pokemon,
    new_pokemon,
)
from .texts import _bottomHTML_template, button_style
from .utils import is_dev_mode

_collected_pokemon_ids = set()

# === TEAM CYCLING STATE ===
_team_cycle_index = 0
_team_cycle_pokemon_ids = []  # Cache of first 3 team member IDs

def get_team_pokemon_list():
    """Load first 3 team member IDs from database"""
    global _team_cycle_pokemon_ids
    try:
        
        # Get team from database
        db = mw.ankimon_db
        team_data = db.get_team()  # Returns list of dicts with 'individual_id'
        
        # Extract first 3 individual_ids
        _team_cycle_pokemon_ids = [
            entry.get("individual_id")
            for entry in team_data[:3]  # First 3 only
            if entry.get("individual_id")
        ]
        
        return _team_cycle_pokemon_ids
    except Exception as e:
        print(f"Error loading team pokemon from database: {e}")
        return []

def get_pokemon_from_collection(individual_id):
    """Load full pokemon data from database by individual_id"""
    try:
        
        db = mw.ankimon_db
        pokemon_data = db.get_pokemon(individual_id)  # Changed from get_pokemon_by_individual_id
        return pokemon_data
    except Exception as e:
        print(f"Error loading pokemon {individual_id} from database: {e}")
        return None

#_last_cycle_time = 0

def cycle_team_pokemon():

    # GUARD: Prevent spamming the cycle function 
    #If needed
    #global _last_cycle_time
    #import time
    #now = time.time()
    #if now - _last_cycle_time < 0.15:  # Prevent spam within 150ms
    #    return
    # _last_cycle_time = now

    """Main callback: cycle active pokemon to next team slot"""
    global _team_cycle_index, _team_cycle_pokemon_ids
    
    try:
        from .functions.update_main_pokemon import save_main_pokemon
        
        team_ids = get_team_pokemon_list()
        if not team_ids or len(team_ids) < 2:
            tooltip("Not enough team members to cycle (need at least 2)")
            return
        
        # Bounds check for safety
        if _team_cycle_index >= len(team_ids):
            _team_cycle_index = 0
        
        _team_cycle_index = (_team_cycle_index + 1) % len(team_ids)
        next_id = team_ids[_team_cycle_index]
        
        pokemon_data = get_pokemon_from_collection(next_id)
        if not pokemon_data or not pokemon_data.get("id"):
            tooltip("Invalid pokemon data")
            return
        
        try:
            # Update main_pokemon with new data
            from .functions.pokedex_functions import search_pokedex_by_id, search_pokedex
            pokemon_name = pokemon_data.get("name")
            if not pokemon_name:
                pokemon_name = search_pokedex_by_id(pokemon_data.get("id", 1))
                pokemon_data["name"] = pokemon_name
            
            pokemon_data["base_stats"] = search_pokedex(pokemon_name, "baseStats")
            
            main_pokemon.update_stats(**pokemon_data)
            main_pokemon.max_hp = main_pokemon.calculate_max_hp()
            main_pokemon.hp = main_pokemon.max_hp
            main_pokemon.reset_bonuses()
            
            save_main_pokemon(main_pokemon)
        except Exception as e:
            print(f"Error updating pokemon: {e}")
            tooltip(f"Error switching pokemon: {e}")
            return
        
        try:
            # Update HUD immediately by getting current reviewer and forcing refresh
            reviewer = mw.reviewer
            if reviewer and reviewer.web:
                # Call update_life_bar with the actual reviewer instance
                reviewer_obj.update_life_bar(reviewer, 0, 0)
        except Exception as e:
            print(f"Error updating HUD: {e}")
        
        # Show tooltip
        pkmn_name = pokemon_data.get("nickname") or pokemon_data.get("name", "Unknown")
        pkmn_level = pokemon_data.get("level", "?")
        print(f"Switched to {pkmn_name} LVL {pkmn_level}")
        tooltip(f"Switched to {pkmn_name}! LVL: {pkmn_level}")
        
    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        tooltip(f"Error: {str(e)}")

def set_collected_ids(ids):
    global _collected_pokemon_ids
    _collected_pokemon_ids = ids


def catch_shortcut_function():
    if not getattr(mw, "ankimon_startup_finished", False):
        tooltip("Ankimon is still loading, please wait...")
        return
    if enemy_pokemon.hp < 1:
        catch_pokemon(
            enemy_pokemon,
            ankimon_tracker_obj,
            logger,
            "",
            _collected_pokemon_ids,
            achievements,
        )
        new_pokemon(enemy_pokemon, get_test_window(), ankimon_tracker_obj, reviewer_obj, update_hud=True)
    else:
        tooltip("You only catch a pokemon once it's fainted!")


def defeat_shortcut_function():
    if not getattr(mw, "ankimon_startup_finished", False):
        tooltip("Ankimon is still loading, please wait...")
        return
    if enemy_pokemon.hp < 1:
        kill_pokemon(
            main_pokemon, enemy_pokemon, get_evo_window(), logger, achievements, trainer_card
        )
        new_pokemon(enemy_pokemon, get_test_window(), ankimon_tracker_obj, reviewer_obj, update_hud=True)
    else:
        tooltip("Wild pokemon has to be fainted to defeat it!")

# Module-level storage for dynamic key reading
_current_keys = {
    "catch": "6",
    "defeat": "5", 
    "team_cycle": "9"
}
_original_shortcutkeys_wrapped = False
_ui_hooks_installed = False

def setup_reviewer_ui(catch_shortcut: str, defeat_shortcut: str, reviewer_buttons: bool, team_cycle_shortcut: str = "9"):
    """Setup hotkeys and UI elements for reviewer"""
    global _current_keys, _original_shortcutkeys_wrapped, _ui_hooks_installed
    
    # Update the dict (this persists across calls)
    _current_keys["catch"] = str(catch_shortcut).lower()
    _current_keys["defeat"] = str(defeat_shortcut).lower()
    _current_keys["team_cycle"] = str(team_cycle_shortcut).lower()
    
    # Only wrap once; the wrapper reads _current_keys dynamically
    if not _original_shortcutkeys_wrapped:
        # Store original if not already stored
        if not hasattr(Reviewer, "_ankimon_orig_shortcutKeys"):
            Reviewer._ankimon_orig_shortcutKeys = Reviewer._shortcutKeys

        def _shortcutKeys_wrap(self, _old):
            original = _old(self)
            # These lambdas read from _current_keys dict at CALL time, not definition time
            original.append((_current_keys["catch"], lambda: catch_shortcut_function()))
            original.append((_current_keys["defeat"], lambda: defeat_shortcut_function()))
            original.append((_current_keys["team_cycle"], lambda: team_cycle_shortcut_function()))
            if is_dev_mode():
                original.append(("0", lambda: test_encounter_shortcut_function()))
            return original

        Reviewer._shortcutKeys = wrap(Reviewer._shortcutKeys, _shortcutKeys_wrap, "around")
        _original_shortcutkeys_wrapped = True

    if reviewer_buttons is True and not _ui_hooks_installed:
        def _linkHandler_wrap(self, url, _old):
            if url == "catch":
                catch_shortcut_function()
                return True
            elif url == "defeat":
                defeat_shortcut_function()
                return True
            elif url == "team_cycle":
                team_cycle_shortcut_function()
                return True
            else:
                return _old(self, url)

        def _bottomHTML_wrap(self, _old):
            if not getattr(mw, "ankimon_startup_finished", False):
                return _old(self)
            return _bottomHTML_template % dict(
                edit=tr.studying_edit(),
                editkey=tr.actions_shortcut_key(val="E"),
                more=tr.studying_more(),
                morekey=tr.actions_shortcut_key(val="M"),
                downArrow=downArrow(),
                time=self.card.time_taken() // 1000,
                CatchKey=tr.actions_shortcut_key(val=f"{_current_keys['catch']}"),
                DefeatKey=tr.actions_shortcut_key(val=f"{_current_keys['defeat']}"),
                TeamCycleKey=tr.actions_shortcut_key(val=f"{_current_keys['team_cycle']}"),
            )

        # Store originals if not already stored
        if not hasattr(Reviewer, "_ankimon_orig_linkHandler"):
            Reviewer._ankimon_orig_linkHandler = Reviewer._linkHandler
        if not hasattr(Reviewer, "_ankimon_orig_bottomHTML"):
            Reviewer._ankimon_orig_bottomHTML = Reviewer._bottomHTML

        Reviewer._linkHandler = wrap(Reviewer._linkHandler, _linkHandler_wrap, "around")
        Reviewer._bottomHTML = wrap(Reviewer._bottomHTML, _bottomHTML_wrap, "around")
        _ui_hooks_installed = True

def team_cycle_shortcut_function():
    """Callback for team cycle hotkey"""
    if not getattr(mw, "ankimon_startup_finished", False):
        tooltip("Ankimon is still loading, please wait...")
        return
    cycle_team_pokemon()

def test_encounter_shortcut_function():
    """Testing hotkey: trigger a new pokemon encounter immediately"""
    if is_dev_mode():
        new_pokemon(enemy_pokemon, get_test_window(), ankimon_tracker_obj, reviewer_obj, update_hud=True)
        tooltip("New encounter triggered (Test Hotkey 0)")
