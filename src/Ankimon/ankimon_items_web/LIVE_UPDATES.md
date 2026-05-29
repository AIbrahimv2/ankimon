# Live updates for web screens

How the Ankimon web shell keeps an **open** screen in sync with gameplay without
a manual reload — e.g. the Profile screen updating its cash, caught count,
highest Pokémon, XP bar and "Recently Caught" list as you review.

This document is the contract for that mechanism so it can be reused (a future
**Stats** screen, a live **Team** view, etc.).

---

## TL;DR

A gameplay write site calls one screen-agnostic function:

```python
try:
    from .singletons import notify_stats_changed   # `..singletons` from a subpackage
    notify_stats_changed()
except Exception:
    pass
```

The open shell then refreshes **whichever screen is currently showing**, if that
screen registered a refresher. Adding live updates to a new screen is ~3 small
pieces (a refresher method, a dict entry, a JS receiver) — see
[Add a new live screen](#add-a-new-live-screen).

---

## Data flow

```
 gameplay write site                     singletons.py            shop_obj.py (AnkimonItemsWeb)         <screen>.js
 ───────────────────                     ─────────────            ────────────────────────────         ───────────
 save_caught_pokemon()  ─┐
 trainer_card.gain_xp() ─┼─►  notify_stats_changed()  ─►  refresh_live_screen()                          window.liveRefreshProfile(data)
 battle_loop cash reward ┘     (best-effort, no-op       │   guards: visible? current screen        ┌─►   → re-render everything;
 (…add more here…)             if window missing)        │   loaded? has a refresher?               │      new catches animate in
                                                         │   coalesce → QTimer.singleShot(0)        │
                                                         └─►  _run_live_refresh()                    │
                                                              └─► _live_refreshers[screen]()  ───────┘
                                                                   e.g. _push_profile_live():
                                                                   runJavaScript("window.liveRefreshProfile(<json>)")
```

### The pieces

| Layer | Symbol | Responsibility |
|-------|--------|----------------|
| Write site | (call) | After a stat-changing write, fire `notify_stats_changed()` (deferred import, wrapped in `try/except`). |
| Bridge | `singletons.notify_stats_changed()` | Look up the live shell (`getattr(mw, "items_web_window", None)`), and if `is_alive`, call `win.refresh_live_screen()`. Never creates the window. |
| Shell entry | `AnkimonItemsWeb.refresh_live_screen()` | Guard (visible + current screen loaded + has a refresher), then coalesce and schedule `_run_live_refresh` on the next event-loop turn. |
| Shell dispatch | `AnkimonItemsWeb._live_refreshers` | `{screen: bound method}`. Only listed screens react. |
| Shell push | `AnkimonItemsWeb._push_profile_live()` (etc.) | Build the payload and `runJavaScript("window.liveRefreshX(<json>)")`. |
| Screen JS | `window.liveRefreshProfile(data)` (etc.) | Apply the fresh data to the DOM. |

---

## Why it's cheap (performance)

The hooks are designed so they cost essentially **nothing** unless you're
actually looking at a live screen:

1. **Off-screen = near-free.** When the relevant screen isn't open/visible, the
   whole chain is: a `getattr` on `mw`, an `is_alive()` (one `obj.objectName()`
   call), and a few boolean checks in `refresh_live_screen()` — microseconds.
   During normal review the reviewer is showing, not the shell, so this is the
   usual path.
2. **Coalesced.** Multiple `notify_stats_changed()` calls in the same event-loop
   turn (e.g. a defeat that grants XP *and* a cash reward) collapse into a
   single refresh via `QTimer.singleShot(0, …)` guarded by
   `_live_refresh_pending`.
3. **Deferred.** The refresh runs on the next event-loop turn, after the
   triggering gameplay logic has finished and its DB writes have committed.
4. **Diffed DOM.** `renderRecent` skips the rebuild when the list is unchanged,
   so stat-only refreshes (cash/XP) don't churn the grid or interrupt the
   in-flight "NEW" badge animation.

The only non-trivial work — `get_profile_data()` (~a handful of small DB queries
+ sprite-path resolution + one `runJavaScript`) — happens **only when the screen
is visible and something actually changed**, i.e. at most once per event-loop
turn per gameplay event you're watching. That's imperceptible at human pace.

> Keep payload builders cheap. If a future screen needs an expensive aggregate,
> cache the immutable parts (as `_badge_grid` caches `badges.json` in
> `_badge_defs_cache`) and recompute only what changes.

---

## Rules / gotchas

- **GUI thread only.** `refresh_live_screen()` uses Qt (`QTimer`, `runJavaScript`)
  so call `notify_stats_changed()` from the main/GUI thread (gameplay code
  already runs there).
- **Best-effort, always.** Every call site wraps the import + call in
  `try/except: pass`. A UI failure must never break a catch/defeat/save.
- **Never create the window.** The bridge uses `getattr(mw, "items_web_window",
  None)` + `is_alive` — it must not call `get_items_window()` (that would *open*
  the shell as a side effect of gameplay).
- **Deferred import.** Import inside the function, not at module top:
  `singletons` imports many gameplay modules, so a top-level import from those
  modules back into `singletons` risks a circular import.
- **JS receiver is optional at runtime.** Always guard:
  `if (window.liveRefreshX) window.liveRefreshX(...)` — the screen may be an
  older cached page without the function.

---

## Add a new live screen

Example: a **Stats** screen that should update live.

1. **JS receiver** in `stats.js`:
   ```js
   window.liveRefreshStats = function (data) {
       if (!data) return;
       state.data = data;
       renderStats(data);   // your render; diff lists if you animate them
   };
   ```
2. **Payload pusher** in `AnkimonItemsWeb` (`shop_obj.py`):
   ```python
   def _push_stats_live(self):
       data = self.profile_data.get_stats_data()   # keep this cheap
       js = ("if (window.liveRefreshStats) "
             f"window.liveRefreshStats({json.dumps(data)});")
       self.webview_stats.page().runJavaScript(js)
   ```
3. **Register it** in `__init__`:
   ```python
   self._live_refreshers = {
       SCREEN_PROFILE: self._push_profile_live,
       SCREEN_STATS:   self._push_stats_live,
   }
   ```

That's it — every existing gameplay chokepoint now refreshes the Stats screen
too, with the same guards/coalescing. No write-site changes needed.

## Add a new gameplay trigger

If a new event changes stats (e.g. selling an item, hatching an egg), drop this
at that write site (after the value is persisted):

```python
try:
    from ..singletons import notify_stats_changed   # adjust dots to your depth
    notify_stats_changed()
except Exception:
    pass
```

Current triggers: `functions/encounter_functions.py:save_caught_pokemon`
(catches), `pyobj/trainer_card.py:gain_xp` (XP/level/total XP),
`battle_loop.py` cash-reward block (in-review cash). Stat changes that happen
*inside* a shell screen (shop purchases, team edits) don't need a trigger — you
navigate to see them, which reloads that screen.

## Animating "new" items in a live list

See `renderRecent` in `ankimon_profile_web/profile.js`:

- Each item has a stable key (`id:` + `individual_id`, falling back to a
  content key). A `shownRecentKeys` set tracks what's currently on screen.
- On refresh, only keys **not** previously shown get the entrance class
  (`.just-caught` → CSS `recent-pop` / `recent-ring` / `recent-tag`).
- The initial render passes `animateNew=false` so re-opening the screen doesn't
  spuriously animate.
- `renderRecent` returns early when the ordered key list is unchanged, so the
  badge animation runs uninterrupted across stat-only refreshes.
