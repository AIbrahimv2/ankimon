import sys
import os
import json
import random
from unittest.mock import MagicMock
import importlib.util

# --- CONFIGURATION ---
SCENARIOS_TO_RUN = [21, 22]
N = {
    1: 200000,
    2: 50000,
    3: 50000,
    4: 200000,
    5: 200000,
    6: 200000,
    7: 50000,
    8: 50000,
    11: 50000,
    12: 50000,
    13: 50000,
    14: 50000,
    15: 200000,
    16: 400000,
    17: 10000,
    18: 100000,
    19: 100000,
    20: 500000,
    21: 10000,
    22: 10000,
}

# --- SIMULATION SETTINGS ---
MAIN_POKEMON_LEVEL = 50
BYPASS_PREREQUISITES = True
BYPASS_MIN_LEVEL_CHECK = False
BYPASS_BASE_FORM_CHECK = True
# ---------------------------

import types
class MockModule(MagicMock):
    pass

# Initialize addon, addon.pyobj and addon.functions as packages so relative imports resolve
for pkg in ("addon", "addon.pyobj", "addon.functions"):
    mod = types.ModuleType(pkg)
    mod.__path__ = []
    sys.modules[pkg] = mod

modules_to_mock = [
    "aqt", "aqt.qt", "aqt.utils", "anki", "anki.hooks",
    "addon.pyobj.ankimon_tracker", "addon.pyobj.pokemon_obj",
    "addon.pyobj.reviewer_obj", "addon.pyobj.test_window", "addon.pyobj.trainer_card",
    "addon.pyobj.InfoLogger", "addon.pyobj.evolution_window", "addon.pyobj.attack_dialog",
    "addon.pyobj.translator", "addon.pyobj.error_handler",
    "addon.functions.pokemon_functions", "addon.functions.pokedex_functions",
    "addon.functions.trainer_functions", "addon.functions.badges_functions",
    "addon.functions.drawing_utils", "addon.utils", "addon.business", "addon.const",
    "addon.singletons", "addon.functions.encounter_data", "addon.functions.friendship_evolution"
]
for mod in modules_to_mock:
    sys.modules[mod] = MockModule()

sys.modules["addon.pyobj.ankimon_tracker"].AnkimonTracker = MockModule
sys.modules["addon.pyobj.pokemon_obj"].PokemonObject = MockModule
sys.modules["addon.pyobj.reviewer_obj"].Reviewer_Manager = MockModule
sys.modules["addon.pyobj.test_window"].TestWindow = MockModule
sys.modules["addon.pyobj.trainer_card"].TrainerCard = MockModule
sys.modules["addon.pyobj.InfoLogger"].ShowInfoLogger = MockModule
sys.modules["addon.pyobj.evolution_window"].EvoWindow = MockModule
sys.modules["addon.pyobj.attack_dialog"].AttackDialog = MockModule
sys.modules["addon.pyobj.translator"].Translator = MockModule
sys.modules["addon.pyobj.error_handler"].show_warning_with_traceback = lambda *args, **kwargs: None

sys.modules["addon.functions.pokemon_functions"].find_experience_for_level = lambda *args: 0
sys.modules["addon.functions.pokemon_functions"].get_levelup_move_for_pokemon = lambda *args: None
sys.modules["addon.functions.pokemon_functions"].pick_random_gender = lambda *args: "Male"
sys.modules["addon.functions.pokemon_functions"].shiny_chance = lambda *args: False

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
pokedex_path = os.path.join(base_dir, "src", "Ankimon", "data_files", "pokedex.json")
with open(pokedex_path, "r", encoding="utf-8") as f:
    pokedex_data = json.load(f)

id_to_name = {}
for name, data in pokedex_data.items():
    if "actual_id" in data:
        id_to_name[data["actual_id"]] = name

def search_pokedex_by_id(pkmn_id):
    return id_to_name.get(pkmn_id, "Pokémon not found")

def search_pokedex(name, key):
    if not isinstance(name, str):
        return None
    # Normalize name to match JSON keys (e.g., "Darumaka-Galar" -> "darumakagalar")
    name_key = name.lower().replace("-", "").replace(" ", "").replace("'", "")
    if name_key in pokedex_data:
        return pokedex_data[name_key].get(key)
    return None

def safe_int(val):
    try:
        return int(val)
    except:
        return 0

sys.modules["addon.functions.pokedex_functions"].check_evolution_for_pokemon = lambda *args: None
sys.modules["addon.functions.pokedex_functions"].get_all_pokemon_moves = lambda *args: []
sys.modules["addon.functions.pokedex_functions"].get_base_experience = lambda *args: 100
sys.modules["addon.functions.pokedex_functions"].get_effort_values = lambda *args: {}
sys.modules["addon.functions.pokedex_functions"].get_growth_rate = lambda *args: "Medium Fast"
sys.modules["addon.functions.pokedex_functions"].return_name_for_id = search_pokedex_by_id
sys.modules["addon.functions.pokedex_functions"].search_pokedex = search_pokedex
sys.modules["addon.functions.pokedex_functions"].search_pokedex_by_id = search_pokedex_by_id
sys.modules["addon.functions.pokedex_functions"].safe_int = safe_int
sys.modules["addon.functions.pokedex_functions"].get_pretty_name_for_name = lambda name: name

