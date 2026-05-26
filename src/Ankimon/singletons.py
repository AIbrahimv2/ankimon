"""
singletons.py

This module groups up some of the global variables that originally wer ein the __init__.py.
This module, hopefully, does not have vocation to remain permanently. This is but a transition step
in the splitting of the __init__.py file.

Author: Axil
Created: 2025-06-03 (YYY-MM-DD)
"""

import json
import uuid

from aqt import mw

from .pyobj.ankimon_tracker import AnkimonTracker
from .pyobj.settings import Settings
from .pyobj.pokemon_obj import PokemonObject
from .pyobj.InfoLogger import ShowInfoLogger
from .pyobj.trainer_card import TrainerCard
from .pyobj.translator import Translator
from .pyobj.ankimon_shop import PokemonShopManager
from .pyobj.reviewer_obj import Reviewer_Manager
from .pyobj.database_manager import get_db
from .functions.update_main_pokemon import update_main_pokemon
from .functions.badges_functions import populate_achievements_from_badges
from .resources import addon_dir
from .utils import is_alive

# --- RELOAD-SAFE SINGLETONS ---
# We anchor these to 'mw' so they persist across add-on reloads.

# logger
logger = getattr(mw, "logger", None) or ShowInfoLogger()
mw.logger = logger

# Initialize the database
ankimon_db = getattr(mw, "ankimon_db", None) or get_db(logger)
mw.ankimon_db = ankimon_db

# Create the Settings object
settings_obj = getattr(mw, "settings_obj", None) or Settings()
mw.settings_obj = settings_obj

settings_window = None
def get_settings_window():
    global settings_window
    if not is_alive(settings_window):
        settings_window = getattr(mw, "settings_ankimon", None)
        if not is_alive(settings_window):
            from .pyobj.settings_window import SettingsWindow
            settings_window = SettingsWindow(
                config=settings_obj.config,
                set_config_callback=settings_obj.set,
                save_config_callback=settings_obj.save_config,
                load_config_callback=settings_obj.load_config,
            )
            mw.settings_ankimon = settings_window
    return settings_window

# Init Translator
translator = getattr(mw, "translator", None) or Translator(language=int(settings_obj.get("misc.language")))
mw.translator = translator

# Main Pokemon
main_pokemon = getattr(mw, "main_pokemon", None)
if main_pokemon is None:
    main_pokemon, _ = update_main_pokemon()
    mw.main_pokemon = main_pokemon

# Enemy Pokemon
enemy_pokemon = getattr(mw, "enemy_pokemon", None)
if enemy_pokemon is None:
    enemy_pokemon = PokemonObject(
        name="Rattata", shiny=False, id=19, level=5, ability="Run Away", type=["Normal"],
        stats={"hp": 39, "atk": 52, "def": 43, "spa": 60, "spd": 50, "spe": 65, "xp": 101},
        attacks=["Quick Attack", "Tackle", "Tail Whip"], base_experience=58, growth_rate="medium-slow",
        hp=30, ev={"hp": 3, "atk": 5, "def": 4, "spa": 1, "spd": 2, "spe": 3},
        iv={"hp": 27, "atk": 24, "def": 3, "spa": 24, "spd": 16, "spe": 21}, gender="M",
        battle_status="Fighting", xp=0, position=(5, 5), tier="Normal",
        captured_date=None, individual_id=str(uuid.uuid4()),
    )
    mw.enemy_pokemon = enemy_pokemon

# Trainer Card
trainer_card = getattr(mw, "trainer_card", None)
if trainer_card is None:
    trainer_card = TrainerCard(
        logger, main_pokemon, settings_obj,
        trainer_name=settings_obj.get("trainer.name"),
        trainer_id="".join(filter(str.isdigit, str(uuid.uuid4()).replace("-", ""))),
        team="Pikachu (Level 25), Charizard (Level 50), Bulbasaur (Level 15)",
        league="Unranked",
    )
    mw.trainer_card = trainer_card

# --- LAZY WINDOWS & DIALOGS ---
starter_window = None
def get_starter_window():
    global starter_window
    if not is_alive(starter_window):
        starter_window = getattr(mw, "starter_window", None)
        if not is_alive(starter_window):
            from .pyobj.starter_window import StarterWindow
            starter_window = StarterWindow(logger, settings_obj)
            mw.starter_window = starter_window
    return starter_window

# Ankimon Tracker
ankimon_tracker_obj = getattr(mw, "ankimon_tracker_obj", None)
if ankimon_tracker_obj is None:
    ankimon_tracker_obj = AnkimonTracker(trainer_card=trainer_card)
    mw.ankimon_tracker_obj = ankimon_tracker_obj
    ankimon_tracker_obj.set_main_pokemon(main_pokemon)
    ankimon_tracker_obj.set_enemy_pokemon(enemy_pokemon)

