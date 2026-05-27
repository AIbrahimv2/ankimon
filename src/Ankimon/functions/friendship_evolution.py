"""Friendship- and time-of-day-based evolution helpers.

This module is the single source of truth for:
- the in-game day/night clock (derived from the local system clock + settings),
- which friendship evolution(s) a species can undergo,
- whether a given Pokémon is *ready* to evolve via friendship right now, and
- triggering that evolution through the existing :class:`EvoWindow`.

Friendship evolutions in the bundled data (``pokemon_evolution.csv``) are encoded
as ``evolution_trigger_id == 1`` (level-up) rows that carry a positive
``minimum_happiness`` and, for some species, a ``time_of_day`` of ``"day"`` or
``"night"`` (e.g. Eevee -> Espeon by day / Umbreon at night). The legacy
level-up evolution code skips these because they have a blank ``minimum_level``.

Circular-import note
--------------------
This module is imported (directly or transitively) by ``pc_box.py``,
``encounter_functions.py``, ``trainer_functions.py`` and ``pokemon_details.py``.
``singletons.py`` imports ``pc_box`` at module top level *before* it binds the
``settings_obj`` singleton, so importing ``settings_obj`` at this module's top
level would crash at addon load. Therefore ``settings_obj`` is imported lazily,
inside each function that needs it, by which point ``singletons`` is fully
initialised. The ``pokedex_functions`` / ``resources`` imports below have no such
back-edge and are safe at top level.
"""

from __future__ import annotations

import functools
from datetime import datetime, timedelta, timezone
from typing import Any, NamedTuple, Optional

from .pokedex_functions import (
    pokemon_evolves_from_id,
    return_name_for_id,
    rows_for_key_in_table,
)
from ..resources import poke_evo_path

# Reference value for friendship progress bars: the bar reads "full" at this
# value, and it's the fallback bar denominator for species with no friendship
# evolution. NOTE: friendship is NOT capped here — it keeps climbing past 400 as
# a flex stat (the bar just stays full; the raw number is what grows).
MAX_FRIENDSHIP = 400


class FriendshipEvolution(NamedTuple):
    """An immutable description of a single friendship-based evolution.

    Instances are produced by :func:`get_friendship_evolutions_for_species` and
    cached for the lifetime of the process. Being a ``NamedTuple`` they are
    hashable and immutable, so cached tuples can be shared freely across callers
    (``pc_box``, ``pokemon_details``, the battle flow) with no mutation risk.

    Attributes:
        evo_id: National Pokédex id of the evolved species.
        evo_name: Capitalised display name of the evolved species.
        min_happiness: Friendship value required to evolve.
        time_of_day: ``"day"``, ``"night"``, or ``None`` if the evolution has no
            time-of-day requirement.
    """

    evo_id: int
    evo_name: str
    min_happiness: int
    time_of_day: Optional[str]


class LevelEvolution(NamedTuple):
    """An immutable description of a single level-up evolution.

    Counterpart to :class:`FriendshipEvolution` for plain level-up evolutions
    (``evolution_trigger_id == 1`` rows that carry a positive ``minimum_level``
    and *no* friendship requirement). Produced by
    :func:`get_level_evolutions_for_species` and cached for the lifetime of the
    process. Friendship evolutions are deliberately excluded here so the two
    helpers never double-count the same row.

    Attributes:
        evo_id: National Pokédex id of the evolved species.
        evo_name: Capitalised display name of the evolved species.
        min_level: Level required to evolve.
        time_of_day: ``"day"``, ``"night"``, or ``None`` if not time-gated.
    """

    evo_id: int
    evo_name: str
    min_level: int
    time_of_day: Optional[str] = None


def _now_in_configured_tz() -> datetime:
    """Return the current time in the user's configured time zone.

    Auto-detect mode (the default) uses *this device's* local time zone via
    ``datetime.now()`` — so the day/night cycle follows the system clock with no
    setup. When ``evolution.timezone_auto`` is turned off, a fixed UTC offset
    (``evolution.timezone_offset``, in hours) is applied instead. Only the
    resulting wall-clock hour/time is consumed by the day/night logic.
    """
    from ..singletons import settings_obj  # lazy: avoids load-time circular import

    if settings_obj.get("evolution.timezone_auto", True):
        return datetime.now()
    try:
        offset = float(settings_obj.get("evolution.timezone_offset", 0.0))
    except (TypeError, ValueError):
        offset = 0.0
    offset = max(-14.0, min(14.0, offset))  # clamp to the valid UTC range
    return datetime.now(timezone(timedelta(hours=offset)))


