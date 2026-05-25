# Ankimon Experimental (BRRRR_Experimental) Analysis Report

This report provides a comprehensive analysis of the features, architectural changes, and improvements in the `BRRRR_Experimental` branch of the Ankimon repository compared to the `main` branch.

## 1. Performance & Memory Optimization

The most significant architectural improvement in this branch is the transition from high-latency file I/O and redundant database queries to an aggressive **in-memory caching system**. This results in nearly zero lag across the application.

### Comprehensive Data Caching

- **File I/O Elimination**: `learnsets.json`, `pokedex.json`, and `next_lvl.csv` (experience tables) are now cached in memory to eliminate disk reads during move selection and level-up processing.
- **CSV Memory Mapping**: Heavy CSV files (`pokemon.csv`, `stats.csv`, `pokemon_species.csv`, `evolution.csv`) are cached as dictionary structures.
- **HUD Performance**: Implemented sprite caching in the reviewer to drastically speed up HUD rendering during battles.
- **Fast ID Indexing**: A reverse index (`species_id` -> `pokemon_name`) is built at startup for $O(1)$ lookups.

### PC Box Query Optimization

- **Results Caching**: The PC Box caches the results of the last filtered query. Navigating between boxes (paging) or selecting different Pokémon no longer triggers a new SQLite query unless the filter state changes.
- **Filter State Tracking**: Balances performance with data accuracy by intelligently invalidating the cache only when necessary.

### Asynchronous & Thread-Safe Startup Sequence (Zero-Lag Boot)

- **QueryOp Thread Offloading**: Offloaded all disk and CPU-intensive boot tasks (generating/validating database backups, verifying folder structures for sprites and assets, querying item statistics, and generating the first wild enemy Pokémon) to an asynchronous background thread using Anki's `QueryOp` to completely eliminate startup freeze/lag.
- **Responsive UI Deferral**: Deferred Ankimon menu creation, profileLoaded database hooks, and singletons wiring until the background loading thread successfully completes.
- **Robust Client Guards**: Placed thread guards on reviewer shortcuts, battle loops, and custom reviewer bottom bar layout to revert gracefully to safe fallbacks or native bars while loading.
- **Thread-Safe DB Connection**: Configured SQLite connections with `check_same_thread=False` to securely permit read and write operations across background and main thread boundaries.

---

## 2. Major UI/UX Overhaul

### Ankidex (Pokédex V2)

The legacy Pokédex system has been replaced with **Ankidex**, a high-performance, web-based implementation.

- **Tech Stack**: HTML5, CSS3 (Glassmorphism), and Vanilla JavaScript integrated via QtWebEngine.
- **Features**: Faster loading, improved search, and support for regional/special forms.

### PC Box (mini) Rework

