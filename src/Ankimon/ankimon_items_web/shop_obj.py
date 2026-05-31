"""Unified shell window — Items (Mart + Bag) and Ankidex live in one QDialog.

The same QWebEngineView swaps between two screens by changing its URL. No
window close/open flicker; the dropdown switcher in either screen calls back
through QWebChannel to swap content in place.
"""

import json
import random
from datetime import datetime

from aqt import QDialog, QVBoxLayout, QWebEngineView, mw
from aqt.qt import Qt, QUrl, QFrame
from PyQt6.QtCore import QObject, pyqtSlot
from PyQt6.QtGui import QColor
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWidgets import QStackedWidget

import csv

from ..utils import give_item, is_dev_mode
from ..resources import items_path, csv_file_items_cost, csv_file_descriptions
from ..functions.pokedex_functions import (
    find_details_move,
    _load_pokedex_cache,
    check_evolution_by_item,
    return_id_for_item_name,
)
from ..business import calculate_cp_from_dict


SCREEN_ITEMS = "items"
SCREEN_ANKIDEX = "ankidex"
SCREEN_SETTINGS = "settings"


class NavBridge(QObject):
    """Cross-screen navigation — exposed in all shell pages."""

    def __init__(self, window):
        super().__init__()
        self._w = window

    @pyqtSlot()
    def openItems(self):
        self._w.load_screen(SCREEN_ITEMS)

    @pyqtSlot()
    def openAnkidex(self):
        self._w.load_screen(SCREEN_ANKIDEX)

    @pyqtSlot()
    def openSettings(self):
        self._w.load_screen(SCREEN_SETTINGS)


class SettingsBridge(QObject):
    """Settings-screen actions — only meaningful when Settings is loaded."""

    def __init__(self, window):
        super().__init__()
        self._w = window

    @pyqtSlot(result="QVariant")
    def getSettings(self):
        return self._w.get_settings_data()

    # Accept a JSON-encoded string rather than a QVariant dict — PyQt's
    # QVariant → dict auto-unwrap can fail on the first invocation
    # (depending on Qt/PyQt versions), making the first save click error
    # out while later clicks succeed. Round-tripping through JSON removes
    # that ambiguity entirely.
    @pyqtSlot(str, result="QVariant")
    def saveSettings(self, payload_json):
        try:
            payload = json.loads(payload_json) if payload_json else {}
        except (TypeError, ValueError) as e:
            return {"ok": False, "message": f"Invalid payload JSON: {e}"}
        return self._w.handle_save_settings(payload)

    @pyqtSlot(str, result="QVariant")
    def searchPokemon(self, query):
        """Return up to 20 Pokédex entries whose name contains `query`."""
        return self._w.handle_pokemon_search(query)

    @pyqtSlot(result="QVariant")
    def getCaughtPokemon(self):
        """Return list of [{id, name, sprite_url}] for all caught/collected Pokémon."""
        return self._w.handle_get_caught_pokemon()


class ItemsBridge(QObject):
    """Items-screen actions — only meaningful when Items is loaded."""

    def __init__(self, window):
        super().__init__()
        self._w = window

    @pyqtSlot(str, bool, result="QVariant")
    def buy(self, item_name, is_tm):
        result = self._w.handle_buy(item_name, bool(is_tm))
        self._w.push_screen_data()
        return result

    @pyqtSlot(result="QVariant")
    def reroll(self):
        result = self._w.handle_reroll()
        self._w.push_screen_data()
        return result

    @pyqtSlot(bool, result="QVariant")
    def setSkipRerollConfirm(self, skip):
        return self._w.handle_set_skip_reroll_confirm(bool(skip))

    @pyqtSlot(str, result="QVariant")
    def useItem(self, item_name):
        result = self._w.handle_use(item_name)
        self._w.push_screen_data()
        return result

    # In-shell Pokémon picker — replaces the legacy QInputDialog flow for
    # evolution items + held items. JS calls getPokemonChoices() to populate
    # the modal, then useItemOnPokemon() with the chosen individual_id.
    @pyqtSlot(str, result="QVariant")
    def getPokemonChoices(self, item_name=None):
        return self._w.get_pokemon_choices(item_name)

    @pyqtSlot(str, str, result="QVariant")
    def useItemOnPokemon(self, item_name, individual_id):
        result = self._w.handle_use_with_target(item_name, individual_id)
        self._w.push_screen_data()
        return result

    # Back-compat: items.shop.js previously called bridge.openAnkidex; keep
    # it as a passthrough so older cached pages still work.
    @pyqtSlot()
    def openAnkidex(self):
        self._w.load_screen(SCREEN_ANKIDEX)


