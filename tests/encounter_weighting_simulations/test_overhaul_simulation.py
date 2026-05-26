import sys
import os
import json
import random
from unittest.mock import MagicMock
import importlib.util
from pathlib import Path

# --- DIRECTORY RESOLUTION ---
base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, base_dir)

# --- MOCK LIFECYCLE ---
class MockModule(MagicMock):
    pass

# We use the standard Ankimon namespace so relative imports resolve through conftest packages
modules_to_mock = [
    "aqt", "aqt.qt", "aqt.utils", "anki", "anki.hooks",
    "Ankimon.pyobj.ankimon_tracker", "Ankimon.pyobj.pokemon_obj",
    "Ankimon.pyobj.reviewer_obj", "Ankimon.pyobj.test_window", "Ankimon.pyobj.trainer_card",
    "Ankimon.pyobj.InfoLogger", "Ankimon.pyobj.evolution_window", "Ankimon.pyobj.attack_dialog",
    "Ankimon.pyobj.translator", "Ankimon.pyobj.error_handler",
    "Ankimon.functions.pokemon_functions", "Ankimon.functions.pokedex_functions",
    "Ankimon.functions.trainer_functions", "Ankimon.functions.badges_functions",
    "Ankimon.functions.drawing_utils", "Ankimon.utils",
    "Ankimon.singletons", "Ankimon.functions.encounter_data", "Ankimon.functions.friendship_evolution"
]
for mod in modules_to_mock:
    sys.modules[mod] = MockModule()

# Stub out standard loaders and helpers
sys.modules["Ankimon.pyobj.error_handler"].show_warning_with_traceback = lambda *args, **kwargs: None
sys.modules["Ankimon.functions.pokemon_functions"].pick_random_gender = lambda *args: "Female"
sys.modules["Ankimon.functions.pokemon_functions"].shiny_chance = lambda *args: False

pokedex_path = os.path.join(base_dir, "src", "Ankimon", "data_files", "pokedex.json")
pokedex_data = {}
try:
    with open(pokedex_path, "r", encoding="utf-8") as f:
        pokedex_data = json.load(f)
except Exception as e:
    # If not found during headless runs, create a mock minimal pokedex
    pokedex_data = {str(i): {"species_id": i, "actual_id": i} for i in range(1, 1000)}

id_to_name = {}
for name, data in pokedex_data.items():
    if "actual_id" in data:
        id_to_name[data["actual_id"]] = name

def search_pokedex_by_id(pkmn_id):
    return id_to_name.get(pkmn_id, "Pokémon not found")

def search_pokedex(name, key):
    if not isinstance(name, str):
        return None
    name_key = name.lower().replace("-", "").replace(" ", "").replace("'", "")
    if key == "abilities":
        return {"1": "pressure"}
    if name_key in pokedex_data:
        return pokedex_data[name_key].get(key)
    return None

def safe_int(val):
    try: return int(val)
    except: return 0

sys.modules["Ankimon.functions.pokedex_functions"].search_pokedex = search_pokedex
sys.modules["Ankimon.functions.pokedex_functions"].search_pokedex_by_id = search_pokedex_by_id
sys.modules["Ankimon.functions.pokedex_functions"].safe_int = safe_int
sys.modules["Ankimon.functions.pokedex_functions"]._load_pokedex_cache = lambda: pokedex_data

# Stub database manager to mock state variables
class MockAnkimonDB:
    def __init__(self):
        self.pokemon_list = []
        self.caught_ids = set()
        self.user_data = {}
        
    def get_all_pokemon(self):
        return self.pokemon_list
        
    def get_all_pokemon_ids(self):
        return self.caught_ids
        
    def get_user_data(self, key, default=None):
        return self.user_data.get(key, default)
        
    def set_user_data(self, key, value):
        self.user_data[key] = value

mock_db = MockAnkimonDB()
class MockPokemon:
    def __init__(self):
        self.level = 5
class MockTrainerCard:
    def __init__(self):
        self.level = 1
class MockSettings:
    def __init__(self):
        self.daily_average = 100
    def get(self, key, default=None):
        if key == "battle.daily_average":
            return self.daily_average
        return default

mock_pokemon = MockPokemon()
mock_trainer = MockTrainerCard()
mock_settings = MockSettings()

# Ensure both Ankimon.singletons and aqt.mw point to the same mock database
sys.modules["aqt"].mw = MockModule()
sys.modules["aqt"].mw.ankimon_db = mock_db
sys.modules["aqt"].mw.settings_obj = mock_settings

