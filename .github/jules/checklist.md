# Ankimon Release Checklist

Jules, please verify these items before creating the PR. This file shouldn't be edited - copy this for your PR message!

- [ ] **Version Bump**: `src/Ankimon/manifest.json` version matches the intended release.
- [ ] **Changelogs Generated**: `assets/changelogs/<version>.md` exists.
- [ ] **Discord Changelog Generated**: `assets/changelogs/<version>-discord.md` exists.
- [ ] **Placeholders Removed**: All `[JULES_...]` tags have been replaced with real content.
- [ ] **Contributor Credits**: `.all-contributorsrc` is updated with new contributors. Ensure the entries are not duplicated.
- [ ] **Nicknames Validated**: All contributors in the changelog have `"nickname"` and `"discord_id"` fields filled out in their `.all-contributorsrc` entry. If any are missing, tell the user and wait for the info, and update `.all-contributorsrc` as well as the changelogs once you receive it. Ensure the entries are not duplicated.
- [ ] **Integrity Tests**: `pytest tests/test_addon_integrity.py` passes.
- [ ] **Asset Paths**: Verify that changelog paths in the PR description are correct.