# Test Window
test_window = None
def get_test_window():
    global test_window
    if not is_alive(test_window):
        test_window = getattr(mw, "test_window", None)
        if not is_alive(test_window):
            from .pyobj.test_window import TestWindow
            test_window = TestWindow(
                main_pokemon=main_pokemon, enemy_pokemon=enemy_pokemon,
                settings_obj=settings_obj, ankimon_tracker_obj=ankimon_tracker_obj,
                translator=translator, parent=mw, logger=logger,
            )
            mw.test_window = test_window
    return test_window

# Shop Manager
shop_manager = getattr(mw, "shop_manager", None) or PokemonShopManager(
    logger=logger, settings_obj=settings_obj,
    set_callback=settings_obj.set, get_callback=settings_obj.get,
)
mw.shop_manager = shop_manager

# Reviewer Manager
reviewer_obj = getattr(mw, "reviewer_obj", None) or Reviewer_Manager(
    settings_obj=settings_obj, main_pokemon=main_pokemon,
    enemy_pokemon=enemy_pokemon, ankimon_tracker=ankimon_tracker_obj,
)
mw.reviewer_obj = reviewer_obj

# Achievements
achievements = getattr(mw, "achievements_dict", None)
if achievements is None:
    achievements = populate_achievements_from_badges({str(i): False for i in range(1, 69)})
    mw.achievements_dict = achievements

# Windows & Bags
achievement_bag = None
def get_achievement_bag():
    global achievement_bag
    if not is_alive(achievement_bag):
        achievement_bag = getattr(mw, "achievement_bag", None)
        if not is_alive(achievement_bag):
            from .pyobj.achievement_window import AchievementWindow
            achievement_bag = AchievementWindow()
            mw.achievement_bag = achievement_bag
    return achievement_bag

ankimon_tracker_window = None
def get_ankimon_tracker_window():
    global ankimon_tracker_window
    if not is_alive(ankimon_tracker_window):
        ankimon_tracker_window = getattr(mw, "ankimon_tracker_window", None)
        if not is_alive(ankimon_tracker_window):
            from .pyobj.ankimon_tracker_window import AnkimonTrackerWindow
            ankimon_tracker_window = AnkimonTrackerWindow(tracker=ankimon_tracker_obj)
            mw.ankimon_tracker_window = ankimon_tracker_window
    return ankimon_tracker_window

# Ankidex
ankidex_window = getattr(mw, "ankidex_window", None)
def get_ankidex_window():
    global ankidex_window
    if not is_alive(ankidex_window):
        from .ankidex.ankidex_obj import Ankidex
        ankidex_window = Ankidex(addon_dir, ankimon_tracker=ankimon_tracker_obj)
        mw.ankidex_window = ankidex_window
    return ankidex_window

# Unified Ankimon shell window (Items + Ankidex in one web view)
items_web_window = getattr(mw, "items_web_window", None)
def get_items_window():
    global items_web_window
    if not is_alive(items_web_window):
        from .ankimon_items_web.shop_obj import AnkimonItemsWeb
        items_web_window = AnkimonItemsWeb(
            addon_dir,
            shop_manager=shop_manager,
            item_window=get_item_window(),
            ankimon_tracker=ankimon_tracker_obj,
        )
        mw.items_web_window = items_web_window
    return items_web_window

evo_window = None
def get_evo_window():
    global evo_window
    if not is_alive(evo_window):
        evo_window = getattr(mw, "evo_window", None)
        if not is_alive(evo_window):
            from .pyobj.evolution_window import EvoWindow
            evo_window = EvoWindow(
                logger, settings_obj, main_pokemon, translator, reviewer_obj, get_test_window(), achievements,
            )
            mw.evo_window = evo_window
    return evo_window

item_window = None
def get_item_window():
    global item_window
    if not is_alive(item_window):
        item_window = getattr(mw, "item_window", None)
        if not is_alive(item_window):
            from .pyobj.item_window import ItemWindow
            item_window = ItemWindow(
                logger=logger, settings_obj=settings_obj, main_pokemon=main_pokemon,
                enemy_pokemon=enemy_pokemon, achievements=achievements,
                starter_window=get_starter_window(),
                evo_window=get_evo_window(),
            )
            mw.item_window = item_window
    return item_window

# Pokemon PC
pokemon_pc = getattr(mw, "pokemon_pc", None)
def get_pokemon_pc():
    global pokemon_pc
    if not is_alive(pokemon_pc):
        pokemon_pc = getattr(mw, "pokemon_pc", None)
        if not is_alive(pokemon_pc):
            from .pyobj.pc_box import PokemonPC
            pokemon_pc = PokemonPC(
                logger=logger, translator=translator, reviewer_obj=reviewer_obj,
                test_window=get_test_window(), settings=settings_obj, main_pokemon=main_pokemon,
                achievements=achievements,
            )
            mw.pokemon_pc = pokemon_pc
    return pokemon_pc