sys.modules["Ankimon.singletons"].mw = sys.modules["aqt"].mw
sys.modules["Ankimon.singletons"].main_pokemon = mock_pokemon
sys.modules["Ankimon.singletons"].trainer_card = mock_trainer
sys.modules["Ankimon.singletons"].settings_obj = mock_settings
sys.modules["Ankimon.singletons"].ankimon_tracker_obj = MockModule()
sys.modules["Ankimon.singletons"].ankimon_tracker_obj.get_total_reviews = lambda: 0

# --- DYNAMIC SPEC LOAD ---
_src = Path(base_dir) / "src"
spec = importlib.util.spec_from_file_location(
    "Ankimon.functions.encounter_functions",
    _src / "Ankimon" / "functions" / "encounter_functions.py"
)
ef = importlib.util.module_from_spec(spec)
sys.modules["Ankimon.functions.encounter_functions"] = ef
spec.loader.exec_module(ef)

# Bypass long prerequisite recursion checks during rollout
ef._meets_prerequisites = lambda *args: True
ef._player_owns_base_form = lambda *args: True
ef.check_id_ok = lambda *args: True
ef.check_min_generate_level = lambda name: 1
ef.load_collected_pokemon_ids = lambda: set(range(1, 1000))

# --- TEST SUITE DEFINITIONS ---
report_lines = []
results_json = {}

def log(msg):
    print(msg)
    report_lines.append(msg)

def log_header(title):
    border = "=" * 60
    log(border)
    log(title)
    log(border)

def run_scenario_sim(name, N=5000):
    counts = {tier: 0 for tier in ef.OVERHAUL_TIER_PARAMS}
    for _ in range(N):
        tier = ef.get_tier(
            total_reviews=ef.ankimon_tracker_obj.get_total_reviews(),
            trainer_level=ef.trainer_card.level
        )
        counts[tier] = counts.get(tier, 0) + 1
    return counts

# ------------------------------------------------------------------------------
# 1. SCENARIO A: The Beginner Player
# ------------------------------------------------------------------------------
def simulate_scenario_a():
    log_header("SCENARIO A: The Beginner Player (Level 5 Main, 0% Progress)")
    
    # Configure beginner environment
    ef.USE_OVERHAUL_ENCOUNTER_SYSTEM = True
    mock_pokemon.level = 5
    mock_trainer.level = 1
    mock_settings.daily_average = 100
    ef.ankimon_tracker_obj.get_total_reviews = lambda: 0
    mock_db.caught_ids = set()
    mock_db.pokemon_list = []
    mock_db.user_data["ankimon_pity_trackers"] = {k: 0 for k in ef.OVERHAUL_PITY_THRESHOLDS}
    
    # Calculate EP mathematically
    ep = ef.calculate_mastery_index_ep(total_reviews=0, daily_average=100, trainer_level=1)
    log(f"Calculated EP: {ep:.4f}% (Expected ~0.50%)")
    
    # Run roll simulation
    counts = run_scenario_sim("Scenario A", N=5000)
    
    # Analyze
    log("Simulation Spawn Rates (5,000 rolls):")
    passed = True
    errors = []
    
    for tier, count in counts.items():
        rate = (count / 5000) * 100
        log(f"  - {tier}: {rate:.2f}% (Count: {count})")
        
        # Verify locks
        if tier in ["Ultra", "Legendary", "Mega", "Gmax", "Mythical", "Starter"]:
            if count > 0:
                passed = False
                errors.append(f"Locked tier '{tier}' spawned under Level 30 threshold!")
                
    if counts["Normal"] < 4500:
        passed = False
        errors.append("Normal spawn rate abnormally low for a beginner!")
        
    status = "PASS" if passed else "FAIL"
    log(f"Result: {status}")
    if errors:
        for err in errors: log(f"  [ERROR] {err}")
    return passed, counts