sys.modules["addon.functions.trainer_functions"].xp_share_gain_exp = lambda *args: None
sys.modules["addon.functions.badges_functions"].check_for_badge = lambda *args: False
sys.modules["addon.functions.badges_functions"].receive_badge = lambda *args: None
sys.modules["addon.functions.drawing_utils"].tooltipWithColour = lambda *args: None

collected_ids_mock = set(range(1, 11000))
sys.modules["addon.utils"].limit_ev_yield = lambda *args: None
sys.modules["addon.utils"].play_effect_sound = lambda *args: None
sys.modules["addon.utils"].get_ev_spread = lambda *args: {}
sys.modules["addon.utils"].is_alive = lambda *args: True
sys.modules["addon.utils"].load_collected_pokemon_ids = lambda: collected_ids_mock

sys.modules["addon.business"].calc_experience = lambda *args: 0
sys.path.insert(0, os.path.join(base_dir, "src", "Ankimon"))
import const
import functions.encounter_data as ed

sys.modules["addon.const"].gen_ids = const.gen_ids
sys.modules["addon.functions.encounter_data"] = ed
sys.modules["addon.functions"].encounter_data = ed

class MockPokemon:
    def __init__(self):
        self.level = MAIN_POKEMON_LEVEL
class MockTrainerCard:
    def __init__(self):
        self.level = 10
class MockSettings:
    def __init__(self):
        self.config = {}
        self.config["battle.daily_average"] = 100
    def get(self, key, default=None):
        return self.config.get(key, default)
    def set_config(self, cfg):
        self.config.update(cfg)

sys.modules["addon.singletons"].main_pokemon = MockPokemon()
sys.modules["addon.singletons"].ankimon_tracker_obj = MockModule()
sys.modules["addon.singletons"].ankimon_tracker_obj.get_total_reviews = lambda: 100
sys.modules["addon.singletons"].trainer_card = MockTrainerCard()
mock_settings = MockSettings()
sys.modules["addon.singletons"].settings_obj = mock_settings
sys.modules["addon.singletons"].translator = MockModule()
sys.modules["addon.singletons"].ankimon_db = MockModule()
sys.modules["addon.singletons"].pokemon_pc = MockModule()

spec = importlib.util.spec_from_file_location("addon.functions.encounter_functions", os.path.join(base_dir, "src", "Ankimon", "functions", "encounter_functions.py"))
ef = importlib.util.module_from_spec(spec)
sys.modules["addon.functions.encounter_functions"] = ef
spec.loader.exec_module(ef)

if BYPASS_PREREQUISITES:
    ef._meets_prerequisites = lambda pokemon_id, collected_ids: True
if BYPASS_MIN_LEVEL_CHECK:
    ef.check_min_generate_level = lambda name: 1
if BYPASS_BASE_FORM_CHECK:
    ef._player_owns_base_form = lambda actual_id, collected_ids: True

from functools import lru_cache
# Cache the heavy utility lookups
ef.search_pokedex = lru_cache(maxsize=None)(ef.search_pokedex)
ef.check_min_generate_level = lru_cache(maxsize=None)(ef.check_min_generate_level)

# Special handling for functions with unhashable 'set' arguments
original_meets = ef._meets_prerequisites
@lru_cache(maxsize=None)
def cached_meets(pid):
    return original_meets(pid, collected_ids_mock)
ef._meets_prerequisites = lambda pid, coll: cached_meets(pid)

original_owns = ef._player_owns_base_form
@lru_cache(maxsize=None)
def cached_owns(pid):
    return original_owns(pid, collected_ids_mock)
ef._player_owns_base_form = lambda pid, coll: cached_owns(pid)

original_check_id_ok = ef.check_id_ok
ef.check_id_ok = lru_cache(maxsize=None)(original_check_id_ok)

def set_config(cfg):
    # Clear all caches for the new configuration
    ef.check_id_ok.cache_clear()
    ef.search_pokedex.cache_clear()
    ef.check_min_generate_level.cache_clear()
    cached_meets.cache_clear()
    cached_owns.cache_clear()
    
    mock_settings.config = {"battle.daily_average": 100}
    mock_settings.set_config(cfg)
    ef.settings_obj = mock_settings
    ef.clear_encounter_cache()

def run_simulation(config, N=200000, force_tier=None):
    set_config(config)
    original_get_tier = ef.get_tier
    if force_tier:
        ef.get_tier = lambda *args, **kwargs: force_tier
    
    encounters = []
    for count in range(N):
        if count % 1000 == 0:
            print(f"  ...generated {count} encounters", flush=True)
        res = ef.generate_random_pokemon(MAIN_POKEMON_LEVEL, sys.modules["addon.singletons"].ankimon_tracker_obj)
        name, pokemon_id, tier = res[0], res[1], res[14]
        
        forme = search_pokedex(name, "forme")
        generation = ef.get_base_species_gen(pokemon_id)
        is_regional = pokemon_id >= 10000 and forme in ["Alola", "Galar", "Hisui", "Paldea"]
        
        encounters.append({
            "pokemon_id": pokemon_id,
            "name": name,
            "tier": tier,
            "forme": forme,
            "generation": generation,
            "is_regional": is_regional
        })
        
    if force_tier:
        ef.get_tier = original_get_tier
        
    return encounters