def _format_utc_offset(offset: float) -> str:
    """Format a UTC offset in hours, e.g. ``UTC+5:30`` / ``UTC-5`` / ``UTC+0``."""
    sign = "-" if offset < 0 else "+"
    hours, minutes = divmod(int(round(abs(offset) * 60)), 60)
    return f"UTC{sign}{hours}:{minutes:02d}" if minutes else f"UTC{sign}{hours}"


def _coerce_hour(value: Any, default: int) -> int:
    """Coerce a configured day/night boundary hour to a sane ``int``.

    The day/night bounds live in advanced config that isn't surfaced in the
    settings UI, so a hand-edited or migrated config can hand us a string
    (``"6"``), ``None``, or junk. Comparing those against an integer hour would
    raise :class:`TypeError` on the hot PC-render path, so we coerce to ``int``
    (falling back to ``default``) and clamp to ``0-23``.
    """
    try:
        hour = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, min(23, hour))


def _coerce_int(value: Any, default: int) -> int:
    """Coerce a Pokémon stat (friendship / level) to an ``int``.

    A Pokémon dict assembled from the SQLite store can carry these as strings —
    ``json_extract`` returns whatever JSON type was persisted, and trades /
    imports / migrations can stash ``friendship`` or ``level`` as a JSON string
    (``"160"``). Arithmetic and comparisons against the integer thresholds would
    otherwise raise :class:`TypeError`, so we coerce here and fall back to
    ``default`` for ``None`` / non-numeric junk. Floats truncate toward zero,
    matching ``int()``.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_time_of_day(now: Optional[datetime] = None) -> str:
    """Return the current in-game time of day as ``"day"`` or ``"night"``.

    The day window is ``[day_start_hour, night_start_hour)``; everything else is
    night. With the defaults (6, 18) this means 06:00-17:59 is day and
    18:00-05:59 is night, so "night" naturally spans midnight. The clock used is
    the device's local time by default, or a fixed UTC offset when the user
    disables auto-detect (see :func:`_now_in_configured_tz`). The boundary hours
    are coerced/clamped defensively (see :func:`_coerce_hour`); a misconfigured
    ``day_start_hour >= night_start_hour`` simply yields an empty day window
    (always "night") rather than raising.

    Args:
        now: Optional :class:`datetime` to evaluate against. When omitted, the
            user's configured time zone is used. Useful for testing.

    Returns:
        ``"day"`` or ``"night"``.
    """
    from ..singletons import settings_obj  # lazy: avoids load-time circular import

    moment = now if now is not None else _now_in_configured_tz()
    hour = moment.hour
    day_start = _coerce_hour(settings_obj.get("evolution.day_start_hour", 6), 6)
    night_start = _coerce_hour(settings_obj.get("evolution.night_start_hour", 18), 18)
    return "day" if day_start <= hour < night_start else "night"


def current_time_label(now: Optional[datetime] = None) -> str:
    """Return a human-readable label for the current time of day.

    Examples:
        ``"☀️ Day · 09:12"`` or, with a manual time zone,
        ``"🌙 Night · 21:34 · UTC-5"``.

    Args:
        now: Optional :class:`datetime`. When omitted, the user's configured
            time zone is used.

    Returns:
        A short, emoji-prefixed label including the current ``HH:MM`` time (and
        the UTC offset when a manual time zone is configured).
    """
    from ..singletons import settings_obj  # lazy: avoids load-time circular import

    moment = now if now is not None else _now_in_configured_tz()
    tod = get_time_of_day(moment)
    icon = "☀️ Day" if tod == "day" else "🌙 Night"
    label = f"{icon} · {moment.strftime('%H:%M')}"
    if not settings_obj.get("evolution.timezone_auto", True):
        try:
            offset = float(settings_obj.get("evolution.timezone_offset", 0.0))
            label += f" · {_format_utc_offset(offset)}"
        except (TypeError, ValueError):
            pass
    return label


def _is_plain_level_row(row: dict) -> bool:
    """Return ``True`` if a CSV row is a plain level-up evolution.

    A "plain level-up" row has ``evolution_trigger_id == 1``, a positive
    ``minimum_level`` and *no* friendship requirement (blank/zero
    ``minimum_happiness``). It is used to detect evolved species that are already
    reachable by levelling up, so the friendship helper can leave those to the
    level path (see :func:`get_friendship_evolutions_for_species`).
    """
    try:
        if int(row.get("evolution_trigger_id", 0)) != 1:
            return False
    except (TypeError, ValueError):
        return False
    try:
        if int(row.get("minimum_happiness", "") or 0) > 0:
            return False
    except (TypeError, ValueError):
        pass
    try:
        return int(row.get("minimum_level", "")) > 0
    except (TypeError, ValueError):
        return False


@functools.lru_cache(maxsize=None)
def get_friendship_evolutions_for_species(
    pokemon_id: int,
) -> tuple[FriendshipEvolution, ...]:
    """Return all friendship evolutions for a species, sorted by evolved id.
    Prioritizes pokedex.json for regional forms.
    """
    from .pokedex_functions import _load_pokedex_cache, search_pokedex_by_id, safe_int
    
    evolutions: list[FriendshipEvolution] = []
    
    # 1. PRIORITY CHECK: Form-aware evolution from pokedex.json
    pokedex_data = _load_pokedex_cache()
    internal_name = search_pokedex_by_id(pokemon_id)
    
    if internal_name in pokedex_data:
        details = pokedex_data[internal_name]
        evo_list = details.get("evos")
        
        if evo_list:
            for target_evo_name in evo_list:
                normalized_target = target_evo_name.lower().replace(" ", "").replace("-", "").replace("'", "")
                target_data = pokedex_data.get(normalized_target) or pokedex_data.get(target_evo_name.lower())
                
                if target_data:
                    evo_type = target_data.get("evoType")
                    if evo_type == "levelFriendship":
                        target_id = safe_int(target_data.get("actual_id") or target_data.get("species_id"))
                        # Smogon JSON doesn't specify an exact number; use legacy default or 220
                        # Check evoCondition for time of day if present
                        condition = (target_data.get("evoCondition") or "").lower()
                        time_of_day = None
                        if "day" in condition:
                            time_of_day = "day"
                        elif "night" in condition:
                            time_of_day = "night"
                            
                        if target_id > 0:
                            evolutions.append(
                                FriendshipEvolution(
                                    evo_id=target_id,
                                    evo_name=target_data.get("name", target_evo_name),
                                    min_happiness=220, # Default high friendship threshold
                                    time_of_day=time_of_day,
                                )
                            )
            
            if evolutions:
                return tuple(evolutions)

    # 2. LEGACY FALLBACK: Species CSV lookup
    for evo in pokemon_evolves_from_id(pokemon_id):
        # An evolved species can have several rows (one per evolution method), so
        # scan them all and keep the one carrying a positive minimum_happiness.
        # check_key_in_table's first-match would miss e.g. Sylveon, whose blank
        # row precedes its friendship row in the CSV.
        rows = rows_for_key_in_table("evolved_species_id", evo, poke_evo_path)
        # If this evolved species is also reachable by levelling up, leave it to
        # the level path instead of offering a friendship evolution. The bundled
        # CSV carries no Pokémon *form* data, so it conflates e.g. Kantonian
        # Meowth (level 28) and Alolan Meowth (friendship) onto the same evolved
        # id (Persian); preferring friendship there would silently change a
        # classic level-up evolution. Scoping friendship evolution to species
        # that evolve *purely* by friendship (Eevee, Golbat, Pichu, Riolu, ...)
        # keeps the feature focused and leaves existing level evolutions intact.
        if any(_is_plain_level_row(r) for r in rows):
            continue
        for row in rows:
            try:
                min_happiness = int(row.get("minimum_happiness", ""))
            except (TypeError, ValueError):
                continue
            if min_happiness <= 0:
                continue

            time_raw = (row.get("time_of_day") or "").strip().lower()
            time_of_day = time_raw if time_raw in ("day", "night") else None

            name = return_name_for_id(int(evo))
            evo_name = name.capitalize() if name else str(evo)

            evolutions.append(
                FriendshipEvolution(
                    evo_id=int(evo),
                    evo_name=evo_name,
                    min_happiness=min_happiness,
                    time_of_day=time_of_day,
                )
            )
            break  # one friendship row per evolved species is enough

    evolutions.sort(key=lambda e: e.evo_id)
    return tuple(evolutions)


@functools.lru_cache(maxsize=None)
def get_level_evolutions_for_species(
    pokemon_id: int,
) -> tuple[LevelEvolution, ...]:
    """Return all plain level-up evolutions for a species, sorted by evolved id.
    Prioritizes pokedex.json for regional forms.
    """
    from .pokedex_functions import _load_pokedex_cache, search_pokedex_by_id, safe_int
    
    evolutions: list[LevelEvolution] = []
    
    # 1. PRIORITY CHECK: Form-aware evolution from pokedex.json
    pokedex_data = _load_pokedex_cache()
    internal_name = search_pokedex_by_id(pokemon_id)
    
    if internal_name in pokedex_data:
        details = pokedex_data[internal_name]
        evo_list = details.get("evos")
        
        if evo_list:
            for target_evo_name in evo_list:
                normalized_target = target_evo_name.lower().replace(" ", "").replace("-", "").replace("'", "")
                target_data = pokedex_data.get(normalized_target) or pokedex_data.get(target_evo_name.lower())
                
                if target_data:
                    # In Smogon-style pokedex.json, evoLevel is stored on the evolved species
                    target_id = safe_int(target_data.get("actual_id") or target_data.get("species_id"))
                    min_level = safe_int(target_data.get("evoLevel"))
                    
                    if target_id > 0 and min_level > 0:
                        # Extract time of day if present in evoCondition
                        condition = (target_data.get("evoCondition") or "").lower()
                        time_of_day = None
                        if "day" in condition:
                            time_of_day = "day"
                        elif "night" in condition:
                            time_of_day = "night"

                        evolutions.append(
                            LevelEvolution(
                                evo_id=target_id,
                                evo_name=target_data.get("name", target_evo_name),
                                min_level=min_level,
                                time_of_day=time_of_day,
                            )
                        )
            
            if evolutions:
                return tuple(evolutions)

    # 2. LEGACY FALLBACK: Species CSV lookup
    for evo in pokemon_evolves_from_id(pokemon_id):
        # Scan every row for this evolved species and keep the first that is a
        # plain level-up row. An evolved species may carry several method rows
        # (e.g. a level-up row *and* a friendship row), so first-match would pick
        # the wrong one when the level row isn't listed first.
        for row in rows_for_key_in_table("evolved_species_id", evo, poke_evo_path):
            # Level-up trigger only (item/trade/etc. evolutions are out of scope).
            try:
                trigger_id = int(row.get("evolution_trigger_id", 0))
            except (TypeError, ValueError):
                continue
            if trigger_id != 1:
                continue

            # Exclude friendship evolutions — those are handled by the friendship
            # helper and must not be double-counted here.
            try:
                min_happiness = int(row.get("minimum_happiness", "") or 0)
            except (TypeError, ValueError):
                min_happiness = 0
            if min_happiness > 0:
                continue

            try:
                min_level = int(row.get("minimum_level", ""))
            except (TypeError, ValueError):
                continue
            if min_level <= 0:
                continue

            time_raw = (row.get("time_of_day") or "").strip().lower()
            time_of_day = time_raw if time_raw in ("day", "night") else None

            name = return_name_for_id(int(evo))
            evo_name = name.capitalize() if name else str(evo)

            evolutions.append(
                LevelEvolution(
                    evo_id=int(evo),
                    evo_name=evo_name,
                    min_level=min_level,
                    time_of_day=time_of_day,
                )
            )
            break  # one level-up row per evolved species is enough

    evolutions.sort(key=lambda e: e.evo_id)
    return tuple(evolutions)


def _select_evolution(
    evos: tuple[FriendshipEvolution, ...], tod: str
) -> FriendshipEvolution:
    """Pick the most appropriate friendship evolution for the current time.

    Precedence among the available evolutions:
      1. Prefer one eligible *right now* (``time_of_day == tod`` or no time
         requirement); within those, prefer an explicitly time-gated row over a
         blank-time row, then lowest ``evo_id``.
      2. If none is eligible right now, fall back to a representative (lowest
         ``evo_id``) so the UI can still show e.g. "waiting for Night".

    Args:
        evos: Non-empty tuple from :func:`get_friendship_evolutions_for_species`.
        tod: Current time of day (``"day"`` or ``"night"``).

    Returns:
        The chosen :class:`FriendshipEvolution`.
    """
    eligible_now = [e for e in evos if e.time_of_day in (tod, None)]
    if eligible_now:
        # Prefer explicit-time rows (e.g. Espeon@day) over blank-time rows, then
        # lowest evo_id. ``time_of_day is None`` sorts last via the bool key.
        return min(eligible_now, key=lambda e: (e.time_of_day is None, e.evo_id))
    # Nothing matches the current time; still return a representative.
    return min(evos, key=lambda e: e.evo_id)


def evolution_readiness(pokemon: Any, now: Optional[datetime] = None) -> dict:
    """Compute manual-evolution readiness for a single Pokémon.

    Covers both **friendship/time** evolutions and plain **level-up**
    evolutions, so the PC's manual "Evolve now" button and ✨ badge light up for
    either kind. Friendship evolutions take precedence (``method="friendship"``);
    if the species has none, a level-up evolution is considered instead
    (``method="level"``). Accepts either a dict or an object exposing ``id``,
    ``friendship``, ``everstone`` and ``level`` attributes; missing values
    default to ``friendship=0``, ``everstone=False`` and ``level=1``.

    Args:
        pokemon: A Pokémon dict or object.
        now: Optional :class:`datetime` for the time-of-day check.

    Returns:
        A dict with the keys::

            evolvable, ready, method, evo_id, evo_name, min_happiness,
            current_friendship, friendship_remaining, required_time, time_ok,
            status_text, bar_max

        For a friendship evolution ``method`` is ``"friendship"``; for a
        level-up evolution it is ``"level"`` (with ``min_happiness=None``,
        ``required_time=None``, ``time_ok=True``, ``friendship_remaining=0`` and
        ``bar_max`` :data:`MAX_FRIENDSHIP`). For a species with no evolution of
        either kind, ``evolvable`` is ``False``, ``method`` is ``None``,
        ``bar_max`` is :data:`MAX_FRIENDSHIP` and ``status_text`` is empty.
    """
    if isinstance(pokemon, dict):
        pid = pokemon.get("id")
        friendship = _coerce_int(pokemon.get("friendship", 0), 0)
        everstone = pokemon.get("everstone", False)
        evolution_rejected = pokemon.get("evolution_rejected", False)
        level = _coerce_int(pokemon.get("level", 1), 1)
    else:
        pid = getattr(pokemon, "id", None)
        friendship = _coerce_int(getattr(pokemon, "friendship", 0), 0)
        everstone = getattr(pokemon, "everstone", False)
        evolution_rejected = getattr(pokemon, "evolution_rejected", False)
        level = _coerce_int(getattr(pokemon, "level", 1), 1)

    tod = get_time_of_day(now)

    not_evolvable = {
        "evolvable": False,
        "ready": False,
        "method": None,
        "evo_id": None,
        "evo_name": None,
        "min_happiness": None,
        "current_friendship": friendship,
        "friendship_remaining": 0,
        "required_time": None,
        "time_ok": True,
        "status_text": "",
        "bar_max": MAX_FRIENDSHIP,
        "rejected": False,
    }

    if pid is None:
        return not_evolvable
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        # A malformed/non-numeric id can't be matched against the integer CSV
        # ids; treat it like a missing id rather than raising on the hot path.
        return not_evolvable

    evos = get_friendship_evolutions_for_species(pid)
    if not evos:
        # No friendship evolution — fall back to a plain level-up evolution so
        # the manual "Evolve now" path covers level evolvers too (auto level-ups
        # are still handled by check_evolution_for_pokemon; this is for mons that
        # rejected, hold an Everstone, or were caught above their evolve level).
        return _level_readiness(
            pid=pid,
            level=level,
            everstone=everstone,
            friendship=friendship,
            evolution_rejected=evolution_rejected,
            not_evolvable=not_evolvable,
            tod=tod,
        )

    chosen = _select_evolution(evos, tod)
    evo_id = chosen.evo_id
    evo_name = chosen.evo_name
    min_happiness = chosen.min_happiness
    required_time = chosen.time_of_day

    friendship_remaining = max(0, min_happiness - friendship)
    time_ok = required_time is None or required_time == tod
    ready = (not everstone) and friendship >= min_happiness and time_ok

    status_text = _build_status_text(
        everstone=everstone,
        ready=ready,
        evo_name=evo_name,
        friendship_remaining=friendship_remaining,
        required_time=required_time,
        time_ok=time_ok,
        tod=tod,
        rejected=evolution_rejected,
    )

    return {
        "evolvable": True,
        "ready": ready,
        "method": "friendship",
        "evo_id": evo_id,
        "evo_name": evo_name,
        "min_happiness": min_happiness,
        "current_friendship": friendship,
        "friendship_remaining": friendship_remaining,
        "required_time": required_time,
        "time_ok": time_ok,
        "status_text": status_text,
        "bar_max": min_happiness,
        "rejected": evolution_rejected,
    }


def _level_readiness(
    *,
    pid: int,
    level: int,
    everstone: bool,
    friendship: int,
    evolution_rejected: bool,
    not_evolvable: dict,
    tod: str,
) -> dict:
    """Compute readiness for a plain level-up evolution.

    Called by :func:`evolution_readiness` only when the species has no
    friendship evolution. Returns ``not_evolvable`` unchanged when the species
    has no level-up evolution either, so the no-evo case stays identical.

    Readiness ignores ``evolution_rejected`` (so the manual button still shows
    for rejected mons) but DOES enforce ``required_time``/time-of-day.
    ``ready = (not everstone) and level >= min_level and time_ok``.

    Args:
        pid: National Pokédex species id (already coerced to ``int``).
        level: The Pokémon's current level.
        everstone: Whether the Pokémon holds an Everstone.
        friendship: Current friendship value (carried through for the bar/UI).
        evolution_rejected: Whether the user previously rejected this evolution.
        not_evolvable: The pre-built "no evolution" result dict to return when
            there is no level-up evolution.
        tod: Current time of day (``"day"`` or ``"night"``).

    Returns:
        A readiness dict with ``method="level"`` (or ``not_evolvable``).
    """
    level_evos = get_level_evolutions_for_species(pid)
    if not level_evos:
        return not_evolvable

    # Filter based on active region
    active_region = None
    try:
        from aqt import mw
        if hasattr(mw, "settings_obj") and mw.settings_obj:
            active_region = mw.settings_obj.get("misc.active_region")
            if active_region:
                active_region = active_region.strip()
    except Exception:
        pass
    
    if active_region in ("No Region", ""):
        active_region = None

    from .pokedex_functions import _load_pokedex_cache, search_pokedex_by_id
    pokedex_data = _load_pokedex_cache()

    filtered_evos = []
    for e in level_evos:
        target_name = search_pokedex_by_id(e.evo_id)
        if target_name in pokedex_data:
            target_data = pokedex_data[target_name]
            target_region = target_data.get("evoRegion")
            
            if target_region:
                if active_region and active_region.lower() == target_region.lower():
                    filtered_evos.append(e)
            else:
                has_matching_regional_sibling = False
                for other_e in level_evos:
                    other_name = search_pokedex_by_id(other_e.evo_id)
                    if other_name in pokedex_data:
                        other_data = pokedex_data[other_name]
                        other_region = other_data.get("evoRegion")
                        if other_region and active_region and active_region.lower() == other_region.lower():
                            has_matching_regional_sibling = True
                            break
                if not has_matching_regional_sibling:
                    filtered_evos.append(e)
                    
    if filtered_evos:
        level_evos = filtered_evos

    # If there are time-gated evolutions, prefer the one that matches current time
    eligible_now = [e for e in level_evos if e.time_of_day in (tod, None)]
    if eligible_now:
        chosen = min(eligible_now, key=lambda e: (e.time_of_day is None, e.evo_id))
    else:
        chosen = min(level_evos, key=lambda e: e.evo_id)

    evo_name = chosen.evo_name
    min_level = chosen.min_level
    required_time = chosen.time_of_day

    time_ok = required_time is None or required_time == tod
    ready = (not everstone) and level >= min_level and time_ok

    if everstone:
        status_text = "Everstone prevents evolution"
    elif ready and evolution_rejected:
        status_text = "Evolution rejected — tap Evolve now to override"
    elif ready:
        status_text = f"Ready to evolve into {evo_name}!"
    elif level >= min_level and not time_ok:
        status_text = f"Ready — waiting for {required_time.capitalize()} (now {tod.capitalize()})"
    else:
        text = f"Evolves into {evo_name} at Lv{min_level}"
        if required_time is not None:
            text += f" · needs {required_time.capitalize()}"
        status_text = text

    return {
        "evolvable": True,
        "ready": ready,
        "method": "level",
        "evo_id": chosen.evo_id,
        "evo_name": evo_name,
        "min_happiness": None,
        "current_friendship": friendship,
        "friendship_remaining": 0,
        "required_time": required_time,
        "time_ok": time_ok,
        "status_text": status_text,
        "bar_max": MAX_FRIENDSHIP,
        "rejected": evolution_rejected,
    }


def _build_status_text(
    *,
    everstone: bool,
    ready: bool,
    evo_name: str,
    friendship_remaining: int,
    required_time: Optional[str],
    time_ok: bool,
    tod: str,
    rejected: bool = False,
) -> str:
    """Build the human-readable readiness line shown in the UI.

    Examples:
        - ``"Everstone prevents evolution"``
        - ``"Evolution rejected — tap Evolve now to override"``
        - ``"Ready to evolve into Espeon!"``
        - ``"Ready — waiting for Night (now Day)"``
        - ``"40 friendship to evolve into Espeon · needs Day"``
    """
    if everstone:
        return "Everstone prevents evolution"

    if ready and rejected:
        return "Evolution rejected — tap Evolve now to override"

    if ready:
        return f"Ready to evolve into {evo_name}!"

    # Friendship is high enough but the time of day is wrong.
    if friendship_remaining == 0 and not time_ok and required_time is not None:
        return (
            f"Ready — waiting for {required_time.capitalize()} "
            f"(now {tod.capitalize()})"
        )

    # Still needs more friendship.
    text = f"{friendship_remaining} friendship to evolve into {evo_name}"
    if required_time is not None:
        text += f" · needs {required_time.capitalize()}"
    return text


def check_friendship_evolution_for_pokemon(
    individual_id,
    pokemon_id,
    evo_window,
    everstone: bool = False,
    friendship: int = 0,
    evolution_rejected: bool = False,
    now: Optional[datetime] = None,
) -> Optional[int]:
    """Prompt a friendship evolution for a Pokémon if it is ready.

    Honors the global ``evolution.friendship_time_enabled`` toggle and the
    Everstone item. When the Pokémon is ready, opens the evolution window via
    :meth:`EvoWindow.ask_pokemon_evo` and returns the evolved species id.

    Args:
        individual_id: The individual (instance) id of the Pokémon.
        pokemon_id: National Pokédex species id of the Pokémon.
        evo_window: The shared :class:`EvoWindow` used to confirm evolution.
        everstone: Whether the Pokémon holds an Everstone. Defaults to ``False``.
        friendship: Current friendship value. Defaults to ``0``.
        evolution_rejected: Whether the user previously rejected this evolution.
            When ``True`` the automatic prompt is suppressed (the manual
            "Evolve now" button stays available elsewhere). Defaults to ``False``.
        now: Optional :class:`datetime` for the time-of-day check.

    Returns:
        The evolved species id if the evolution was triggered, else ``None``.
    """
    from ..singletons import settings_obj  # lazy: avoids load-time circular import

    if (
        not settings_obj.get("evolution.friendship_time_enabled", True)
        or everstone
        or evolution_rejected
    ):
        return None

    shim = {"id": pokemon_id, "friendship": friendship, "everstone": everstone}
    readiness = evolution_readiness(shim, now)
    # Only the friendship path auto-prompts here. Level-up evolutions are
    # auto-handled by check_evolution_for_pokemon (pokedex_functions.py); a
    # level-ready Pokémon surfaced by evolution_readiness must NOT be auto-
    # prompted by this friendship checker (the manual PC button still covers it).
    if readiness["method"] == "friendship" and readiness["ready"]:
        evo_window.ask_pokemon_evo(individual_id, pokemon_id, readiness["evo_id"])
        return readiness["evo_id"]
    return None