# ------------------------------------------------------------------------------
# 2. SCENARIO B: Mid-Game Progression
# ------------------------------------------------------------------------------
def simulate_scenario_b():
    log_header("SCENARIO B: Mid-Game Progression (Level 35 Main, EP ~25)")
    
    mock_pokemon.level = 35  # locks Legendary, Mega, Gmax, Mythical, Starter; unlocks Ultra
    mock_trainer.level = 20
    mock_settings.daily_average = 100
    ef.ankimon_tracker_obj.get_total_reviews = lambda: 60  # 60% session progress
    
    # 20% pokedex completion out of a mock 100 species
    mock_db.caught_ids = set(range(1, 21))
    pokedex_data.clear()
    pokedex_data.update({str(i): {"species_id": i, "actual_id": i} for i in range(1, 101)})
    
    # Top 6 pokemon each with 1200 CP -> Core team CP = 1200
    mock_db.pokemon_list = [{"level": 30, "stats": {}, "individual_id": str(i)} for i in range(6)]
    ef.calculate_cp_from_dict = lambda p: 1200
    
    mock_db.user_data["ankimon_pity_trackers"] = {k: 0 for k in ef.OVERHAUL_PITY_THRESHOLDS}
    
    ep = ef.calculate_mastery_index_ep(total_reviews=60, daily_average=100, trainer_level=20)
    log(f"Calculated EP: {ep:.4f}% (Expected ~25.00%)")
    
    counts = run_scenario_sim("Scenario B", N=5000)
    
    log("Simulation Spawn Rates (5,000 rolls):")
    passed = True
    errors = []
    
    for tier, count in counts.items():
        rate = (count / 5000) * 100
        log(f"  - {tier}: {rate:.2f}% (Count: {count})")
        
        # Verify level locks
        if tier in ["Legendary", "Mega", "Gmax", "Mythical", "Starter"]:
            if count > 0:
                passed = False
                errors.append(f"Locked tier '{tier}' spawned under level lock thresholds!")
                
    if counts["Ultra"] == 0:
        passed = False
        errors.append("Unlocked Ultra Beast tier failed to spawn any encounters!")
        
    status = "PASS" if passed else "FAIL"
    log(f"Result: {status}")
    if errors:
        for err in errors: log(f"  [ERROR] {err}")
    return passed, counts

# ------------------------------------------------------------------------------
# 3. SCENARIO C: Endgame Master
# ------------------------------------------------------------------------------
def simulate_scenario_c():
    log_header("SCENARIO C: Endgame Master (Level 85 Main, EP ~48)")
    
    mock_pokemon.level = 85  # All locks cleared
    mock_trainer.level = 50  # Maxed Trainer norm (Trainer cap = 50)
    mock_settings.daily_average = 100
    ef.ankimon_tracker_obj.get_total_reviews = lambda: 50  # 50% session progress
    
    # 30% pokedex completion
    mock_db.caught_ids = set(range(1, 31))
    pokedex_data.clear()
    pokedex_data.update({str(i): {"species_id": i, "actual_id": i} for i in range(1, 101)})
    
    # Top 6 average CP = 2000 -> Core Team norm = 12.5% (cap = 16000)
    mock_db.pokemon_list = [{"level": 80, "stats": {}, "individual_id": str(i)} for i in range(6)]
    ef.calculate_cp_from_dict = lambda p: 2000
    
    mock_db.user_data["ankimon_pity_trackers"] = {k: 0 for k in ef.OVERHAUL_PITY_THRESHOLDS}
    
    ep = ef.calculate_mastery_index_ep(total_reviews=50, daily_average=100, trainer_level=50)
    log(f"Calculated EP: {ep:.4f}% (Expected ~48.125%)")
    
    counts = run_scenario_sim("Scenario C", N=5000)
    
    log("Simulation Spawn Rates (5,000 rolls):")
    passed = True
    errors = []
    total_rares = 0
    
    for tier, count in counts.items():
        rate = (count / 5000) * 100
        log(f"  - {tier}: {rate:.2f}% (Count: {count})")
        if tier not in ["Normal", "Baby"]:
            total_rares += count
            
    aggregate_rare_rate = (total_rares / 5000) * 100
    log(f"Aggregate Rare Spawn Rate: {aggregate_rare_rate:.2f}% (Expected under 13% Soft Landing cap)")
    
    if aggregate_rare_rate > 13.0:
        passed = False
        errors.append(f"Aggregate rare spawn economy inflated! Got {aggregate_rare_rate:.2f}% (Max allowed: 13%)")
    elif aggregate_rare_rate < 1.0:
        passed = False
        errors.append("Aggregate rare spawn rate heavily throttled below baseline expectations!")
        
    status = "PASS" if passed else "FAIL"
    log(f"Result: {status}")
    if errors:
        for err in errors: log(f"  [ERROR] {err}")
    return passed, counts