- **Persistent Details Panel**: Prevents UI flickering by reusing widgets and animating transitions.
- **Fluid Animations**: Smooth fade-ins for headers, sliding bar animations for stats, and hover lift effects for slots.
- **Friendship Bar Relocation**: Moved the Friendship bar from the top header to a dedicated animated row in the Stats tab (directly below XP) for a cleaner, unified UI.
- **Manual Evolution Button**: Integrated a "Manual Evolution" button directly into the PC details panel, allowing users to evolve Pokémon instantly when readiness criteria are met. Ported from [scotej's PR #445](https://github.com/h0tp-ftw/ankimon/pull/445) and optimized for the current architecture.
- **Maximized Window Stability**: Refactored the details panel to use a persistent `QStackedWidget`, fixing a legacy Qt layout issue where selecting a Pokémon while maximized would cause the window to restore/un-maximize.
- **Nature Indicators**: Added Nature indicators (▲/▼) to stat labels to indicate the 10% boost or reduction from the Pokémon's Nature.(Also implemented nature randomization for captured Pokémon)
- **Advanced Sorting**: Added sorting by all individual stats (HP, Atk, Def, etc.), CP, IV Total, and EV Total.
- **Move Manager Integration**: A new window to Manage Pokémon moves `MoveManagerWidget`.

### HUD Portal for Reviewer

The reviewer interface received a "HUD Portal" upgrade for better injection and management of battle elements.

---

## 3. Advanced Battle & Collection Logic

### Manual Evolution & Readiness

- **Ported Evolution Logic**: Ported the comprehensive manual evolution system from [scotej's PR #445](https://github.com/h0tp-ftw/ankimon/pull/445).
- **Evolution Hub**: The PC Box now acts as the primary hub for triggering evolutions that were previously rejected or missed during level-up.
- **UI Refresh**: Implemented automatic cache invalidation and sprite refreshing to ensure evolved Pokémon are reflected instantly in the PC grid.
- **Form-Aware Evolution**: Both auto-evolution (post-battle) and manual evolution (PC Box) now prioritize `pokedex.json` metadata over legacy CSVs. This fully supports evolution paths for regional forms (e.g., Alolan Geodude -> Alolan Graveler).
- **Time-of-Day Enforcement**: Level-up evolutions now strictly respect time-of-day constraints (day/night) parsed from `pokedex.json` or CSVs. The PC Box displays dynamic status text (e.g., "waiting for Night") when the level is met but the time is wrong.

### Rare & Level-Gated Encounters

- **Mega & Gigantamax**: Restored and stabilized. These now require the user to have encountered the **base form** first, creating a more realistic progression.
- **Starter Families**: Implemented as rare level-gated encounters with a strict prerequisite chain (e.g., you cannot encounter Charmeleon until you have caught Charmander).
- **Legendary & Mythical Chains**: Gen I-III legendaries use their original `encounters.txt` prerequisite chains. Similar logic has been applied to Gen IV-IX legendaries and mythicals.

### Regional Forms & Region Selection

- **Region Menu**: A new setting allows users to select a specific Pokémon region.
- **Dynamic Odds**: Depending on the selected region, certain Pokémon generations are boosted with a higher chance of appearance.

### Auto-Catching

- **Settings Toggle**: Added a setting to automatically catch rare Pokémon regardless of whether "Automatic Battle" is enabled, ensuring valuable encounters aren't lost.

### Implementing EV-yield modifying Items

- **Macho Brace**: Doubles the EV yield of defeated Pokémon.
- **Power Items (Power Anklet, Power Band, etc.)**: Adds a flat +8 EVs to the yield for a specific stat.

---

## 4. Enhanced Trading System (Trade V2)

The trade system has been modernized with protocol versioning and enhanced data transmission.

- **Protocol Versioning (v02)**: Implemented a versioning system (sentinel `-200`) to ensure data integrity and prevent version mismatches.
- **Nature Support**: Pokémon Natures are now transmitted in trade codes. Legacy codes automatically default to a "Serious" nature.
- **Legacy Support**: Added a "Legacy Mode" to generate old-format codes, ensuring backward compatibility with older software versions.
- **Canonicalization**: Improved verification logic to normalize trade codes and reduce manual entry errors.

---

## 5. Developer & Power-User Tools

### Hidden Developer Mode Trigger

Developer features are now dynamically enabled at runtime without modifying code. To activate developer mode, name your Anki Profile or Trainer in the settings to include a certain string (Ask BRRRRR if you wanna know haha).

### Account & Database Switcher (Hidden Dev Feature)

Toggle seamlessly between save profiles (different `.db` files) to test features without impacting main account progression. This menu action is visible only when Developer Mode is active.

### Add-on Reloader (Hidden Dev Feature)

A dedicated menu button for hot-reloading code. This eliminates the need to restart Anki for every code change, significantly accelerating development and testing. This menu action is visible only when Developer Mode is active.

### Test Encounter Shortcut (Hidden Dev Feature)

- **Hotkey '0'**: Triggers a new Pokémon encounter immediately during cards review. Only registered and active when Developer Mode is active.

### Team Cycling

- **Hotkey '9'**: Instantly swap between the top 3 team members during battle while clearing buffs/debuffs.

---

## 6. Architectural & Data Improvements

### Fixes & Fallbacks

- **Generational Fallback**: A progressive move lookup system (Gen 9 → Gen 1) to handle incomplete data, specifically for newer additions like Ultra Beasts.
- **Sprite Fallbacks**: Improved naming logic and back-sprite fallbacks for special forms to prevent "MissingNo" errors.
- **Reward Balancing**: Configurable cash reward amounts and payout intervals.

### Massive Data Update

- **Updated `pokedex.json`**: Enhanced with some metadata and actual IDs for special variants.

---

## 7. Automatic Update Notifications & Snooze System

A modern startup check and installation system designed specifically to keep users on the experimental branch up-to-date with remote changes.

- **Startup Delta Checks**: Queries the GitHub API in a silent background thread at startup to compare local and remote commits on the `BRRRR_Experimental` branch.
- **Sandbox & Offline Resiliency**: Bypasses fragile synchronous network connectivity pre-checks, ensuring branch update checks run completely asynchronously in the background. This prevents startup blocking and ensures prompts trigger even in restricted packaged sandboxes like `AnkiTEST`.
- **Unconditional User Data Protection**: The installer unconditionally protects all files under `user_files/` (such as SQLite `.db`, `.db-shm`, `.db-wal` databases, local backups, and custom downloaded sprites) and critical root files (`HelpInfos.html`, `updateinfos.md`, `meta.json`). This guarantees updates never corrupt or delete user progress.
- **Premium 3-Tab Update Dialog Interface**: The manual "Check for Updates" menu option has been redesigned into a highly responsive, multi-tabbed dashboard:
  - **Tab 1: BRRRR_Experimental Branch** (Automatically opened by default): Displays the active branch name, currently installed commit SHA, author/committer date (fetched dynamically via GitHub API), the local last-update installation timestamp, real-time sync status, a weekly snooze checkbox, and a scrollable `QTextBrowser` commit feed of what's new. Includes a primary update button for one-click asynchronous branch updates.
  - **Tab 2: Releases**: Provides a fast dropdown list and direct release installer for public experimental releases.
  - **Tab 3: Developer**: Allows power users to lazy-load and install directly from other branches, tags, or specific open Pull Requests asynchronously.
- **Safe Installation Logging**: Fixed state persistence to record the actual current time in `installed_at` upon successful update, instead of keeping the old cached file modification date.
- **Commit Logs Feed**: Displays commit messages and titles inside a scrollable `QTextBrowser` styled dynamically for both Anki light and dark night modes.
- **Weekly Snooze Option**: A checkbox allows users to snooze update checks and prompts for exactly 1 week, saving the snooze timestamp cleanly in `update_state.json`.
- **Locked-Files Bypass Safety**: Gracefully bypasses Windows permission locks on static assets (such as loaded `.ttf` fonts like `Early GameBoy.ttf`) by displaying a non-fatal warning and successfully installing code updates.
- **Simplified Menu Interface**: Action renamed to **Check for Updates** under `Ankimon => Help` for standard UX naming.

---

## 8. Summary of Key Files Changed

| File                                           | Primary Change                                                |
| ---------------------------------------------- | ------------------------------------------------------------- |
| `src/Ankimon/ankidex/`                         | **New** web-based Pokedex system.                             |
| `src/Ankimon/pyobj/pc_box.py`                  | Complete overhaul of the PC interface and caching.            |
| `src/Ankimon/pyobj/pokemon_trade.py`           | **New** Trade V2 logic, versioning, and legacy support.       |
| `src/Ankimon/reloader.py`                      | **New** hot-reload logic.                                     |
| `src/Ankimon/functions/encounter_functions.py` | Prerequisite chains, level-gating, and region-boost logic.    |
| `src/Ankimon/singletons.py`                    | Account switching and lazy-loading support.                   |
| `src/Ankimon/pyobj/settings.py`                | Region selection, reward balancing, and auto-catch settings.  |
| `src/Ankimon/pyobj/update_manager.py`          | **New** updater state, locked-file safety, and commit fetch.  |
| `src/Ankimon/pyobj/update_dialog.py`           | **New** update available modal, snooze box, and progress bar. |
| `src/Ankimon/changelog.py`                     | **New** background startup update check query logic.          |
| `src/Ankimon/startup.py`                      | **New** split of boot sequence into asynchronous QueryOp background checks and main-thread UI callbacks. |
| `src/Ankimon/__init__.py`                     | **New** asynchronous and thread-safe startup registration and deferred client-side hooks wiring. |

---

_Analysis completed based on repository state as of May 24, 2026, incorporating developer-provided feature documentation._
