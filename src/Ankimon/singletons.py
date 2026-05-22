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
from .pyobj.settings_window import SettingsWindow
from .pyobj.pokemon_obj import PokemonObject
from .pyobj.InfoLogger import ShowInfoLogger
from .pyobj.trainer_card import TrainerCard
from .pyobj.translator import Translator
from .pyobj.test_window import TestWindow
from .pyobj.achievement_window import AchievementWindow
from .pyobj.ankimon_tracker_window import AnkimonTrackerWindow
from .pyobj.ankimon_shop import PokemonShopManager
from .ankidex.ankidex_obj import Ankidex
from .pyobj.reviewer_obj import Reviewer_Manager
from .pyobj.evolution_window import EvoWindow
from .pyobj.starter_window import StarterWindow
from .pyobj.item_window import ItemWindow
from .pyobj.pc_box import PokemonPC
from .pyobj.database_manager import get_db
from .gui_entities import (
    License,
    Credits,
    TableWidget,
    IDTableWidget,
    NatureTableWidget,
    Version_Dialog,
)
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

# Pass the correct attributes to SettingsWindow
settings_window = getattr(mw, "settings_ankimon", None) or SettingsWindow(
    config=settings_obj.config,
    set_config_callback=settings_obj.set,
    save_config_callback=settings_obj.save_config,
    load_config_callback=settings_obj.load_config,
)
mw.settings_ankimon = settings_window

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

# Starter Window
starter_window = getattr(mw, "starter_window", None) or StarterWindow(logger, settings_obj)
mw.starter_window = starter_window

# Ankimon Tracker
ankimon_tracker_obj = getattr(mw, "ankimon_tracker_obj", None)
if ankimon_tracker_obj is None:
    ankimon_tracker_obj = AnkimonTracker(trainer_card=trainer_card)
    mw.ankimon_tracker_obj = ankimon_tracker_obj
    ankimon_tracker_obj.set_main_pokemon(main_pokemon)
    ankimon_tracker_obj.set_enemy_pokemon(enemy_pokemon)

# Test Window
test_window = getattr(mw, "test_window", None)
if test_window is None:
    test_window = TestWindow(
        main_pokemon=main_pokemon, enemy_pokemon=enemy_pokemon,
        settings_obj=settings_obj, ankimon_tracker_obj=ankimon_tracker_obj,
        translator=translator, parent=mw, logger=logger,
    )
    mw.test_window = test_window

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
achievements = populate_achievements_from_badges({str(i): False for i in range(1, 69)})

# Windows & Bags
# Achievements
achievements = getattr(mw, "achievements_dict", None)
if achievements is None:
    achievements = populate_achievements_from_badges({str(i): False for i in range(1, 69)})
    mw.achievements_dict = achievements

# Windows & Bags
achievement_bag = getattr(mw, "achievement_bag", None) or AchievementWindow()
mw.achievement_bag = achievement_bag

ankimon_tracker_window = getattr(mw, "ankimon_tracker_window", None) or AnkimonTrackerWindow(tracker=ankimon_tracker_obj)
mw.ankimon_tracker_window = ankimon_tracker_window

# Ankidex
ankidex_window = getattr(mw, "ankidex_window", None)
def get_ankidex_window():
    global ankidex_window
    if not is_alive(ankidex_window):
        ankidex_window = Ankidex(addon_dir, ankimon_tracker=ankimon_tracker_obj)
        mw.ankidex_window = ankidex_window
    return ankidex_window

# Initialize initially
get_ankidex_window()

evo_window = getattr(mw, "evo_window", None) or EvoWindow(
    logger, settings_obj, main_pokemon, translator, reviewer_obj, test_window, achievements,
)
mw.evo_window = evo_window

item_window = getattr(mw, "item_window", None) or ItemWindow(
    logger=logger, settings_obj=settings_obj, main_pokemon=main_pokemon,
    enemy_pokemon=enemy_pokemon, achievements=achievements,
    starter_window=starter_window,
    evo_window=evo_window,
)
mw.item_window = item_window

# Pokemon PC
pokemon_pc = getattr(mw, "pokemon_pc", None)
def get_pokemon_pc():
    global pokemon_pc
    if not is_alive(pokemon_pc):
        pokemon_pc = PokemonPC(
            logger=logger, translator=translator, reviewer_obj=reviewer_obj,
            test_window=test_window, settings=settings_obj, main_pokemon=main_pokemon,
        )
        mw.pokemon_pc = pokemon_pc
    return pokemon_pc

# Initialize initially
get_pokemon_pc()

# UI Utilities
eff_chart = TableWidget()
gen_id_chart = IDTableWidget()
nature_chart = NatureTableWidget()
license = License()
credits = Credits()
version_dialog = Version_Dialog()


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
        new_ids = mw.ankimon_db.get_all_pokemon_ids()
        set_collected_ids(new_ids)

        # Clear encounter percentages cache (uses new trainer level/stats)
        clear_encounter_cache()

        # Generate a fresh encounter for the new account
        new_pokemon(mw.enemy_pokemon, mw.test_window, mw.ankimon_tracker_obj, mw.reviewer_obj)

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
