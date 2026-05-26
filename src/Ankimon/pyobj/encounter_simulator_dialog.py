import json
import os
from pathlib import Path
from PyQt6.QtWidgets import QDialog, QVBoxLayout
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import QUrl, QObject, pyqtSlot, Qt
from PyQt6.QtGui import QColor

from aqt import mw
from ..functions import encounter_functions as ef
from .. import business
from ..singletons import (
    main_pokemon,
    ankimon_tracker_obj,
    settings_obj,
    trainer_card
)
from ..functions.pokedex_functions import (
    search_pokedex,
    search_pokedex_by_id,
    safe_int
)


class SimulatorBridge(QObject):
    """
    Exposes slots to JavaScript via QWebChannel for retrieving initial state
    and running real-time encounter rate calculations.
    """
    def __init__(self, dialog):
        super().__init__()
        self.dialog = dialog

    @pyqtSlot(result=str)
    def get_initial_state(self) -> str:
        """
        Fetches the player's active live data state to pre-populate simulator sliders.
        """
        # 1. Trainer Level
        t_level = trainer_card.level if trainer_card and hasattr(trainer_card, 'level') else 1

        # 2. Dex Completion Percentage
        d_pct = 0.0
        try:
            from ..functions.pokedex_functions import _load_pokedex_cache
            pokedex_data = _load_pokedex_cache()
            if pokedex_data and hasattr(mw, 'ankimon_db') and mw.ankimon_db:
                caught_ids = mw.ankimon_db.get_all_pokemon_ids()
                caught_species = set()
                for pid in caught_ids:
                    if pid >= 10000:
                        name = search_pokedex_by_id(pid)
                        if name and name != "Pokémon not found":
                            base_id = safe_int(search_pokedex(name, "species_id"))
                            if base_id:
                                caught_species.add(base_id)
                    else:
                        caught_species.add(pid)
                        
                unique_species_in_game = {safe_int(v.get("species_id")) for v in pokedex_data.values() if v.get("species_id")}
                unique_species_in_game.discard(0)
                total_species_count = len(unique_species_in_game) if unique_species_in_game else 1
                d_pct = (len(caught_species & unique_species_in_game) / total_species_count) * 100.0
        except Exception as e:
            print(f"[Ankimon Bridge] Warning: Could not calculate live Dex Completion: {e}")

        # 3. Reviews Done
        reviews = ankimon_tracker_obj.get_total_reviews() if ankimon_tracker_obj else 0

        # 4. Daily Goal
        daily_goal = 100
        try:
            if settings_obj:
                daily_goal = int(settings_obj.get("battle.daily_average"))
        except Exception:
            pass

        # 5. Average CP
        avg_cp = 10.0
        try:
            if hasattr(mw, 'ankimon_db') and mw.ankimon_db:
                all_pkmn = mw.ankimon_db.get_all_pokemon()
                if all_pkmn:
                    cps = []
                    for p in all_pkmn:
                        try:
                            cp = business.calculate_cp_from_dict(p)
                            cps.append(cp)
                        except Exception:
                            pass
                    cps.sort(reverse=True)
                    top_6 = cps[:6]
                    avg_cp = sum(top_6) / len(top_6) if top_6 else 10.0
        except Exception as e:
            print(f"[Ankimon Bridge] Warning: Could not calculate live top-6 CP: {e}")

        # 6. Main Pokémon Level
        main_lvl = main_pokemon.level if main_pokemon and hasattr(main_pokemon, 'level') and main_pokemon.level is not None else 1

        # Check which system is currently active in the Ankimon add-on
        active_system = "Overhaul" if ef.USE_OVERHAUL_ENCOUNTER_SYSTEM else "Legacy"

        # Package Overhaul Configuration constants dynamically from encounter_functions
        overhaul_config = {
            "ep_weight_trainer_level": float(ef.EP_WEIGHT_TRAINER_LEVEL),
            "ep_weight_dex_completion": float(ef.EP_WEIGHT_DEX_COMPLETION),
            "ep_weight_session_progress": float(ef.EP_WEIGHT_SESSION_PROGRESS),
            "ep_weight_core_team_power": float(ef.EP_WEIGHT_CORE_TEAM_POWER),
            "trainer_level_cap": float(ef.TRAINER_LEVEL_CAP),
            "core_team_power_cap": float(ef.CORE_TEAM_POWER_CAP),
            "tier_params": ef.OVERHAUL_TIER_PARAMS,
            "level_thresholds": ef.OVERHAUL_LEVEL_THRESHOLDS,
            "pity_thresholds": ef.OVERHAUL_PITY_THRESHOLDS,
            "pity_divisor": float(ef.OVERHAUL_PITY_DIVISOR)
        }

        state = {
            "trainer_level": int(t_level),
            "dex_completion": round(d_pct, 1),
            "reviews_done": int(reviews),
            "daily_goal": int(daily_goal),
            "avg_cp": int(avg_cp),
            "main_level": int(main_lvl),
            "config": overhaul_config,
            "active_system": active_system
        }
        return json.dumps(state)

    @pyqtSlot(str, result=str)
    def calculate_rates_js(self, slider_state_json: str) -> str:
        """
        Receives slider values, executes backend calculations, and returns JSON weights.
        """
        slider_state = json.loads(slider_state_json)
        result = self.dialog.calculate_rates(slider_state)
        return json.dumps(result)


