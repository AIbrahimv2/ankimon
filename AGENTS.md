# Ankimon — Agent & Contributor Guide

## What is Ankimon?

A Pokemon game addon for [Anki](https://apps.ankiweb.net/) — the spaced repetition flashcard app. Every card review triggers a Pokemon battle. You catch, evolve, and collect Pokemon while studying.

The addon runs inside Anki's Python/Qt environment. `aqt` is Anki's module, `mw` is the main window singleton.

## Repository Structure

```
src/Ankimon/              # The Anki addon (symlinked to addons21/ for dev)
  __init__.py             # Entry point (~175 lines) — imports, wiring, hook registration
  battle_loop.py          # Core battle loop (on_review_card), BattleState dataclass
  card_hooks.py           # Card timer + answer quality tracking hooks
  changelog.py            # GitHub changelog fetch + update notification
  discord_integration.py  # Discord Rich Presence hooks
  hook_registry.py        # Catch/defeat hook system for external integrations
  profile_hooks.py        # Profile lifecycle: tip of the day, monthly pokemon, sync
  reviewer_ui.py          # Reviewer shortcut keys + bottom bar buttons
  startup.py              # Boot sequence: backup, migration, assets, first enemy
  singletons.py           # All singleton objects (settings, pokemon, tracker, etc.)
  resources.py            # File paths, constants, version detection
  business.py             # CP calculation, experience formulas
  functions/              # Game logic functions (encounters, battles, badges, etc.)
  pyobj/                  # Qt dialog classes (settings, shop, PC box, evolution, etc.)
  gui_classes/            # More UI classes (pokemon details, team view, etc.)
  poke_engine/            # Battle simulation engine (from ArdentRoe/poke-engine)
  user_files/             # User data directory (gitignored — DB, sprites, saves)
    sprites/              # Pokemon sprites (gitignored, downloaded on first run)
    ankimon.db            # SQLite database (all user data post-migration)
tests/                    # Test suite
```

## Architecture

### Data Flow

1. User reviews a card in Anki
2. `card_hooks.py` tracks timing and answer quality
3. `battle_loop.py` runs the battle (calls poke-engine)
4. `encounter_functions.py` handles catch/defeat/level-up
5. `reviewer_obj.py` updates the HUD via JavaScript injection

### Key Singletons (singletons.py)

- `main_pokemon` / `enemy_pokemon` — PokemonObject instances
- `settings_obj` — Settings loaded from DB or config.obf
- `ankimon_tracker_obj` — Tracks reviews, battles, multipliers
- `ankimon_db` — AnkimonDB (SQLite database manager)
- `trainer_card` — Player profile (level, cash, badges)

### Data Storage

All user data is in SQLite (`user_files/ankimon.db`). The `database_manager.py` handles all DB operations. Legacy JSON files are migrated on first run via `migration_dialog.py`.

Key tables: `captured_pokemon`, `items`, `badges`, `team`, `pokemon_history`, `metadata`

## Running Tests

```bash
# Install dependencies (once)
pip install pytest pytest-qt PyQt6 markdown

# Run all tests
python -m pytest tests/ -v

# Run just the integrity test (imports every module)
python -m pytest tests/test_addon_integrity.py -v
```

All tests should pass. The integrity test dynamically imports every module to catch ImportError/AttributeError at load time.

## Running Anki for Manual Testing

```bash
# Using the anki-vscode dev setup:
<PATH_TO_ANKI_EXECUTABLE> -b "<PATH_TO_ANKI_PROFILE>"

# Quick 20-second smoke test:
timeout 20 <PATH_TO_ANKI_EXECUTABLE> -b "<PATH_TO_ANKI_PROFILE>" 2>&1 || true
```

Clean startup should show: `AnkimonDB: Database schema initialized.` and `Ankimon Startup.` with no tracebacks.

## Making Changes

### Rules

- Run `pytest tests/` after every change. All tests must pass.
- Run the Anki smoke test for anything touching startup, imports, or singletons.
- Never modify user data files (anything gitignored).
- The `__init__.py` is a thin orchestrator — add new logic to the appropriate extracted module, not to init.
- `singletons.py` instantiates objects — don't add logic there.
- Imports from `poke_engine/` should only happen via `functions/ankimon_hooks_to_poke_engine.py` (the bridge file). The engine itself has zero ankimon imports.

### PR Workflow

- Every change goes through a PR, even small fixes. No direct pushes to main.
- PRs from external contributors: push adapted code to their branch if `maintainerCanModify` is true, then merge their PR so they get credit.
- Reference the original issue/PR number in commit messages: `fix: nickname bug (#361)`

### Common Pitfalls

- `aqt` and `anki` modules are only available inside Anki runtime. Tests must mock them.
- Qt widgets can only be created/accessed on the main thread.
- `settings_obj.get()` is called live everywhere — values are not cached at startup.
- `poke_engine/` contains the battle simulation engine. Only `functions/ankimon_hooks_to_poke_engine.py` bridges it to ankimon — the engine itself has zero ankimon imports.
- Sprites are gitignored and downloaded on first run. Source of truth: `h0tp-ftw/ankimon-sprites` repo.
- The `user_files/` directory is for runtime data. Never commit files there.

### Test Integrity Ignore List

The integrity test skips these modules (they require full Anki runtime):
- `Ankimon.singletons` (StopIteration from mock Qt widgets)
- `Ankimon.pyobj.tip_of_the_day` (uses `from aqt.qt import *` at class level)
- `Ankimon.poke_engine.tests.*` / `Ankimon.poke_engine.setup` (upstream test files)

If you add a new module that crashes during import without Anki, add it to `ignore_modules` in `test_addon_integrity.py` AND explain why.

## External Repos

- `h0tp-ftw/ankimon-sprites` — Sprite assets. GitHub Action auto-builds ZIP + syncs to HuggingFace.
- `ArdentRoe/poke-engine` — Battle simulation engine used as a submodule.
- `h0tp-ftw/anki-vscode` — Dev environment setup for running Anki with debugger.