def analyze_encounters(encounters):
    stats = {
        "total": len(encounters),
        "by_id": {},
        "by_generation": {},
        "by_tier": {},
        "by_forme": {},
        "regional_count": 0,
    }
    for e in encounters:
        pid = str(e["pokemon_id"])
        gen = e["generation"]
        tier = e["tier"]
        forme = e["forme"] or "Base"
        name = e["name"]
        
        if pid not in stats["by_id"]:
            stats["by_id"][pid] = {
                "count": 0,
                "name": name,
                "generation": gen,
                "tier": tier
            }
        stats["by_id"][pid]["count"] += 1
        
        stats["by_generation"][gen] = stats["by_generation"].get(gen, 0) + 1
        stats["by_tier"][tier] = stats["by_tier"].get(tier, 0) + 1
        stats["by_forme"][forme] = stats["by_forme"].get(forme, 0) + 1
        if e["is_regional"]:
            stats["regional_count"] += 1
    return stats

results_json = {}
report_lines = []

def log(msg):
    print(msg)
    report_lines.append(msg)

def log_test(scenario, passed, msgs):
    status = "PASS" if passed else "FAIL"
    log(f"[{status}] {scenario}")
    for m in msgs:
        log(f"  - {m}")
    log("")

def should_run(n):
    return not SCENARIOS_TO_RUN or n in SCENARIOS_TO_RUN