class AnkimonItemsWeb(QDialog):
    def __init__(self, addon_dir, shop_manager, item_window, ankimon_tracker):
        super().__init__()
        self.addon_dir = addon_dir
        self.shop_manager = shop_manager
        self.item_window = item_window
        self.ankimon_tracker = ankimon_tracker
        self.current_screen = None
        self.setWindowTitle("Ankimon")

        # Disabled WA_TranslucentBackground to prevent heavy window-level repaint
        # flickering under Windows DWM when QWebEngineView re-composes or updates.
        # self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.resize(1180, 720)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        frame = QFrame()
        frame.setContentsMargins(0, 0, 0, 0)
        frame.setFrameStyle(QFrame.Shape.NoFrame)
        frame.setLayout(QVBoxLayout())
        frame.layout().setContentsMargins(0, 0, 0, 0)
        layout.addWidget(frame)

        self.stack = QStackedWidget()
        frame.layout().addWidget(self.stack)

        self.webview_items = QWebEngineView()
        self.webview_ankidex = QWebEngineView()
        self.webview_settings = QWebEngineView()

        for w in (self.webview_items, self.webview_ankidex, self.webview_settings):
            w.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
            w.page().setBackgroundColor(QColor("#0d1117"))
            self.stack.addWidget(w)

        self.bridge = ItemsBridge(self)
        self.nav = NavBridge(self)
        self.settings_bridge = SettingsBridge(self)

        self.channel_items = QWebChannel(self.webview_items)
        self.channel_items.registerObject("bridge", self.bridge)
        self.channel_items.registerObject("nav", self.nav)
        self.channel_items.registerObject("settings", self.settings_bridge)
        self.webview_items.page().setWebChannel(self.channel_items)

        self.channel_ankidex = QWebChannel(self.webview_ankidex)
        self.channel_ankidex.registerObject("bridge", self.bridge)
        self.channel_ankidex.registerObject("nav", self.nav)
        self.channel_ankidex.registerObject("settings", self.settings_bridge)
        self.webview_ankidex.page().setWebChannel(self.channel_ankidex)

        self.channel_settings = QWebChannel(self.webview_settings)
        self.channel_settings.registerObject("bridge", self.bridge)
        self.channel_settings.registerObject("nav", self.nav)
        self.channel_settings.registerObject("settings", self.settings_bridge)
        self.webview_settings.page().setWebChannel(self.channel_settings)

        self.webview_items.loadFinished.connect(
            lambda ok, s=SCREEN_ITEMS: self._on_screen_load_finished(ok, s)
        )
        self.webview_ankidex.loadFinished.connect(
            lambda ok, s=SCREEN_ANKIDEX: self._on_screen_load_finished(ok, s)
        )
        self.webview_settings.loadFinished.connect(
            lambda ok, s=SCREEN_SETTINGS: self._on_screen_load_finished(ok, s)
        )

        self.loaded_screens = set()

        # Boot with Items by default; menu entries can call load_screen()
        # before show() to pick a different initial screen.
        self.load_screen(SCREEN_ITEMS)
        self._restore_geometry()

    # ------------------------------------------------------------------
    # Screen switching
    # ------------------------------------------------------------------
    def load_screen(self, screen):
        def do_load():
            self.current_screen = screen
            if screen == SCREEN_ITEMS:
                title = "Ankimon — Items"
                target_view = self.webview_items
                path = self.addon_dir / "ankimon_items_web" / "shop.html"
            elif screen == SCREEN_ANKIDEX:
                title = "Ankimon — Ankidex"
                target_view = self.webview_ankidex
                path = self.addon_dir / "ankidex" / "ankidex.html"
            elif screen == SCREEN_SETTINGS:
                title = "Ankimon — Settings"
                target_view = self.webview_settings
                path = self.addon_dir / "ankimon_items_web" / "settings.html"
            else:
                return

            self.setWindowTitle(title)
            self.stack.setCurrentWidget(target_view)

            if screen not in self.loaded_screens:
                self.loaded_screens.add(screen)
                target_view.setUrl(QUrl.fromLocalFile(path.as_posix()))
            else:
                self.push_screen_data()

        # Save Ankidex prefs before navigating away
        if self.current_screen == SCREEN_ANKIDEX and screen != SCREEN_ANKIDEX:
            self._save_ankidex_prefs(callback=do_load)
        else:
            do_load()

    def _on_screen_load_finished(self, ok, screen):
        if not ok:
            return
        if self.current_screen == screen:
            self.push_screen_data()

    def push_screen_data(self):
        if self.current_screen == SCREEN_ITEMS:
            data = self.get_inventory_data()
            js = f"if (window.initializeItems) window.initializeItems({json.dumps(data)});"
            self.webview_items.page().runJavaScript(js)
        elif self.current_screen == SCREEN_ANKIDEX:
            data = self._get_ankidex_data()
            js = f"if (window.initializeAnkidex) window.initializeAnkidex({json.dumps(data)});"
            self.webview_ankidex.page().runJavaScript(js)
        elif self.current_screen == SCREEN_SETTINGS:
            data = self.get_settings_data()
            js = f"if (window.initializeSettings) window.initializeSettings({json.dumps(data)});"
            self.webview_settings.page().runJavaScript(js)

    def _get_ankidex_data(self):
        # Reuse the existing Ankidex singleton's data getter — keeps the
        # dex query logic in one place.
        from ..singletons import get_ankidex_window

        ankidex = get_ankidex_window()
        return ankidex.get_ankidex_data()

    def _save_ankidex_prefs(self, callback=None):
        def on_state_ready(state):
            if state and isinstance(state, dict):
                for key, val in state.items():
                    mw.settings_obj.set(f"ankidex.{key}", val)
            if callback:
                callback()

        self.webview_ankidex.page().runJavaScript(
            "if (window.getAnkidexState) window.getAnkidexState();",
            on_state_ready,
        )

    def show(self):
        if self.isMinimized():
            self.showNormal()
        else:
            super().show()
        self.raise_()
        self.activateWindow()

    def _restore_geometry(self):
        import base64
        from PyQt6.QtCore import QByteArray

        try:
            geo = mw.pm.profile.get("ankimon.items_web_window.geometry")
            if geo:
                self.restoreGeometry(QByteArray(base64.b64decode(geo)))
        except Exception:
            pass

    def _save_geometry(self):
        import base64

        try:
            if not self.isMinimized():
                mw.pm.profile["ankimon.items_web_window.geometry"] = base64.b64encode(
                    bytes(self.saveGeometry())
                ).decode()
        except Exception:
            pass

    def closeEvent(self, event):
        if self.current_screen == SCREEN_ANKIDEX:
            self._save_ankidex_prefs()
        self._save_geometry()
        super().closeEvent(event)

    def hideEvent(self, event):
        self._save_geometry()
        super().hideEvent(event)

    def showEvent(self, event):
        # Re-push fresh data on every show (e.g. after buy/use happened
        # while the window was hidden).
        self.push_screen_data()
        super().showEvent(event)

    # Back-compat alias for the bridge methods that still call update_ui_data.
    def update_ui_data(self):
        self.push_screen_data()

    def handle_pokemon_search(self, query: str):
        """Search the Pokédex by name substring. Returns {results: [{id, name}]}."""
        from ..functions.pokedex_functions import _load_pokedex_cache, format_lore_name
        from ..functions import encounter_data

        query = (query or "").strip().lower()
        if len(query) < 2:
            return {"results": []}
        pokedex = _load_pokedex_cache()
        results = []
        for internal_name, data in pokedex.items():
            # Exclude alternate sub-forms of plate/drive/memory switching species to avoid redundancy
            if internal_name.startswith("arceus") and internal_name != "arceus":
                continue
            if internal_name.startswith("silvally") and internal_name != "silvally":
                continue
            if internal_name.startswith("genesect") and internal_name != "genesect":
                continue

            name = data.get("name", internal_name)
            pretty_name = format_lore_name(name)
            if query in name.lower() or query in pretty_name.lower():
                pid = data.get("actual_id") or data.get("species_id")
                if pid and int(pid) > 0:
                    pid_val = int(pid)
                    if pid_val not in encounter_data.UNAVAILABLE:
                        results.append({"id": pid_val, "name": pretty_name})
            if len(results) >= 20:
                break
        results.sort(key=lambda r: r["name"].lower())
        return {"results": results}

    def handle_get_caught_pokemon(self):
        """Get the list of caught/collected Pokémon for the quick-add panel."""
        from ..utils import load_collected_pokemon_ids
        from ..functions.pokedex_functions import _load_pokedex_cache, search_pokedex_by_id, get_pretty_name_for_id

        caught_ids = load_collected_pokemon_ids()
        results = []
        pokedex = _load_pokedex_cache()

        for pid in sorted(list(caught_ids)):
            internal_name = search_pokedex_by_id(pid)
            if internal_name and internal_name != "Pokémon not found":
                pretty_name = get_pretty_name_for_id(pid)
                results.append({
                    "id": int(pid),
                    "name": pretty_name,
                })
        # Sort by name alphabetically
        results.sort(key=lambda r: r["name"].lower())
        return {"results": results}

    def get_inventory_data(self):
        sm = self.shop_manager

        # Today's stock (cached by PokemonShopManager.get_daily_items)
        raw_items = sm.get_daily_items() or []
        raw_tms = sm.get_daily_tms() or []
        sm.todays_daily_items = raw_items
        sm.todays_daily_tms = raw_tms

        shop_index = {}
        for entry in raw_items:
            shop_index[entry["name"]] = {
                "price": int(self._lookup_price(entry["name"]) or 0),
                "is_tm": False,
                "item_type": entry.get("item_type"),
            }
        for entry in raw_tms:
            shop_index[entry["name"]] = {
                "price": int(sm.tm_price or 0),
                "is_tm": True,
                "item_type": entry.get("item_type") or "TM",
            }

        # Player's bag (every owned item)
        owned_rows = []
        try:
            owned_rows = mw.ankimon_db.get_all_items() or []
        except Exception:
            owned_rows = []

        owned_index = {}
        for row in owned_rows:
            name = row.get("item_name") or row.get("name")
            qty = int(row.get("quantity") or 0)
            if not name or qty <= 0:
                continue
            owned_index[name] = {
                "quantity": qty,
                "category_id": row.get("category_id"),
            }

        all_names = sorted(set(shop_index.keys()) | set(owned_index.keys()))

        items = []
        for name in all_names:
            shop_entry = shop_index.get(name)
            owned_entry = owned_index.get(name)
            is_tm = bool(
                (shop_entry or {}).get("is_tm")
                or (owned_entry or {}).get("category_id") == 37
            )
            items.append(
                self._serialize_item(
                    name=name,
                    is_tm=is_tm,
                    in_shop=bool(shop_entry),
                    shop_price=(shop_entry or {}).get("price"),
                    item_type=(shop_entry or {}).get("item_type"),
                    owned_quantity=(owned_entry or {}).get("quantity", 0),
                )
            )

        return {
            "cash": int(sm.get_callback("trainer.cash") or 0),
            "reroll_cost": int(sm.daily_items_reroll_cost or 0),
            "skip_reroll_confirm": self._get_skip_reroll_today(),
            "items": items,
            # pokemon_choices intentionally NOT included — for players with
            # 10k+ captures the payload is multiple MB. JS lazy-fetches via
            # bridge.getPokemonChoices() on first picker open + caches.
        }

    def _get_skip_reroll_today(self):
        # Stored as {"date": "YYYY-MM-DD", "skip": bool}. Treated as False
        # whenever the date doesn't match today, which gives the "reset every
        # day" behavior without needing a separate cleanup pass.
        try:
            data = mw.ankimon_db.get_user_data("shop_skip_reroll_confirm")
        except Exception:
            return False
        if not isinstance(data, dict):
            return False
        if data.get("date") != datetime.now().strftime("%Y-%m-%d"):
            return False
        return bool(data.get("skip"))

    def handle_set_skip_reroll_confirm(self, skip):
        try:
            mw.ankimon_db.set_user_data(
                "shop_skip_reroll_confirm",
                {"date": datetime.now().strftime("%Y-%m-%d"), "skip": bool(skip)},
            )
        except Exception as e:
            return {"ok": False, "message": str(e)}
        return {"ok": True}

    def _serialize_item(
        self, name, is_tm, in_shop, shop_price, item_type, owned_quantity
    ):
        ui_name = name.replace("-", " ").title()
        entry = {
            "name": name,
            "ui_name": ui_name,
            "is_tm": is_tm,
            "in_shop": in_shop,
            "price": int(shop_price) if shop_price is not None else None,
            "owned_quantity": int(owned_quantity or 0),
            "item_type": item_type,
            "category": self._categorize(name, is_tm),
        }

        if is_tm:
            move = find_details_move(name) or {}
            move_type = move.get("type") or "Normal"
            entry["image_url"] = QUrl.fromLocalFile(
                str(items_path / f"Bag_TM_{move_type}_SV_Sprite.png")
            ).toString()
            short_desc = move.get("shortDesc") or ""
            entry["description"] = (
                f"Teaches a compatible Pokémon the move {ui_name}."
                + (f" {short_desc}" if short_desc else "")
            )
            entry["move_type"] = move_type
            entry["move_power"] = self._coerce_int(move.get("basePower"))
            accuracy = move.get("accuracy")
            entry["move_accuracy"] = (
                "—" if accuracy is True else self._coerce_int(accuracy)
            )
            entry["move_pp"] = self._coerce_int(move.get("pp"))
            entry["move_damage_class"] = (move.get("category") or "").title() or None
        else:
            entry["image_url"] = QUrl.fromLocalFile(
                str(items_path / f"{name}.png")
            ).toString()
            entry["description"] = (
                self._lookup_description(name) or f"A useful item: {ui_name}"
            )

        return entry

    def _categorize(self, name, is_tm):
        """Bucket items into the same groups the legacy bag exposed."""
        if is_tm:
            return "tm"
        bag = self.item_window
        if bag is not None:
            if name in getattr(bag, "hp_heal_items", {}):
                return "heal"
            if name in getattr(bag, "fossil_pokemon", {}):
                return "fossil"
            if name in getattr(bag, "pokeball_chances", {}):
                return "pokeball"
            if name in getattr(bag, "evolution_items", set()):
                return "evolution"
        return "other"

    def _lookup_price(self, name):
        entry = self._items_csv.get(name)
        return entry["cost"] if entry else 0

    def _lookup_description(self, name):
        entry = self._items_csv.get(name)
        if not entry:
            return None
        try:
            lang = int(self.shop_manager.settings_obj.get("misc.language") or 9)
        except (TypeError, ValueError):
            lang = 9
        if lang == 14:  # es_latam → fall back to es per legacy behaviour
            lang = 7
        return self._descriptions.get((entry["id"], lang))

    @property
    def _items_csv(self):
        """{identifier: {"id": int, "cost": int}} — items.csv loaded once."""
        cached = getattr(self, "_items_csv_cache", None)
        if cached is not None:
            return cached
        index = {}
        try:
            with open(csv_file_items_cost, mode="r", newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    try:
                        index[row["identifier"]] = {
                            "id": int(row["id"]),
                            "cost": int(row["cost"]),
                        }
                    except (KeyError, ValueError):
                        continue
        except OSError:
            pass
        self._items_csv_cache = index
        return index

    @property
    def _descriptions(self):
        """{(item_id, language_id): flavor_text} — item_flavor_text.csv loaded once."""
        cached = getattr(self, "_descriptions_cache", None)
        if cached is not None:
            return cached
        index = {}
        try:
            with open(csv_file_descriptions, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    try:
                        key = (int(row["item_id"]), int(row["language_id"]))
                    except (KeyError, ValueError):
                        continue
                    # First occurrence wins (legacy get_item_description does the same).
                    index.setdefault(key, row.get("flavor_text"))
        except OSError:
            pass
        self._descriptions_cache = index
        return index

    @staticmethod
    def _coerce_int(value):
        try:
            if value in (None, "", "—"):
                return None
            if isinstance(value, bool):
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------------------------
    # Actions (JS → Python)
    # ------------------------------------------------------------------
    def handle_buy(self, item_name, is_tm):
        item = self._find_serialized(item_name)
        if not item or not item.get("in_shop"):
            return {"ok": False, "message": "Item is not in today's stock."}

        ui_name = item["ui_name"]
        price = int(item.get("price") or 0)
        cash = int(self.shop_manager.get_callback("trainer.cash") or 0)

        if is_tm and item.get("owned_quantity", 0) > 0:
            return {"ok": False, "message": f"{ui_name} is already owned."}
        if cash < price:
            return {"ok": False, "message": "Not enough money."}

        try:
            self.shop_manager.set_callback("trainer.cash", int(cash - price))
            give_item(item_name, item.get("item_type") if is_tm else None)
        except Exception as e:
            self.shop_manager.set_callback("trainer.cash", cash)
            return {"ok": False, "message": f"Purchase failed: {e}"}

        return {"ok": True, "message": f"Bought {ui_name} for {price}¥"}

    def handle_reroll(self):
        sm = self.shop_manager
        cost = int(sm.daily_items_reroll_cost or 0)
        cash = int(sm.get_callback("trainer.cash") or 0)
        if cash < cost:
            return {"ok": False, "message": "Not enough money to reroll."}

        # Compute new stock + write to DB first; only deduct cash once the
        # write succeeds. Otherwise a DB failure could swallow the reroll
        # cost with nothing to show for it.
        from ..pyobj.ankimon_shop import DAILY_ITEMS_POOL

        random.seed()
        # Clamp sample sizes — random.sample raises if asked for more entries
        # than the pool contains, which would crash the bridge call.
        tm_pool = sm.get_tm_pool()
        num_items = min(sm.number_of_daily_items, len(DAILY_ITEMS_POOL))
        num_tms = min(sm.number_of_daily_items, len(tm_pool))
        new_items = random.sample(DAILY_ITEMS_POOL, num_items)
        new_tms = random.sample(tm_pool, num_tms)

        try:
            mw.ankimon_db.set_user_data(
                "todays_shop",
                {
                    "items": new_items,
                    "technical_machines": new_tms,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                },
            )
            sm.todays_daily_items = new_items
            sm.todays_daily_tms = new_tms
            sm.set_callback("trainer.cash", int(cash - cost))
        except Exception as e:
            return {"ok": False, "message": f"Reroll failed: {e}"}

        return {"ok": True, "message": f"Rerolled stock for {cost}¥"}

    def handle_use(self, item_name):
        item = self._find_serialized(item_name)
        if not item:
            return {"ok": False, "message": "Item not found in your bag."}
        if (item.get("owned_quantity") or 0) <= 0:
            return {"ok": False, "message": "You don't own that item."}
        if self.item_window is None:
            return {"ok": False, "message": "Item bag service unavailable."}
        item_type = item.get("item_type") or ("TM" if item.get("is_tm") else None)
        result = self.item_window.dispatch_use(item_name, item_type)
        # Fossils + healing main can change team data (new entry / hp).
        if item.get("category") in ("fossil", "heal"):
            self._invalidate_pokemon_cache()
        return result

    def _invalidate_pokemon_cache(self):
        self._pokemon_choices_cache = None

    def get_pokemon_choices(self, item_name=None):
        """Return the player's Pokémon team for the in-shell picker.

        Enhancements:
        - Calculates CP for each Pokémon.
        - Provides base species ID ('b') for sprite fallbacks.
        - Checks evolution eligibility ('e') if an evolution item is used.
        - Sorts by eligibility (top), then active status, then level, then name.
        - Utilizes an instance cache for base results to maintain O(1) speed
          for repeated opens with non-evolution items.
        """
        # Determine if we need specific eligibility data
        is_evo_item = False
        if item_name:
            # We assume non-TM here; if it was a TM, useItemOnPokemon wouldn't be called.
            is_evo_item = (self._categorize(item_name, False) == "evolution")

        cached = getattr(self, "_pokemon_choices_cache", None)
        # If not an evolution item, we can safely return the base cache (if it exists).
        # This keeps the "Give Item" picker snappy even with 10k+ Pokémon.
        if not is_evo_item and cached is not None:
            return cached

        try:
            pokemons = mw.ankimon_db.get_all_pokemon() or []
        except Exception as e:
            print(f"[Ankimon] get_pokemon_choices: get_all_pokemon failed: {e}")
            return {"choices": []}

        # Active Pokémon's individual_id (so we can flag it in the UI).
        main_individual_id = None
        bag = self.item_window
        if bag is not None and getattr(bag, "main_pokemon", None):
            main_individual_id = getattr(bag.main_pokemon, "individual_id", None)

        pokedex_data = _load_pokedex_cache()
        from ..functions.pokedex_functions import search_pokedex_by_id

        # Pre-fetch the region setting to avoid repeated lookups
        active_region = None
        if hasattr(mw, "settings_obj") and mw.settings_obj:
            active_region = mw.settings_obj.get("misc.active_region")
            if active_region:
                active_region = active_region.strip()

        choices = []
        for data in pokemons:
            if not isinstance(data, dict):
                continue
            individual_id = data.get("individual_id")
            pokedex_id = data.get("id")
            name = data.get("name")
            if not individual_id or not name:
                continue

            nickname = (data.get("nickname") or "").strip()
            held_item = data.get("held_item") or ""
            level = data.get("level")
            shiny = bool(data.get("shiny"))
            is_main = bool(main_individual_id and individual_id == main_individual_id)

            # Resolve internal name using the optimized pokedex index
            internal_name = search_pokedex_by_id(pokedex_id)
            p_details = pokedex_data.get(internal_name)

            # Sprite fallback: get base species_id
            base_id = pokedex_id
            if p_details:
                base_id = p_details.get("species_id") or pokedex_id

            entry = {
                "id": individual_id,
                "p": pokedex_id or 0,
                "b": base_id or 0,
                "n": name,
                "l": int(level) if level is not None else None,
                "cp": calculate_cp_from_dict(data),
            }
            if shiny:
                entry["s"] = 1
            if is_main:
                entry["m"] = 1
            if held_item:
                entry["h"] = held_item
            if nickname and nickname.lower() != (name or "").lower():
                entry["nk"] = nickname

            # Evolution eligibility (Optimized inline to avoid file I/O)
            if is_evo_item and item_name and p_details:
                evo_list = p_details.get("evos")
                if evo_list:
                    for target_evo_name in evo_list:
                        normalized_target = target_evo_name.lower().replace(" ", "").replace("-", "").replace("'", "").replace(".", "").replace(":", "")
                        target_data = pokedex_data.get(normalized_target) or pokedex_data.get(target_evo_name.lower())

                        if target_data and target_data.get("evoType") == "useItem":
                            # required_item is normalized to match the input item_name (e.g. "Fire Stone" -> "fire-stone")
                            required_item = (target_data.get("evoItem") or "").lower().replace(" ", "-")
                            if required_item == item_name:
                                target_region = target_data.get("evoRegion")

                                if target_region:
                                    if active_region and active_region.lower() == target_region.lower():
                                        entry["e"] = 1
                                        break
                                else:
                                    # Standard form is only allowed if there is no regional sibling for this region/method
                                    has_matching_regional_sibling = False
                                    for sibling_name in evo_list:
                                        sib_norm = sibling_name.lower().replace(" ", "").replace("-", "").replace("'", "").replace(".", "").replace(":", "")
                                        sib_data = pokedex_data.get(sib_norm) or pokedex_data.get(sibling_name.lower())
                                        if sib_data and sib_data.get("evoRegion") and active_region and sib_data.get("evoRegion").lower() == active_region.lower():
                                            if sib_data.get("evoType") == target_data.get("evoType") and (sib_data.get("evoItem") or "").lower() == (target_data.get("evoItem") or "").lower():
                                                has_matching_regional_sibling = True
                                                break
                                    if not has_matching_regional_sibling:
                                        entry["e"] = 1
                                        break

            choices.append(entry)

        # Eligible first, then active first, then level (high → low), then alphabetical.
        choices.sort(
            key=lambda c: (
                not c.get("e"),
                not c.get("m"),
                -(c.get("l") or 0),
                (c.get("nk") or c.get("n") or "").lower(),
            )
        )
        result = {"choices": choices}
        # Update the base cache if this was a non-evolution run.
        if not is_evo_item:
            self._pokemon_choices_cache = result
        return result
    def handle_use_with_target(self, item_name, individual_id):
        """Apply an item to a specific Pokémon (chosen via the in-shell
        picker). Bypasses dispatch_use's QInputDialog branches by calling
        the underlying item_window helpers directly with the id."""
        item = self._find_serialized(item_name)
        if not item:
            return {"ok": False, "message": "Item not found in your bag."}
        if (item.get("owned_quantity") or 0) <= 0:
            return {"ok": False, "message": "You don't own that item."}
        if self.item_window is None:
            return {"ok": False, "message": "Item bag service unavailable."}
        if not individual_id:
            return {"ok": False, "message": "No Pokémon selected."}

        bag = self.item_window
        # Either branch below mutates the team (held-item or evolution),
        # so invalidate up front regardless of which path runs.
        self._invalidate_pokemon_cache()
        try:
            if item.get("category") == "evolution":
                # Check_Evo_Item needs the pre-evo's pokedex id to match
                # against the evolution table. Pull it from the proven
                # get_pokemon() API.
                pokemon_data = None
                try:
                    pokemon_data = mw.ankimon_db.get_pokemon(individual_id)
                except Exception as e:
                    print(f"[Ankimon] get_pokemon({individual_id}) failed: {e}")
                pokedex_id = (pokemon_data or {}).get("id")
                if not pokedex_id:
                    return {"ok": False, "message": "Could not look up that Pokémon."}
                bag.Check_Evo_Item(individual_id, pokedex_id, item_name)
                return {"ok": True, "message": ""}

            # Held items (and anything else routed through the give-item
            # flow) — the legacy method already surfaces success/error via
            # log_and_showinfo, so we just return an empty message.
            bag._give_held_item_by_id(individual_id, item_name)
            return {"ok": True, "message": ""}
        except Exception as e:
            return {"ok": False, "message": f"Use failed: {e}"}

    def _find_serialized(self, item_name):
        data = self.get_inventory_data()
        for entry in data["items"]:
            if entry["name"] == item_name:
                return entry
        return None

    # ------------------------------------------------------------------
    # Settings screen
    # ------------------------------------------------------------------
    def get_settings_data(self):
        """Build the schema + current values payload for the Settings screen."""
        from . import settings_schema

        settings_obj = self.shop_manager.settings_obj
        # Refresh config from disk so external edits are picked up.
        try:
            config = settings_obj.load_config()
        except Exception:
            config = settings_obj.config

        name_map = self._load_lang_json("setting_name.json")
        desc_map = self._load_lang_json("setting_description.json")
        # Reverse the friendly_name → key map so we can resolve friendly names
        # from the schema back to their config keys.
        key_by_friendly = {v: k for k, v in name_map.items()}

        groups = []
        for group_def in settings_schema.GROUPS:
            settings = self._serialize_settings_list(
                group_def.get("settings", []),
                key_by_friendly,
                name_map,
                desc_map,
                config,
            )
            # Append a chip-group as one composite setting after the regular
            # settings — keeps it in the same scroll section.
            chip_def = group_def.get("chip_group")
            if chip_def:
                settings.append(self._serialize_chip_group(chip_def, config))
            group = {
                "label": group_def["label"],
                "settings": settings,
                "subgroups": [],
            }
            for sub in group_def.get("subgroups", []):
                sub_settings = self._serialize_settings_list(
                    sub.get("settings", []),
                    key_by_friendly,
                    name_map,
                    desc_map,
                    config,
                )
                sub_chip_def = sub.get("chip_group")
                if sub_chip_def:
                    sub_settings.append(self._serialize_chip_group(sub_chip_def, config))
                group["subgroups"].append(
                    {
                        "label": sub["label"],
                        "settings": sub_settings,
                    }
                )
            groups.append(group)
        return {"groups": groups, "dev_mode": bool(is_dev_mode())}

    @staticmethod
    def _serialize_chip_group(chip_def, config):
        chips = []
        for key, chip_label in chip_def["keys"]:
            chips.append(
                {
                    "key": key,
                    "label": chip_label,
                    "value": bool(config.get(key, False)),
                }
            )
        return {
            "key": "__chips__" + chip_def["label"].lower().replace(" ", "_"),
            "label": chip_def["label"],
            "description": chip_def.get("description", ""),
            "type": "chips",
            "chips": chips,
        }

    def _serialize_settings_list(
        self, friendly_names, key_by_friendly, name_map, desc_map, config
    ):
        out = []
        for friendly in friendly_names:
            key = key_by_friendly.get(friendly)
            if not key or key not in config:
                continue
            out.append(
                self._serialize_setting(
                    key,
                    friendly,
                    name_map,
                    desc_map,
                    config.get(key),
                )
            )
        return out

    @staticmethod
    def _serialize_setting(key, friendly, name_map, desc_map, value):
        from . import settings_schema

        entry = {
            "key": key,
            "label": friendly,
            "description": desc_map.get(key, ""),
            "value": value,
        }

        if key == "battle.auto_catch_wishlist":
            entry["type"] = "wishlist"
            from ..functions.pokedex_functions import get_pretty_name_for_id
            names_dict = {}
            if isinstance(value, list):
                for pid in value:
                    try:
                        pid_int = int(pid)
                        names_dict[pid_int] = get_pretty_name_for_id(pid_int)
                    except Exception:
                        names_dict[pid] = f"#{pid}"
            entry["names"] = names_dict
            return entry
        if key == "misc.active_region":
            entry["type"] = "select"
            entry["options"] = settings_schema.ACTIVE_REGION_OPTIONS
        elif isinstance(value, bool):
            entry["type"] = "boolean"
        elif isinstance(value, int):
            entry["type"] = "int"
        elif isinstance(value, float):
            entry["type"] = "float"
        else:
            entry["type"] = "text"
        return entry

    def _load_lang_json(self, filename):
        import json as _json

        cache_attr = f"_lang_{filename.replace('.', '_')}_cache"
        cached = getattr(self, cache_attr, None)
        if cached is not None:
            return cached
        path = self.addon_dir / "lang" / filename
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = _json.load(f)
        except (OSError, _json.JSONDecodeError):
            data = {}
        setattr(self, cache_attr, data)
        return data

    def handle_save_settings(self, payload):
        """Apply the JS-side payload, run legacy bounds checks, persist."""
        from . import settings_schema

        if not isinstance(payload, dict):
            return {"ok": False, "message": "Invalid payload."}

        settings_obj = self.shop_manager.settings_obj
        try:
            config = settings_obj.load_config()
        except Exception:
            config = dict(settings_obj.config)

        # Snapshot what's on disk so we can skip writes for unchanged keys
        # after clamping (avoids spurious observer notifications).
        original_config = dict(config)

        # Coerce incoming values back to the type of the existing config
        # entry so e.g. an int field doesn't silently become a string.
        try:
            for raw_key, raw_val in payload.items():
                key = str(raw_key)
                if key not in config:
                    continue
                config[key] = self._coerce_incoming(config[key], raw_val)
        except ValueError as e:
            return {"ok": False, "message": f"Validation error: {e}"}

        config, adjustments = settings_schema.validate_and_clamp(config)

        try:
            changed = False
            for key, val in config.items():
                if original_config.get(key) != val:
                    settings_obj.set(key, val)
                    changed = True
            if changed:
                # Settings.save_config(config) requires the dict — passing
                # the fully-merged config persists every key in one write.
                settings_obj.save_config(config)
        except Exception as e:
            return {"ok": False, "message": f"Save failed: {e}"}

        self._refresh_reviewer_hotkeys(config)

        if adjustments:
            return {
                "ok": True,
                "message": "Saved (with adjustments).",
                "adjustments": adjustments,
            }
        return {"ok": True, "message": "Settings saved."}

    @staticmethod
    def _coerce_incoming(existing, incoming):
        """Match the new value's type to the existing config entry so a
        text-input UI doesn't accidentally rewrite an int field as a str.
        Raises ValueError for non-coercible numeric input — caller surfaces
        the failure rather than silently writing garbage to config."""
        if isinstance(existing, list):
            if isinstance(incoming, list):
                # Accept only integer IDs; silently drop anything non-numeric.
                return [int(x) for x in incoming if str(x).lstrip('-').isdigit()]
            return existing  # reject non-list payloads silently
        if isinstance(existing, bool):
            return bool(incoming)
        if isinstance(existing, int) and not isinstance(existing, bool):
            try:
                return int(incoming)
            except (TypeError, ValueError):
                # Range strings (e.g. "1-3" for cards_per_round) pass through;
                # validate_and_clamp's _coerce_cards_per_round normalizes them.
                if isinstance(incoming, str) and "-" in incoming:
                    return incoming
                raise ValueError(f"Expected integer, got {incoming!r}")
        if isinstance(existing, float):
            try:
                return float(incoming)
            except (TypeError, ValueError):
                raise ValueError(f"Expected float, got {incoming!r}")
        if existing is None:
            # active_region accepts None or a string region name
            return incoming if incoming not in ("", None, "None") else None
        return incoming if incoming is None else str(incoming)

    @staticmethod
    def _refresh_reviewer_hotkeys(config):
        try:
            from ..reviewer_ui import setup_reviewer_ui

            setup_reviewer_ui(
                config.get("controls.catch_key", "6"),
                config.get("controls.defeat_key", "5"),
                config.get("controls.pokemon_buttons", True),
                config.get("controls.team_cycle_key", "9"),
            )
        except Exception:
            # Best-effort — settings still saved even if the hook fails.
            pass
