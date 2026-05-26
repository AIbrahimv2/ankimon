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

from ..utils import give_item, is_dev_mode
from ..resources import items_path, csv_file_items_cost, csv_file_descriptions
from ..functions.pokedex_functions import find_details_move


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

    @pyqtSlot("QVariant", result="QVariant")
    def saveSettings(self, payload):
        return self._w.handle_save_settings(payload)


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
        self.settings_bridge = SettingsBridge(self)
        self.channel.registerObject("bridge", self.bridge)
        self.channel.registerObject("nav", self.nav)
        self.channel.registerObject("settings", self.settings_bridge)
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
            elif screen == SCREEN_SETTINGS:
                path = self.addon_dir / "ankimon_items_web" / "settings.html"
                title = "Ankimon — Settings"
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
        elif self.current_screen == SCREEN_SETTINGS:
            data = self.get_settings_data()
            js = f"if (window.initializeSettings) window.initializeSettings({json.dumps(data)});"
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
        return self.item_window.dispatch_use(item_name, item_type)

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
                group_def.get("settings", []), key_by_friendly,
                name_map, desc_map, config,
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
                group["subgroups"].append(
                    {
                        "label": sub["label"],
                        "settings": self._serialize_settings_list(
                            sub.get("settings", []),
                            key_by_friendly,
                            name_map,
                            desc_map,
                            config,
                        ),
                    }
                )
            groups.append(group)
        return {"groups": groups, "dev_mode": bool(is_dev_mode())}

    @staticmethod
    def _serialize_chip_group(chip_def, config):
        chips = []
        for key, chip_label in chip_def["keys"]:
            chips.append({
                "key": key,
                "label": chip_label,
                "value": bool(config.get(key, False)),
            })
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

        # Coerce incoming values back to the type of the existing config
        # entry so e.g. an int field doesn't silently become a string.
        for raw_key, raw_val in payload.items():
            key = str(raw_key)
            if key not in config:
                continue
            config[key] = self._coerce_incoming(config[key], raw_val)

        config, adjustments = settings_schema.validate_and_clamp(config)

        try:
            for key, val in config.items():
                settings_obj.set(key, val)
            settings_obj.save_config()
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
        text-input UI doesn't accidentally rewrite an int field as a str."""
        if isinstance(existing, bool):
            return bool(incoming)
        if isinstance(existing, int) and not isinstance(existing, bool):
            try:
                # Allow strings that look like ints; fall through for ranges.
                return int(incoming)
            except (TypeError, ValueError):
                return incoming
        if isinstance(existing, float):
            try:
                return float(incoming)
            except (TypeError, ValueError):
                return incoming
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
