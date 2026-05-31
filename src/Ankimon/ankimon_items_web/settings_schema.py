"""Settings schema + validation for the web settings screen.

Mirrors the hierarchical structure of the legacy QMainWindow settings_window.py
so users see the same groups in the same order, but exposed as data so the
web shell can render it.
"""

# Two-level group structure. Each group has a friendly-name list of settings
# (matched against lang/setting_name.json) and optional subgroups.
GROUPS = [
    {
        "label": "General",
        "settings": [
            "Trainer Name",
            "Language",
            "Show Tip of the Day On Startup",
        ],
        "subgroups": [
            {
                "label": "Technical Settings",
                "settings": [
                    "SSH Access",
                    "Prevent Ankimon News on Startup",
                    "AnkiWeb Sync",
                    "Ankimon Leaderboard",
                    "Developer Mode",
                ],
            },
            {
                "label": "Discord Integration",
                "settings": [
                    "Discord Rich Presence - Ankimon",
                    "Discord Rich Presence - Quote Type",
                ],
            },
        ],
    },
    {
        "label": "Battle",
        "settings": [
            "Cards per Round",
            "Show Main Pokémon in Reviewer",
            "Hide HUD on Reviewer Startup",
            "Show Pokémon Buttons",
            "Pop-Up on Defeat",
            "Show Text Message Box in Reviewer",
            "Message Box Display Time",
            "Review Based Damage",
            "Auto-detect Time Zone",
            "Time Zone UTC Offset",
        ],
        "subgroups": [
            {
                "label": "Auto-Battle Rules",
                "settings": [
                    "Automatic Battle",
                    "Always Catch Wishlist",
                ],
                "chip_group": {
                    "label": "Always Catch Tiers",
                    "description": (
                        "In automatic battle mode, Pokémon of these tiers are always caught "
                        "regardless of your collection status or mode setting. "
                        "Shiny Pokémon are always caught automatically."
                    ),
                    "keys": [
                        ("battle.auto_catch_legendary", "Legendary"),
                        ("battle.auto_catch_mythical",  "Mythical"),
                        ("battle.auto_catch_ultra",     "Ultra Beast"),
                        ("battle.auto_catch_starter",   "Starter"),
                        ("battle.auto_catch_mega",      "Mega"),
                        ("battle.auto_catch_gmax",      "Gigantamax"),
                        ("battle.auto_catch_regional",  "Regional Form"),
                    ],
                },
            },
            {
                "label": "Fight Hotkeys",
                "settings": [
                    "Key for Defeat",
                    "Key for Catching",
                    "Key for Team Cycling",
                    "Key for Opening/Closing Ankimon",
                    "Allow Choosing Moves",
                ],
            },
            {
                "label": "HP, XP and Level Settings",
                "settings": [
                    "HP Bar Configuration",
                    "XP Bar Configuration",
                    "XP Bar Location",
                    "Remove Level Cap",
                ],
            },
        ],
    },
    {
        "label": "Styling",
        "settings": [
            "Styling in Reviewer",
            "Team Overview in Deck Overview",
            "Animate Time",
            "HP Bar Thickness",
            "Reviewer Image as GIF",
            "View Main Pokémon Front",
            "Show GIFs in Collection",
        ],
    },
    {
        "label": "Sound",
        "settings": [
            "Enable Sound Effects",
            "Enable Sounds",
            "Enable Battle Sounds",
            "Volume",
        ],
    },
    {
        "label": "Study",
        "settings": [
            "Goal of Daily Average Cards",
            "Card Max Time",
            "Cash Reward Per Interval",
            "Cards Per Cash Reward",
        ],
    },
    {
        "label": "Generations",
        "settings": [
            "Active Region",
        ],
        # The 9 per-generation booleans render as a single chip row instead of
        # 9 separate Enabled/Disabled rows — much faster to scan and toggle.
        "chip_group": {
            "label": "Enabled Generations",
            "description": (
                "Toggle which generations can spawn. Disabled gens are "
                "excluded from the encounter pool entirely; the Active Region "
                "only biases spawns within the enabled set."
            ),
            "keys": [
                ("misc.gen1", "Gen 1"),
                ("misc.gen2", "Gen 2"),
                ("misc.gen3", "Gen 3"),
                ("misc.gen4", "Gen 4"),
                ("misc.gen5", "Gen 5"),
                ("misc.gen6", "Gen 6"),
                ("misc.gen7", "Gen 7"),
                ("misc.gen8", "Gen 8"),
                ("misc.gen9", "Gen 9"),
            ],
        },
    },
]


# Active region dropdown options — preserved verbatim from the legacy window.
ACTIVE_REGION_OPTIONS = [
    {"value": None, "label": "No Region"},
    {"value": "kanto", "label": "Kanto (Gen 1)"},
    {"value": "johto", "label": "Johto (Gen 2)"},
    {"value": "hoenn", "label": "Hoenn (Gen 3)"},
    {"value": "sinnoh", "label": "Sinnoh (Gen 4)"},
    {"value": "unova", "label": "Unova (Gen 5)"},
    {"value": "kalos", "label": "Kalos (Gen 6)"},
    {"value": "alola", "label": "Alola (Gen 7)"},
    {"value": "galar", "label": "Galar (Gen 8)"},
    {"value": "hisui", "label": "Hisui (Gen 8)"},
    {"value": "paldea", "label": "Paldea (Gen 9)"},
]


def validate_and_clamp(config):
    """Apply the legacy window's save-time bounds. Returns (config, adjustments)
    where adjustments is a list of human-readable strings describing what
    was changed (empty if nothing was clamped)."""
    adjustments = []

    if "battle.cards_per_round" in config:
        config["battle.cards_per_round"] = _coerce_cards_per_round(
            config["battle.cards_per_round"]
        )

    if "trainer.cash_reward_interval" in config:
        v = config["trainer.cash_reward_interval"]
        if isinstance(v, int):
            new_v = max(5, min(250, v))
            if new_v != v:
                config["trainer.cash_reward_interval"] = new_v
                adjustments.append(
                    f"Reward Interval adjusted to {new_v} (range 5–250)."
                )

    if "trainer.cash_reward_amount" in config:
        amt = config["trainer.cash_reward_amount"]
        if isinstance(amt, int):
            new_amt = max(10, min(2000, amt))
            interval = config.get("trainer.cash_reward_interval", 10)
            max_allowed = interval * 100
            if new_amt > max_allowed:
                new_amt = max_allowed
                adjustments.append(
                    f"Reward Amount capped at {new_amt}¥ (100:1 ratio limit)."
                )
            elif new_amt != amt:
                adjustments.append(
                    f"Reward Amount adjusted to {new_amt}¥ (range 10–2000)."
                )
            config["trainer.cash_reward_amount"] = new_amt

    return config, adjustments


def _coerce_cards_per_round(value):
    """Accept an int, the string "a-b" range, or fall back to 2 on garbage."""
    if isinstance(value, int):
        return 1 if value == 0 else value
    text = str(value).strip()
    try:
        n = int(text)
        return 1 if n == 0 else n
    except ValueError:
        pass
    if "-" in text:
        try:
            a, b = (int(x) for x in text.split("-", 1))
            low, high = min(a, b), max(a, b)
            return f"{low}-{high}"
        except ValueError:
            pass
    return 2