class EncounterSimulatorDialog(QDialog):
    """
    Modern PyQt6 dialog housing the Encounter Rate Simulator web view.
    Exposes simulated mathematical weighting without code duplication.
    """
    def __init__(self, addon_dir: Path):
        super().__init__()
        self.addon_dir = addon_dir
        self.setWindowTitle("Ankimon Encounter Rate Simulator")
        self.resize(1100, 800)

        # Allow minimizing/maximizing cleanly
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint)

        # Setup Layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        # Setup QWebEngineView
        self.webview = QWebEngineView()
        # Prevent white background loading flash
        self.webview.page().setBackgroundColor(QColor(13, 15, 25))
        
        # Configure WebChannel communication
        self.channel = QWebChannel(self.webview)
        self.bridge = SimulatorBridge(self)
        self.channel.registerObject("pyBridge", self.bridge)
        self.webview.page().setWebChannel(self.channel)

        layout.addWidget(self.webview)

        # Load Local HTML file
        html_path = self.addon_dir / "encounter_simulator" / "simulator.html"
        self.webview.setUrl(QUrl.fromLocalFile(html_path.as_posix()))

    def calculate_rates(self, slider_state: dict) -> dict:
        """
        Temporarily monkeypatches active settings and database references to run
        live math formulas directly from encounter_functions.py, then restores state.
        """
        # 1. Clear caches first
        ef.clear_encounter_cache()

        # 2. Preserve original global references before simulation override
        orig_use_overhaul = ef.USE_OVERHAUL_ENCOUNTER_SYSTEM
        orig_main_pokemon_level = getattr(main_pokemon, "level", 1)
        orig_trainer_card_level = getattr(trainer_card, "level", 1)
        orig_db = getattr(mw, "ankimon_db", None)
        orig_calc_cp = getattr(business, "calculate_cp_from_dict", None)
        orig_ef_calc_cp = getattr(ef, "calculate_cp_from_dict", None)

        # 3. Calculate "Current Live Rates" under both systems based on absolute active save database values
        live_reviews = ankimon_tracker_obj.get_total_reviews() if ankimon_tracker_obj else 0
        live_goal = 100
        try:
            live_goal = int(settings_obj.get("battle.daily_average"))
        except Exception:
            pass
        live_trainer_lvl = trainer_card.level if trainer_card and hasattr(trainer_card, 'level') else 1

        # Calculate Live Overhaul Rates
        ef.USE_OVERHAUL_ENCOUNTER_SYSTEM = True
        ef.clear_encounter_cache()
        live_overhaul_rates = ef.modify_percentages(live_reviews, live_goal, live_trainer_lvl)

        # Calculate Live Legacy Rates
        ef.USE_OVERHAUL_ENCOUNTER_SYSTEM = False
        ef.clear_encounter_cache()
        live_legacy_rates = ef.modify_percentages(live_reviews, live_goal, live_trainer_lvl)

        # 4. Perform simulation override swaps
        # A. Swap Main Pokemon Level
        if main_pokemon:
            main_pokemon.level = slider_state["main_level"]
        if trainer_card:
            trainer_card.level = slider_state["trainer_level"]

        # B. Swap Database with a mock containing matching length and CP outputs
        class MockDB:
            def get_all_pokemon_ids(self):
                try:
                    from ..functions.pokedex_functions import _load_pokedex_cache
                    pokedex_data = _load_pokedex_cache()
                    unique_species = {ef.safe_int(v.get("species_id")) for v in pokedex_data.values() if v.get("species_id")}
                    unique_species.discard(0)
                    total_count = len(unique_species) if unique_species else 151
                except Exception:
                    total_count = 151

                target_count = int((slider_state["dex_completion"] / 100.0) * total_count)
                return list(range(1, target_count + 1))

            def get_all_pokemon(self):
                # Returns 6 elements to feed average top-6 CP calculation
                return [{"cp": slider_state["avg_cp"]}] * 6

            def get_user_data(self, key):
                # Fallback to active pity values inside database so pity boosts display correctly
                if orig_db and hasattr(orig_db, "get_user_data"):
                    return orig_db.get_user_data(key)
                return None

        mw.ankimon_db = MockDB()

        # C. Monkeypatch both business and ef calculate_cp_from_dict to return simulated avg CP directly
        business.calculate_cp_from_dict = lambda p: slider_state["avg_cp"]
        ef.calculate_cp_from_dict = lambda p: slider_state["avg_cp"]

        # D. Calculate Simulated Overhaul Rates
        ef.USE_OVERHAUL_ENCOUNTER_SYSTEM = True
        ef.clear_encounter_cache()
        overhaul_rates = ef.modify_percentages(
            slider_state["reviews_done"],
            slider_state["daily_goal"],
            slider_state["trainer_level"]
        )

        # E. Calculate Simulated Legacy Rates
        ef.USE_OVERHAUL_ENCOUNTER_SYSTEM = False
        ef.clear_encounter_cache()
        legacy_rates = ef.modify_percentages(
            slider_state["reviews_done"],
            slider_state["daily_goal"],
            slider_state["trainer_level"]
        )

        # 5. Restore original references
        ef.USE_OVERHAUL_ENCOUNTER_SYSTEM = orig_use_overhaul
        if main_pokemon and hasattr(main_pokemon, "level"):
            main_pokemon.level = orig_main_pokemon_level
        if trainer_card and hasattr(trainer_card, "level"):
            trainer_card.level = orig_trainer_card_level
        mw.ankimon_db = orig_db
        if orig_calc_cp:
            business.calculate_cp_from_dict = orig_calc_cp
        if orig_ef_calc_cp:
            ef.calculate_cp_from_dict = orig_ef_calc_cp
        ef.clear_encounter_cache()

        # 6. Compute EP Mastery Index component values dynamically using constants from encounter_functions
        t_norm = min((slider_state["trainer_level"] / ef.TRAINER_LEVEL_CAP) * 100.0, 100.0)
        d_norm = slider_state["dex_completion"]
        s_norm = min((slider_state["reviews_done"] / slider_state["daily_goal"]) * 100.0, 100.0)
        c_norm = min((slider_state["avg_cp"] / ef.CORE_TEAM_POWER_CAP) * 100.0, 100.0)
        simulated_ep = (ef.EP_WEIGHT_TRAINER_LEVEL * t_norm) + \
                       (ef.EP_WEIGHT_DEX_COMPLETION * d_norm) + \
                       (ef.EP_WEIGHT_SESSION_PROGRESS * s_norm) + \
                       (ef.EP_WEIGHT_CORE_TEAM_POWER * c_norm)
        simulated_ep = max(0.0, min(simulated_ep, 100.0))

        # Check Active Locks dynamically from OVERHAUL_LEVEL_THRESHOLDS
        locks = {tier: (slider_state["main_level"] < limit) for tier, limit in ef.OVERHAUL_LEVEL_THRESHOLDS.items()}

        return {
            "live_overhaul": live_overhaul_rates,
            "live_legacy": live_legacy_rates,
            "overhaul": overhaul_rates,
            "legacy": legacy_rates,
            "ep": simulated_ep,
            "locks": locks
        }
