import sys
import importlib
import os
from aqt import mw, gui_hooks
from aqt.qt import *
from aqt.utils import tooltip

def restart_ankimon():
    """Main entry point to restart the addon."""
    try:
        # Get the addon package name (e.g., '1908235722')
        addon_package = __name__.split('.')[0]
        
        # 1. Teardown current state
        teardown_ankimon(addon_package)
        
        # 2. Clear modules from sys.modules
        # We need to be careful to remove all submodules
        modules_to_remove = [name for name in sys.modules if name.startswith(addon_package)]
        for name in modules_to_remove:
            del sys.modules[name]
            
        # 3. Re-import the main module
        importlib.import_module(addon_package)
        
        tooltip("Ankimon restarted successfully!")
        
    except Exception as e:
        import traceback
        error_msg = f"Error during Ankimon restart: {e}\n{traceback.format_exc()}"
        print(error_msg)
        tooltip("Failed to restart Ankimon. See console for details.")

def teardown_ankimon(addon_package):
    """Cleans up hooks, menus, and windows."""
    
    # --- 1. Unregister GUI Hooks ---
    # Iterate through all gui_hooks and remove handlers from this addon
    for attr_name in dir(gui_hooks):
        attr = getattr(gui_hooks, attr_name)
        
        # Determine handlers list
        handlers = []
        if hasattr(attr, "_handlers"):
            handlers = list(attr._handlers)
        elif isinstance(attr, list):
            handlers = list(attr)
        else:
            continue

        for handler in handlers:
            # Check if it's a module-level function or a method
            handler_module = getattr(handler, "__module__", "")
            
            # For methods, the module is on the function itself
            if not handler_module and hasattr(handler, "__func__"):
                handler_module = getattr(handler.__func__, "__module__", "")

            if handler_module and handler_module.startswith(addon_package):
                try:
                    if hasattr(attr, "remove"):
                        attr.remove(handler)
                    elif isinstance(attr, list):
                        attr.remove(handler)
                    print(f"Ankimon Reloader: Removed hook {attr_name} -> {handler}")
                except Exception as e:
                    print(f"Ankimon Reloader: Failed to remove hook {attr_name}: {e}")

    # --- 2. Remove Menu ---
    if hasattr(mw, "pokemenu"):
        mw.form.menubar.removeAction(mw.pokemenu.menuAction())
        # Also remove from mw to avoid dangling references
        delattr(mw, "pokemenu")

    # --- 3. Close Windows ---
    # List of known singleton window attributes on mw
    windows_on_mw = [
        "test_window", "item_window", "pokemon_pc", "settings_ankimon",
        "trainer_card", "ankimon_tracker_window", "reviewer_obj",
        # Unified Items/Mart/Ankidex shell. Must be torn down too, or a
        # reload reuses the old QWebEngineView (and its already-loaded
        # shop.js/shop.html), so web-asset changes never take effect.
        "items_web_window",
    ]
    for attr in windows_on_mw:
        if hasattr(mw, attr):
            obj = getattr(mw, attr)
            if hasattr(obj, "close"):
                try:
                    obj.close()
                except:
                    pass
            # Also handle instances that might be QDialogs or QWidgets directly
            if isinstance(obj, QWidget):
                obj.deleteLater()
            delattr(mw, attr)

    # Close any other leftover widgets from this addon
    for widget in QApplication.allWidgets():
        if widget.__class__.__module__.startswith(addon_package):
            widget.close()
            widget.deleteLater()

    # --- 4. Restore Wrapped Methods (Reviewer) ---
    from aqt.reviewer import Reviewer
    if hasattr(Reviewer, "_ankimon_orig_shortcutKeys"):
        Reviewer._shortcutKeys = Reviewer._ankimon_orig_shortcutKeys
        delattr(Reviewer, "_ankimon_orig_shortcutKeys")
    
    if hasattr(Reviewer, "_ankimon_orig_linkHandler"):
        Reviewer._linkHandler = Reviewer._ankimon_orig_linkHandler
        delattr(Reviewer, "_ankimon_orig_linkHandler")
        
    if hasattr(Reviewer, "_ankimon_orig_bottomHTML"):
        Reviewer._bottomHTML = Reviewer._ankimon_orig_bottomHTML
        delattr(Reviewer, "_ankimon_orig_bottomHTML")

    # --- 5. Remove other mw attributes (UI ONLY) ---
    # We DO NOT remove: logger, settings_obj, ankimon_db, ankimon_tracker_obj, main_pokemon, enemy_pokemon
    # because we want these to persist across reloads (Reload-safe singletons).
    pass