# ------------------------------------------------------------------------------
# 4. SCENARIO D: Pity Tracking & Bad-Luck Protection
# ------------------------------------------------------------------------------
def simulate_scenario_d():
    log_header("SCENARIO D: Pity Tracking & Reset Simulation")
    
    # Establish Endgame Master environment
    mock_pokemon.level = 85
    mock_trainer.level = 50
    ef.ankimon_tracker_obj.get_total_reviews = lambda: 50
    mock_db.caught_ids = set(range(1, 31))
    pokedex_data.clear()
    pokedex_data.update({str(i): {"species_id": i, "actual_id": i} for i in range(1, 101)})
    ef.calculate_cp_from_dict = lambda p: 2000
    
    # Simulate a deep dry spell for Legendary: Counter = 400 reviews (150 above 250 threshold)
    pity_data = {
        "Ultra": 10,
        "Gmax": 20,
        "Starter": 30,
        "Mega": 40,
        "Legendary": 400, # Large dry spell
        "Mythical": 50
    }
    mock_db.user_data["ankimon_pity_trackers"] = pity_data
    
    # Run 5,000 rolls with inflated Legendary pity
    counts = run_scenario_sim("Scenario D (High Pity)", N=5000)
    
    passed = True
    errors = []
    
    legendary_rate = (counts.get("Legendary", 0) / 5000) * 100
    log(f"Legendary Spawn Rate under Pity: {legendary_rate:.2f}% (Normal: ~0.90%)")
    
    if legendary_rate < 1.0:
        passed = False
        errors.append(f"Independent pity multiplier failed to boost Legendary spawn rate! Rate: {legendary_rate:.2f}%")
    else:
        log("PASS: Independent pity counter successfully boosted Legendary spawn rates!")
        
    # --- PITY RESET LOGIC VERIFICATION ---
    ef.get_tier = lambda *args, **kwargs: "Legendary"
    ef.get_all_pokemon_in_tier = lambda tier: [150] # Mewtwo
    ef.search_pokedex_by_id = lambda pid: "mewtwo"
    
    # Run one generation to trigger the pity tracker updates
    res = ef.generate_random_pokemon(85, sys.modules["Ankimon.singletons"].ankimon_tracker_obj)
    log(f"DEBUG: generate_random_pokemon returned name={res[0]}, id={res[1]}, tier={res[14]}")
    
    # Retrieve updated trackers from mock database
    updated_pity = mock_db.get_user_data("ankimon_pity_trackers")
    log("Updated Pity Trackers after Legendary spawn:")
    for tier, p_val in updated_pity.items():
        log(f"  - {tier}: {p_val}")
        
    if updated_pity["Legendary"] != 0:
        passed = False
        errors.append("Legendary pity counter failed to reset to 0 after Legendary spawn!")
    else:
        log("PASS: Legendary pity counter successfully reset to 0!")
        
    if updated_pity["Ultra"] != 11 or updated_pity["Gmax"] != 21:
        passed = False
        errors.append("Other rare pity counters failed to increment by 1!")
    else:
        log("PASS: Non-selected rare pity counters successfully incremented by 1!")
        
    status = "PASS" if passed else "FAIL"
    log(f"Result: {status}")
    if errors:
        for err in errors: log(f"  [ERROR] {err}")
    return passed, counts

# --- RUN LIFECYCLE ---
def test_simulation_suite():
    # Setup conftest stubs to allow proper resolution inside ef
    import types
    _src = Path(base_dir) / "src"
    for _pkg in ("Ankimon", "Ankimon.functions"):
        if _pkg not in sys.modules:
            _mod = types.ModuleType(_pkg)
            _mod.__path__ = [str(_src / _pkg.replace(".", "/"))]
            _mod.__package__ = _pkg
            sys.modules[_pkg] = _mod

    passed_a, _ = simulate_scenario_a()
    passed_b, _ = simulate_scenario_b()
    passed_c, _ = simulate_scenario_c()
    passed_d, _ = simulate_scenario_d()
    
    assert passed_a is True
    assert passed_b is True
    assert passed_c is True
    assert passed_d is True

if __name__ == "__main__":
    log("Starting Encounter Overhaul Simulation Suite...")
    try:
        test_simulation_suite()
        log("\n[SUCCESS] All 4 progression simulation scenarios passed successfully!")
    except AssertionError:
        log("\n[FAILURE] One or more simulation validation assertions failed!")
        sys.exit(1)
