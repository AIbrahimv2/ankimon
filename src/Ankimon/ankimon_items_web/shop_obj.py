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

import csv

from ..utils import give_item
from ..resources import items_path, csv_file_items_cost, csv_file_descriptions
from ..functions.pokedex_functions import find_details_move


SCREEN_ITEMS = "items"
SCREEN_ANKIDEX = "ankidex"


class NavBridge(QObject):
    """Cross-screen navigation — exposed in both Items and Ankidex pages."""

    def __init__(self, window):
        super().__init__()
        self._w = window

    @pyqtSlot()
    def openItems(self):
        self._w.load_screen(SCREEN_ITEMS)

    @pyqtSlot()
    def openAnkidex(self):
        self._w.load_screen(SCREEN_ANKIDEX)


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

    @pyqtSlot(str, result="QVariant")
    def useItem(self, item_name):
        result = self._w.handle_use(item_name)
        self._w.push_screen_data()
        return result

    # In-shell Pokémon picker — replaces the legacy QInputDialog flow for
    # evolution items + held items. JS calls getPokemonChoices() to populate
    # the modal, then useItemOnPokemon() with the chosen individual_id.
    @pyqtSlot(result="QVariant")
    def getPokemonChoices(self):
        return self._w.get_pokemon_choices()

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

        self.webview = QWebEngineView()
        # Suppress the QtWebEngine browser-style right-click menu (Inspect,
        # Reload, etc.) — irrelevant noise in a game UI.
        self.webview.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        # Paint the underlying webview page dark so the user doesn't see a
        # white flash between window-show and HTML/CSS first paint.
        self.webview.page().setBackgroundColor(QColor("#0d1117"))
        frame.layout().addWidget(self.webview)

        self.channel = QWebChannel(self.webview)
        self.bridge = ItemsBridge(self)
        self.nav = NavBridge(self)
        self.channel.registerObject("bridge", self.bridge)
        self.channel.registerObject("nav", self.nav)
        self.webview.page().setWebChannel(self.channel)

        self.webview.loadFinished.connect(self._on_load_finished)

        # Boot with Items by default; menu entries can call load_screen()
        # before show() to pick a different initial screen.
        self.load_screen(SCREEN_ITEMS)

    # ------------------------------------------------------------------
    # Screen switching
    # ------------------------------------------------------------------
    def load_screen(self, screen):
        def do_load():
            self.current_screen = screen
            if screen == SCREEN_ITEMS:
                path = self.addon_dir / "ankimon_items_web" / "shop.html"
                title = "Ankimon — Items"
            elif screen == SCREEN_ANKIDEX:
                path = self.addon_dir / "ankidex" / "ankidex.html"
                title = "Ankimon — Ankidex"
            else:
                return
            self.setWindowTitle(title)
            self.webview.setUrl(QUrl.fromLocalFile(path.as_posix()))

        # Save Ankidex prefs before navigating away — defer the URL change
        # until the async getAnkidexState() callback fires, otherwise the JS
        # context tears down before prefs are read.
        if self.current_screen == SCREEN_ANKIDEX and screen != SCREEN_ANKIDEX:
            self._save_ankidex_prefs(callback=do_load)
        else:
            do_load()

    def _on_load_finished(self, ok):
        if not ok:
            return
        self.push_screen_data()

    def push_screen_data(self):
        if self.current_screen == SCREEN_ITEMS:
            data = self.get_inventory_data()
            js = f"if (window.initializeItems) window.initializeItems({json.dumps(data)});"
        elif self.current_screen == SCREEN_ANKIDEX:
            data = self._get_ankidex_data()
            js = f"if (window.initializeAnkidex) window.initializeAnkidex({json.dumps(data)});"
        else:
            return
        self.webview.page().runJavaScript(js)

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

        self.webview.page().runJavaScript(
            "if (window.getAnkidexState) window.getAnkidexState();",
            on_state_ready,
        )

    def closeEvent(self, event):
        if self.current_screen == SCREEN_ANKIDEX:
            self._save_ankidex_prefs()
        super().closeEvent(event)

    def showEvent(self, event):
        # Re-push fresh data on every show (e.g. after buy/use happened
        # while the window was hidden).
        self.push_screen_data()
        super().showEvent(event)

    # Back-compat alias for the bridge methods that still call update_ui_data.
    def update_ui_data(self):
        self.push_screen_data()

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
            "items": items,
            # pokemon_choices intentionally NOT included — for players with
            # 10k+ captures the payload is multiple MB. JS lazy-fetches via
            # bridge.getPokemonChoices() on first picker open + caches.
        }

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
        new_items = random.sample(DAILY_ITEMS_POOL, sm.number_of_daily_items)
        new_tms = random.sample(sm.get_tm_pool(), sm.number_of_daily_items)

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

    def get_pokemon_choices(self):
        """Return the player's Pokémon team for the in-shell picker — name,
        nickname, level, id. Replaces the QInputDialog flow for evolution
        items and held items.

        Cached on the instance — `get_all_pokemon()` JSON-parses every
        captured row, which costs hundreds of ms for players with 10k+
        captures. Buy/reroll don't change the team, so they reuse the
        cache; team-mutating actions call `_invalidate_pokemon_cache()`.
        """
        cached = getattr(self, "_pokemon_choices_cache", None)
        if cached is not None:
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

        choices = []
        for data in pokemons:
            if not isinstance(data, dict):
                continue
            individual_id = data.get("individual_id")
            pokedex_id = data.get("id")
            name = data.get("name")
            if not individual_id or not name:
                # No id or no name means we can't display or address it —
                # but pokedex_id == 0 / missing is fine (we just fall back
                # to a placeholder sprite).
                continue

            nickname = (data.get("nickname") or "").strip()
            held_item = data.get("held_item") or ""
            level = data.get("level")
            shiny = bool(data.get("shiny"))
            is_main = bool(main_individual_id and individual_id == main_individual_id)

            # Per-entry payload is intentionally minimal — for players with
            # 10k+ captures, every extra byte multiplies into MB of IPC.
            # JS reconstructs the sprite URL from pokedex_id; nickname is
            # only shipped when it actually differs from the species name.
            entry = {
                "id": individual_id,
                "p": pokedex_id or 0,
                "n": name,
                "l": int(level) if level is not None else None,
            }
            if shiny:
                entry["s"] = 1
            if is_main:
                entry["m"] = 1
            if held_item:
                entry["h"] = held_item
            if nickname and nickname.lower() != (name or "").lower():
                entry["nk"] = nickname
            choices.append(entry)

        # Active first, then by level (high → low), then alphabetical.
        choices.sort(
            key=lambda c: (
                not c.get("m"),
                -(c.get("l") or 0),
                (c.get("nk") or c.get("n") or "").lower(),
            )
        )
        result = {"choices": choices}
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