# UI Utilities
eff_chart = None
def get_eff_chart():
    global eff_chart
    if not is_alive(eff_chart):
        from .gui_entities import TableWidget
        eff_chart = TableWidget()
    return eff_chart

gen_id_chart = None
def get_gen_id_chart():
    global gen_id_chart
    if not is_alive(gen_id_chart):
        from .gui_entities import IDTableWidget
        gen_id_chart = IDTableWidget()
    return gen_id_chart

nature_chart = None
def get_nature_chart():
    global nature_chart
    if not is_alive(nature_chart):
        from .gui_entities import NatureTableWidget
        nature_chart = NatureTableWidget()
    return nature_chart

license = None
def get_license():
    global license
    if not is_alive(license):
        from .gui_entities import License
        license = License()
    return license

credits = None
def get_credits():
    global credits
    if not is_alive(credits):
        from .gui_entities import Credits
        credits = Credits()
    return credits

version_dialog = None
def get_version_dialog():
    global version_dialog
    if not is_alive(version_dialog):
        from .gui_entities import Version_Dialog
        version_dialog = Version_Dialog()
    return version_dialog


def __getattr__(name):
    if name == "settings_window":
        return get_settings_window()
    elif name == "starter_window":
        return get_starter_window()
    elif name == "test_window":
        return get_test_window()
    elif name == "achievement_bag":
        return get_achievement_bag()
    elif name == "ankimon_tracker_window":
        return get_ankimon_tracker_window()
    elif name == "evo_window":
        return get_evo_window()
    elif name == "item_window":
        return get_item_window()
    elif name == "eff_chart":
        return get_eff_chart()
    elif name == "gen_id_chart":
        return get_gen_id_chart()
    elif name == "nature_chart":
        return get_nature_chart()
    elif name == "license":
        return get_license()
    elif name == "credits":
        return get_credits()
    elif name == "version_dialog":
        return get_version_dialog()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def swap_ankimon_account():
    """Toggles between ankimon.db and ankimonDEV.db and refreshes the game state."""
    from aqt.utils import tooltip
    from .functions.update_main_pokemon import update_main_pokemon
    from .functions.encounter_functions import new_pokemon, clear_encounter_cache

    current_name = mw.ankimon_db.db_path.name
    new_name = "ankimonDEV.db" if current_name == "ankimon.db" else "ankimon.db"

    try:
        # Switch DB connection
        mw.ankimon_db.switch_database(new_name)

        # Reload configuration (in-place)
        mw.settings_obj.load_config()

        # Update main pokemon in-place
        update_main_pokemon(mw.main_pokemon)

        # Refresh trainer card data
        mw.trainer_card.refresh()

        # Reset battle and capture state so no stale data can bleed through
        mw.ankimon_tracker_obj.caught = 0
        mw.ankimon_tracker_obj.general_card_count_for_battle = 0
        
        # Sync collected IDs to current account
        from .reviewer_ui import set_collected_ids
        from .battle_loop import init_battle_state
        new_ids = mw.ankimon_db.get_all_pokemon_ids()
        set_collected_ids(new_ids)
        init_battle_state(new_ids)

        # Clear encounter percentages cache (uses new trainer level/stats)
        clear_encounter_cache()

        # Generate a fresh encounter for the new account
        new_pokemon(mw.enemy_pokemon, getattr(mw, "test_window", None), mw.ankimon_tracker_obj, mw.reviewer_obj)

        # Refresh windows if they are open
        if hasattr(mw, "pokemon_pc") and is_alive(mw.pokemon_pc):
            # Reset selection because IDs change between databases
            mw.pokemon_pc._selected_individual_id = None
            mw.pokemon_pc.pokemon_details_layout = None
            mw.pokemon_pc.refresh_gui()
        
        if hasattr(mw, "item_window") and is_alive(mw.item_window):
            mw.item_window.renewWidgets()

        if hasattr(mw, "ankidex_window") and is_alive(mw.ankidex_window):
            mw.ankidex_window.update_ui_data()

        # If in reviewer, force HUD update
        if hasattr(mw, "reviewer") and mw.reviewer and hasattr(mw, "reviewer_obj"):
            mw.reviewer_obj.update_life_bar(mw.reviewer, None, 0)

        tooltip(f"Switched to {new_name}")
    except Exception as e:
        tooltip(f"Failed to switch account: {e}")
        import traceback
        traceback.print_exc()