def run_all():
    print("====================================================")
    print("Ankimon Encounter Weighting System - Phase 2 Test Report")
    print("====================================================")
    print(f"SETTINGS: Level={MAIN_POKEMON_LEVEL}, BypassLvl={BYPASS_MIN_LEVEL_CHECK}, BypassPre={BYPASS_PREREQUISITES}, BypassOwn={BYPASS_BASE_FORM_CHECK}")
    print("----------------------------------------------------")

    # Base config
    base_config = {f"misc.gen{i}": True for i in range(1, 10)}
    base_config["misc.active_region"] = None
    
    def get_count(stats, pid):
        return stats["by_id"].get(str(pid), {}).get("count", 0)

    # We always need stats1 for comparisons in 4, 5, 6
    stats1 = None
    encs1 = None

    # ----------------------------------------------------
    # SCENARIO 1 — BASELINE: No region, all gens enabled
    # ----------------------------------------------------
    if should_run(1) or should_run(4) or should_run(5) or should_run(6):
        sc1_cfg = dict(base_config)
        encs1 = run_simulation(sc1_cfg, N=N[1])
        stats1 = analyze_encounters(encs1)
        results_json["scenario_1"] = stats1
        
        msgs1 = []
        passed1 = True
        
        if stats1["regional_count"] == 0:
            msgs1.append("FAIL: No regional forms ever appear.")
            passed1 = False
        else:
            msgs1.append(f"PASS: Regional forms appear ({stats1['regional_count']}/{stats1['total']})")
            
        # --- MEOWTH CHECK ---
        meowth_base = 52
        meowth_alola = 10107
        meowth_galar = 10161
        m_total = get_count(stats1, meowth_base) + get_count(stats1, meowth_alola) + get_count(stats1, meowth_galar)
        if m_total > 0:
            br = get_count(stats1, meowth_base) / m_total
            ar = get_count(stats1, meowth_alola) / m_total
            gr = get_count(stats1, meowth_galar) / m_total
            msgs1.append(f"Meowth: Base {br:.1%}, Alola {ar:.1%}, Galar {gr:.1%} (target ~7% each)")
            if not (0.04 <= ar <= 0.10 and 0.04 <= gr <= 0.10):
                passed1 = False
                msgs1.append("FAIL: Meowth variance too high")

        # --- TAUROS CHECK ---
        tauros_base = 128
        paldea_tauros = [10250, 10251, 10252]
        t_total = get_count(stats1, tauros_base) + sum(get_count(stats1, tid) for tid in paldea_tauros)
        if t_total > 0:
            for tid in paldea_tauros:
                rate = get_count(stats1, tid) / t_total
                msgs1.append(f"Tauros {tid}: {rate:.1%} (target ~7%)")
                if not (0.04 <= rate <= 0.10):
                    passed1 = False
        
        # --- WOOPER CHECK ---
        wooper_base = 194
        wooper_paldea = 10253
        w_total = get_count(stats1, wooper_base) + get_count(stats1, wooper_paldea)
        if w_total > 0:
            wr = get_count(stats1, wooper_paldea) / w_total
            msgs1.append(f"Wooper Paldea: {wr:.1%} (target ~7%)")
            if not (0.04 <= wr <= 0.10):
                passed1 = False

        # --- TAUROS CHECK ---
        tauros_base = 128
        paldea_tauros = [10250, 10251, 10252]
        t_total = get_count(stats1, tauros_base) + sum(get_count(stats1, tid) for tid in paldea_tauros)
        if t_total > 0:
            for tid in paldea_tauros:
                rate = get_count(stats1, tid) / t_total
                msgs1.append(f"Tauros {tid}: {rate:.1%} (target ~7%)")
                if not (0.04 <= rate <= 0.10):
                    passed1 = False
        
        # --- WOOPER CHECK ---
        wooper_base = 194
        wooper_paldea = 10253
        w_total = get_count(stats1, wooper_base) + get_count(stats1, wooper_paldea)
        if w_total > 0:
            wr = get_count(stats1, wooper_paldea) / w_total
            msgs1.append(f"Wooper Paldea: {wr:.1%} (target ~7%)")
            if not (0.04 <= wr <= 0.10):
                passed1 = False

        if should_run(1):
            log_test("SCENARIO 1 — BASELINE", passed1, msgs1)

    # ----------------------------------------------------
    # SCENARIO 2 — No region, gens 7/8/9 disabled
    # ----------------------------------------------------
    if should_run(2):
        sc2_cfg = dict(base_config)
        sc2_cfg["misc.gen7"] = False
        sc2_cfg["misc.gen8"] = False
        sc2_cfg["misc.gen9"] = False
        encs2 = run_simulation(sc2_cfg, N=N[2])
        stats2 = analyze_encounters(encs2)
        results_json["scenario_2"] = stats2
        msgs2 = []
        passed2 = True
        
        if stats2["regional_count"] > 0:
            passed2 = False
            msgs2.append(f"FAIL: Regional forms appeared when gens 7/8/9 disabled ({stats2['regional_count']})")
        else:
            msgs2.append("PASS: No regional forms appeared")
            
        if sum(stats2["by_generation"].get(g, 0) for g in [7, 8, 9]) > 0:
            passed2 = False
            msgs2.append("FAIL: Gen 7/8/9 Pokemon appeared")
        else:
            msgs2.append("PASS: No Gen 7/8/9 Pokemon appeared")
            
        log_test("SCENARIO 2 — No region, gens 7/8/9 disabled", passed2, msgs2)

    # ----------------------------------------------------
    # SCENARIO 3 — No region, only gen1 + gen7 enabled
    # ----------------------------------------------------
    if should_run(3):
        sc3_cfg = {f"misc.gen{i}": False for i in range(1, 10)}
        sc3_cfg["misc.gen1"] = True
        sc3_cfg["misc.gen7"] = True
        sc3_cfg["misc.active_region"] = None
        encs3 = run_simulation(sc3_cfg, N=N[3])
        stats3 = analyze_encounters(encs3)
        results_json["scenario_3"] = stats3
        msgs3 = []
        passed3 = True
        
        if sum(stats3["by_generation"].get(g, 0) for g in [2,3,4,5,6,8,9]) > 0:
            passed3 = False
            msgs3.append("FAIL: Unauthorized gens appeared")
        else:
            msgs3.append("PASS: Only Gen 1 and Gen 7 appeared")
            
        if stats3["by_forme"].get("Alola", 0) == 0:
            passed3 = False
            msgs3.append("FAIL: No Alolan forms appeared")
        else:
            msgs3.append(f"PASS: Alolan forms appeared ({stats3['by_forme'].get('Alola')})")
            
        log_test("SCENARIO 3 — No region, gen1+gen7 only", passed3, msgs3)

    # ----------------------------------------------------
    # SCENARIO 4 — Region = kanto, all gens enabled
    # ----------------------------------------------------
    if should_run(4):
        sc4_cfg = dict(base_config)
        sc4_cfg["misc.active_region"] = "kanto"
        encs4 = run_simulation(sc4_cfg, N=N[4])
        stats4 = analyze_encounters(encs4)
        results_json["scenario_4"] = stats4
        
        msgs4 = []
        passed4 = True
        
        gen1_s1 = stats1["by_generation"].get(1, 0) / stats1["total"]
        gen1_s4 = stats4["by_generation"].get(1, 0) / stats4["total"]
        
        if gen1_s4 <= gen1_s1 + 0.05:
            msgs4.append(f"FAIL: Gen 1 rate in Scenario 4 ({gen1_s4:.1%}) not meaningfully higher than Scenario 1 ({gen1_s1:.1%})")
            passed4 = False
        else:
            msgs4.append(f"PASS: Gen 1 rate increased from {gen1_s1:.1%} to {gen1_s4:.1%}")
            
        log_test("SCENARIO 4 — Region = kanto", passed4, msgs4)

    # ----------------------------------------------------
    # SCENARIO 5 — Region = alola, all gens enabled
    # ----------------------------------------------------
    if should_run(5):
        meowth_alola = 10107
        meowth_galar = 10161
        sc5_cfg = dict(base_config)
        sc5_cfg["misc.active_region"] = "alola"
        encs5 = run_simulation(sc5_cfg, N=N[5])
        stats5 = analyze_encounters(encs5)
        results_json["scenario_5"] = stats5
        
        msgs5 = []
        passed5 = True
        vulpix_alola = 10103
        valola_s1 = get_count(stats1, vulpix_alola)
        valola_s5 = get_count(stats5, vulpix_alola)
        
        if valola_s5 <= valola_s1:
            msgs5.append(f"FAIL: Alolan Vulpix rate didn't increase ({valola_s1} -> {valola_s5})")
            passed5 = False
        else:
            msgs5.append(f"PASS: Alolan Vulpix increased ({valola_s1} -> {valola_s5})")
            
        alola_m = get_count(stats5, meowth_alola)
        galar_m = get_count(stats5, meowth_galar)
        if alola_m <= galar_m:
            msgs5.append(f"FAIL: Alolan Meowth ({alola_m}) not strictly > Galarian Meowth ({galar_m})")
            passed5 = False
        else:
            msgs5.append(f"PASS: Alolan Meowth ({alola_m}) > Galarian Meowth ({galar_m})")
            
        log_test("SCENARIO 5 — Region = alola", passed5, msgs5)

    # ----------------------------------------------------
    # SCENARIO 6 — Region = hisui, all gens enabled
    # ----------------------------------------------------
    if should_run(6):
        sc6_cfg = dict(base_config)
        sc6_cfg["misc.active_region"] = "hisui"
        encs6 = run_simulation(sc6_cfg, N=N[6])
        stats6 = analyze_encounters(encs6)
        results_json["scenario_6"] = stats6
        
        msgs6 = []
        passed6 = True
        
        gen4_s1 = stats1["by_generation"].get(4, 0) / stats1["total"]
        gen4_s6 = stats6["by_generation"].get(4, 0) / stats6["total"]
        
        gen8_s1 = stats1["by_generation"].get(8, 0) / stats1["total"]
        gen8_s6 = stats6["by_generation"].get(8, 0) / stats6["total"]
        
        msgs6.append(f"Gen 4 rate: {gen4_s1:.1%} -> {gen4_s6:.1%}")
        msgs6.append(f"Gen 8 rate: {gen8_s1:.1%} -> {gen8_s6:.1%}")
        
        hisui_ids = ef.encounter_data.REGIONAL_FORMS.get("hisui", [])
        hisui_s1 = sum(get_count(stats1, aid) for aid in hisui_ids)
        hisui_s6 = sum(get_count(stats6, aid) for aid in hisui_ids)
        msgs6.append(f"Hisui forms: {hisui_s1} -> {hisui_s6}")
        
        if hisui_s6 <= hisui_s1: passed6 = False; msgs6.append("FAIL: Hisui forms not boosted")
        
        log_test("SCENARIO 6 — Region = hisui", passed6, msgs6)
    
    # ----------------------------------------------------
    # SCENARIO 7 — Region = hisui, gen4 disabled
    # ----------------------------------------------------
    if should_run(7):
        sc7_cfg = dict(base_config)
        sc7_cfg["misc.active_region"] = "hisui"
        sc7_cfg["misc.gen4"] = False
        encs7 = run_simulation(sc7_cfg, N=N[7])
        stats7 = analyze_encounters(encs7)
        results_json["scenario_7"] = stats7
        msgs7 = []
        passed7 = True
        if stats7["by_generation"].get(4, 0) > 0:
            passed7 = False
            msgs7.append("FAIL: Gen 4 Pokemon appeared when disabled")
        else:
            msgs7.append("PASS: No Gen 4 Pokemon appeared")
        log_test("SCENARIO 7 — Region = hisui, gen4 disabled", passed7, msgs7)

    # ----------------------------------------------------
    # SCENARIO 8 — Region = alola, gen7 disabled
    # ----------------------------------------------------
    if should_run(8):
        sc8_cfg = dict(base_config)
        sc8_cfg["misc.active_region"] = "alola"
        sc8_cfg["misc.gen7"] = False
        encs8 = run_simulation(sc8_cfg, N=N[8])
        stats8 = analyze_encounters(encs8)
        results_json["scenario_8"] = stats8
        msgs8 = []
        passed8 = True
        if stats8["by_forme"].get("Alola", 0) > 0:
            passed8 = False
            msgs8.append("FAIL: Alolan forms appeared despite gen7 disabled")
        else:
            msgs8.append("PASS: No Alolan forms appeared")
        log_test("SCENARIO 8 — Region = alola, gen7 disabled", passed8, msgs8)

    # ----------------------------------------------------
    # SCENARIO 11 — All gens disabled except gen1
    # ----------------------------------------------------
    if should_run(11):
        sc11_cfg = {f"misc.gen{i}": False for i in range(1, 10)}
        sc11_cfg["misc.gen1"] = True
        sc11_cfg["misc.active_region"] = None
        encs11 = run_simulation(sc11_cfg, N=N[11])
        stats11 = analyze_encounters(encs11)
        results_json["scenario_11"] = stats11
        msgs11 = []
        passed11 = True
        if sum(stats11["by_generation"].get(g, 0) for g in range(2, 10)) > 0:
            passed11 = False
            msgs11.append("FAIL: Non-gen1 pokemon appeared")
        else:
            msgs11.append("PASS: Only Gen 1 appeared")
        if stats11["regional_count"] > 0:
            passed11 = False
            msgs11.append("FAIL: Regional forms appeared")
        else:
            msgs11.append("PASS: No regional forms appeared")
        log_test("SCENARIO 11 — All gens disabled except gen1", passed11, msgs11)

    # ----------------------------------------------------
    # SCENARIO 12 — Mega/Gmax tier with region = kanto
    # ----------------------------------------------------
    if should_run(12):
        sc12_cfg = dict(base_config)
        sc12_cfg["misc.active_region"] = "kanto"
        encs12 = run_simulation(sc12_cfg, N=N[12], force_tier="Mega")
        stats12 = analyze_encounters(encs12)
        results_json["scenario_12"] = stats12
        msgs12 = []
        passed12 = True
        if stats12["by_generation"].get(1, 0) == 0:
            passed12 = False
            msgs12.append("FAIL: No Gen 1 Megas appeared")
        else:
            msgs12.append(f"PASS: Gen 1 Megas appeared ({stats12['by_generation'].get(1, 0)} times)")
        log_test("SCENARIO 12 — Mega/Gmax tier with region = kanto", passed12, msgs12)

    # ----------------------------------------------------
    # SCENARIO 13 — Legendary tier with region = kanto
    # ----------------------------------------------------
    if should_run(13):
        sc13_cfg = dict(base_config)
        sc13_cfg["misc.active_region"] = "kanto"
        encs13 = run_simulation(sc13_cfg, N=N[13], force_tier="Legendary")
        stats13 = analyze_encounters(encs13)
        results_json["scenario_13"] = stats13
        msgs13 = []
        passed13 = True
        gen1_leg_rate = stats13["by_generation"].get(1, 0) / stats13["total"]
        msgs13.append(f"Gen 1 Legendary Rate: {gen1_leg_rate:.1%}")
        if gen1_leg_rate < 0.30:
            passed13 = False
            msgs13.append("FAIL: Gen 1 legendaries not boosted enough (expected > 30%)")
        log_test("SCENARIO 13 — Legendary tier with region = kanto", passed13, msgs13)

    # ----------------------------------------------------
    # SCENARIO 14 — Galarian birds with region = galar, gen1+gen8 enabled
    # ----------------------------------------------------
    if should_run(14):
        sc14_cfg = {f"misc.gen{i}": False for i in range(1, 10)}
        sc14_cfg["misc.gen1"] = True
        sc14_cfg["misc.gen8"] = True
        sc14_cfg["misc.active_region"] = "galar"
        encs14 = run_simulation(sc14_cfg, N=N[14], force_tier="Legendary")
        stats14 = analyze_encounters(encs14)
        results_json["scenario_14"] = stats14
        msgs14 = []
        passed14 = True
        if stats14["by_forme"].get("Galar", 0) == 0:
            passed14 = False
            msgs14.append("FAIL: No Galarian legendaries appeared")
        else:
            msgs14.append(f"PASS: Galarian legendaries appeared ({stats14['by_forme'].get('Galar')} times)")
        log_test("SCENARIO 14 — Galarian birds", passed14, msgs14)

    # ----------------------------------------------------
    # SCENARIO 15 — Full-pool fairness check (no region, all gens)
    # ----------------------------------------------------
    if should_run(15):
        encs15 = run_simulation(base_config, N=N[15], force_tier="Normal")
        stats15 = analyze_encounters(encs15)
        results_json["scenario_15"] = stats15
        msgs15 = []
        passed15 = True
        zero_count = 0
        for pid in ed.NORMAL:
            if get_count(stats15, pid) == 0 and ef.check_id_ok(pid):
                zero_count += 1
        if zero_count > 0:
            msgs15.append(f"WARN: {zero_count} eligible Normal pokemon never appeared.")
        else:
            msgs15.append("PASS: All eligible Normal pokemon appeared at least once.")
        log_test("SCENARIO 15 — Full-pool fairness check", passed15, msgs15)
    
    # ----------------------------------------------------
    # SCENARIO 16 — Tauros (3 Paldean forms) fairness check
    # ----------------------------------------------------
    if should_run(16):
        encs16 = run_simulation(base_config, N=N[16], force_tier="Normal")
        stats16 = analyze_encounters(encs16)
        results_json["scenario_16"] = stats16
        msgs16 = []
        passed16 = True
        tauros_id = 128
        paldea_tauros = [10250, 10251, 10252]
        
        t_counts = {tid: get_count(stats16, tid) for tid in [tauros_id] + paldea_tauros}
        t_total = sum(t_counts.values())
        if t_total > 0:
            for tid in paldea_tauros:
                rate = t_counts[tid] / t_total
                msgs16.append(f"Tauros {tid} rate: {rate:.1%} (expected ~7%)")
                if not (0.04 <= rate <= 0.10):
                    passed16 = False
        log_test("SCENARIO 16 — Tauros fairness check", passed16, msgs16)

    # ----------------------------------------------------
    # SCENARIO 17 — Region switching mid-session
    # ----------------------------------------------------
    if should_run(17):
        # We switch regions and see if the cache/state leaks
        msgs17 = []
        passed17 = True
        
        set_config(base_config)
        ef.generate_random_pokemon(100, sys.modules["addon.singletons"].ankimon_tracker_obj) # Warm up
        
        cfg_k = dict(base_config); cfg_k["misc.active_region"] = "kanto"
        encs_k = run_simulation(cfg_k, N=N[17])
        
        cfg_a = dict(base_config); cfg_a["misc.active_region"] = "alola"
        encs_a = run_simulation(cfg_a, N=N[17])
        
        k_in_a = sum(1 for e in encs_a if e["generation"] == 1) / N[17]
        a_in_a = sum(1 for e in encs_a if e["generation"] == 7) / N[17]
        if k_in_a > a_in_a:
            passed17 = False
            msgs17.append(f"FAIL: Kanto rate ({k_in_a:.1%}) > Alola rate ({a_in_a:.1%}) in Alola session")
        else:
            msgs17.append("PASS: No obvious state leak from Kanto to Alola")
        log_test("SCENARIO 17 — Region switching state leak", passed17, msgs17)

    # ----------------------------------------------------
    # SCENARIO 18 — Paldea region scenario
    # ----------------------------------------------------
    if should_run(18):
        sc18_cfg = dict(base_config)
        sc18_cfg["misc.active_region"] = "paldea"
        encs18 = run_simulation(sc18_cfg, N=N[18])
        stats18 = analyze_encounters(encs18)
        results_json["scenario_18"] = stats18
        msgs18 = []
        passed18 = True
        
        gen9_rate = stats18["by_generation"].get(9, 0) / stats18["total"]
        msgs18.append(f"Gen 9 rate in Paldea: {gen9_rate:.1%}")
        if gen9_rate < 0.30:
            passed18 = False
            msgs18.append("FAIL: Gen 9 not boosted in Paldea")
            
        paldea_tauros = [10250, 10251, 10252]
        p_tauros_count = sum(get_count(stats18, tid) for tid in paldea_tauros)
        if p_tauros_count == 0:
            passed18 = False
            msgs18.append("FAIL: No Paldean Tauros in Paldea region")
        log_test("SCENARIO 18 — Region = paldea", passed18, msgs18)

    # ----------------------------------------------------
    # SCENARIO 19 — Cross-gen gating: gen2+gen9 only
    # ----------------------------------------------------
    if should_run(19):
        sc19_cfg = {f"misc.gen{i}": False for i in range(1, 10)}
        sc19_cfg["misc.gen2"] = True
        sc19_cfg["misc.gen9"] = True
        sc19_cfg["misc.active_region"] = None
        encs19 = run_simulation(sc19_cfg, N=N[19])
        stats19 = analyze_encounters(encs19)
        results_json["scenario_19"] = stats19
        msgs19 = []
        passed19 = True
        
        # Wooper Paldea: Base Gen 2, Form Gen 9 -> SHOULD appear
        w_p_count = get_count(stats19, 10253)
        if w_p_count == 0:
            passed19 = False
            msgs19.append("FAIL: Paldean Wooper (Gen 2+9) did not appear")
        else:
            msgs19.append(f"PASS: Paldean Wooper appeared ({w_p_count} times)")
            
        # Tauros Paldea: Base Gen 1, Form Gen 9 -> SHOULD NOT appear (Gen 1 disabled)
        paldea_tauros = [10250, 10251, 10252]
        t_p_count = sum(get_count(stats19, tid) for tid in paldea_tauros)
        if t_p_count > 0:
            passed19 = False
            msgs19.append(f"FAIL: Paldean Tauros appeared despite Gen 1 disabled ({t_p_count} times)")
        else:
            msgs19.append("PASS: Paldean Tauros (Gen 1+9) correctly gated out")
            
        log_test("SCENARIO 19 — Cross-gen gating (Wooper vs Tauros)", passed19, msgs19)

    # ----------------------------------------------------
    # SCENARIO 20 — All variants check: gen 1+7+8+9
    # ----------------------------------------------------
    if should_run(20):
        sc20_cfg = {f"misc.gen{i}": False for i in range(1, 10)}
        for g in [1, 7, 8, 9]: sc20_cfg[f"misc.gen{g}"] = True
        sc20_cfg["misc.active_region"] = None
        encs20 = run_simulation(sc20_cfg, N=N[20])
        stats20 = analyze_encounters(encs20)
        results_json["scenario_20"] = stats20
        msgs20 = []
        passed20 = True
        
        # --- MEOWTH (Base, Alola, Galar) ---
        m_base, m_alola, m_galar = 52, 10107, 10161
        m_total = get_count(stats20, m_base) + get_count(stats20, m_alola) + get_count(stats20, m_galar)
        if m_total > 0:
            br = get_count(stats20, m_base) / m_total
            ar = get_count(stats20, m_alola) / m_total
            gr = get_count(stats20, m_galar) / m_total
            msgs20.append(f"Meowth: Base {br:.1%}, Alola {ar:.1%}, Galar {gr:.1%}")
            if not (0.04 <= ar <= 0.10 and 0.04 <= gr <= 0.10):
                passed20 = False
        
        # --- TAUROS (Base, Paldea x3) ---
        t_base = 128
        p_tauros = [10250, 10251, 10252]
        t_total = get_count(stats20, t_base) + sum(get_count(stats20, tid) for tid in p_tauros)
        if t_total > 0:
            tr = get_count(stats20, t_base) / t_total
            msgs20.append(f"Tauros: Base {tr:.1%}")
            for tid in p_tauros:
                rate = get_count(stats20, tid) / t_total
                msgs20.append(f"  - Paldea {tid}: {rate:.1%}")
                if not (0.04 <= rate <= 0.10):
                    passed20 = False
                    
        log_test("SCENARIO 20 — All variants (Meowth/Tauros) check", passed20, msgs20)

    # ----------------------------------------------------
    # SCENARIO 21 — Galarian Darmanitan region = galar, gen5+gen8 enabled
    # ----------------------------------------------------
    if should_run(21):
        sc21_cfg = {f"misc.gen{i}": False for i in range(1, 10)}
        sc21_cfg["misc.gen5"] = True
        sc21_cfg["misc.gen8"] = True
        sc21_cfg["misc.active_region"] = "galar"
        encs21 = run_simulation(sc21_cfg, N=N[21], force_tier="Normal")
        stats21 = analyze_encounters(encs21)
        results_json["scenario_21"] = stats21
        msgs21 = []
        passed21 = True
        
        # Darumaka variants
        d_base, d_galar = 554, 10176
        dn_base, dn_galar = 555, 10177
        
        c_d_base = get_count(stats21, d_base)
        c_d_galar = get_count(stats21, d_galar)
        c_dn_base = get_count(stats21, dn_base)
        c_dn_galar = get_count(stats21, dn_galar)
        
        msgs21.append(f"Darumaka: Base {c_d_base}, Galar {c_d_galar}")
        msgs21.append(f"Darmanitan: Base {c_dn_base}, Galar {c_dn_galar}")
        
        if c_d_galar == 0 or c_dn_galar == 0:
            passed21 = False
            msgs21.append("FAIL: Galarian variants did not appear")
        else:
            msgs21.append("PASS: Galarian variants appeared")
            
        log_test("SCENARIO 21 — Darumaka/Darmanitan check in Galar", passed21, msgs21)

    # ----------------------------------------------------
    # SCENARIO 22 — Starter tier: gen 1+2, region = kanto
    # ----------------------------------------------------
    if should_run(22):
        sc22_cfg = {f"misc.gen{i}": False for i in range(1, 10)}
        sc22_cfg["misc.gen1"] = True
        sc22_cfg["misc.gen2"] = True
        sc22_cfg["misc.active_region"] = "kanto"
        encs22 = run_simulation(sc22_cfg, N=N[22], force_tier="Starter")
        stats22 = analyze_encounters(encs22)
        results_json["scenario_22"] = stats22
        msgs22 = []
        passed22 = True
        
        gen1_starters = [1,2,3, 4,5,6, 7,8,9]
        gen2_starters = [152,153,154, 155,156,157, 158,159,160]
        
        msgs22.append("Gen 1 Individual Counts:")
        for sid in gen1_starters:
            count = get_count(stats22, sid)
            name = ef.search_pokedex_by_id(sid)
            msgs22.append(f"  - {name} ({sid}): {count} ({count/N[22]:.1%})")
            
        msgs22.append("Gen 2 Individual Counts:")
        for sid in gen2_starters:
            count = get_count(stats22, sid)
            name = ef.search_pokedex_by_id(sid)
            msgs22.append(f"  - {name} ({sid}): {count} ({count/N[22]:.1%})")
        
        c1 = sum(get_count(stats22, sid) for sid in gen1_starters)
        c2 = sum(get_count(stats22, sid) for sid in gen2_starters)
        
        # In Kanto, Gen 1 should be boosted (30% pool chance + 70% shared)
        if c1 <= c2:
            passed22 = False
            msgs22.append(f"FAIL: Gen 1 total ({c1}) <= Gen 2 total ({c2}) in Kanto")
        else:
            msgs22.append(f"PASS: Gen 1 total ({c1}) > Gen 2 total ({c2}) in Kanto")
            
        log_test("SCENARIO 22 — Starter family individual counts", passed22, msgs22)
    
if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    results_path = os.path.join(base_dir, "simulation_results.json")
    report_path = os.path.join(base_dir, "simulation_report.txt")
    try:
        run_all()
    finally:
        with open(results_path, "w") as f:
            json.dump(results_json, f, indent=2)
        with open(report_path, "w") as f:
            f.write("\n".join(report_lines))
