# Ankimon Release Checklist

Jules, please verify these items before creating the PR.

- [ ] **Version Bump**: `src/Ankimon/manifest.json` version matches the intended release.
- [ ] **Changelogs Generated**: `assets/changelogs/<version>.md` exists.
- [ ] **Discord Changelog Generated**: `assets/changelogs/<version>-discord.md` exists.
- [ ] **Placeholders Removed**: All `[JULES_...]` tags have been replaced with real content.
- [ ] **Contributor Credits**: `.all-contributorsrc` is updated with new contributors. Ensure the entries are not duplicated.
- [ ] **Nicknames Validated**: All contributors in the changelog have entries in `.github/contributor-nicknames.json` with their Discord IDs and nicknames. If any are missing, tell the user and wait for the info, and update the JSON as well as the changelogs once you receive it. Ensure the entries are not duplicated.
- [ ] **Integrity Tests**: `pytest tests/test_addon_integrity.py` passes.
- [ ] **Asset Paths**: Verify that changelog paths in the PR description are correct.
