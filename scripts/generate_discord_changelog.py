import os
import re
import json
import sys
import argparse

def main():
    # Force UTF-8 stdout encoding for Windows compatibility when printing emojis
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    parser = argparse.ArgumentParser(description="Generate a Discord-formatted changelog.")
    parser.add_argument("--version", help="Version to generate for (e.g. 1.6-E). If omitted, reads from manifest.json.")
    args = parser.parse_args()

    version = args.version
    if not version:
        manifest_path = "src/Ankimon/manifest.json"
        if os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                version = data.get("version")
        if not version:
            print("Error: Could not find version in manifest.json and no --version argument was provided.")
            return

    version_no_v = version.lstrip('v')
    changelog_path = f"assets/changelogs/{version_no_v}.md"

    if not os.path.exists(changelog_path):
        print(f"Error: Changelog file not found at {changelog_path}")
        return

    # Load Discord IDs from .all-contributorsrc
    discord_ids = {}
    contrib_path = ".all-contributorsrc"
    if os.path.exists(contrib_path):
        with open(contrib_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            for c in data.get("contributors", []):
                login = c.get("login")
                d_id = c.get("discord_id")
                if login:
                    discord_ids[login] = d_id

    # Read default changelog
    with open(changelog_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Remove everything starting from "## 📜 Full changelog"
    full_changelog_marker = "## 📜 Full changelog"
    if full_changelog_marker in content:
        content = content.split(full_changelog_marker)[0].strip()

    # Remove any trailing horizontal rules (*** or ---)
    content = re.sub(r'\s*\*\*\*+\s*$', '', content)
    content = re.sub(r'\s*---+\s*$', '', content)
    content = content.strip()

    # 2. Replace contributor links in the remaining content:
    # Pattern 1: [@username](url) (Nickname)
    # Pattern 2: [@username](url)
    def replace_user(match):
        username = match.group(1)
        d_id = discord_ids.get(username)
        if d_id:
            return f"<@{d_id}>"
        return f"@{username}"

    # Replace Pattern 1
    content = re.sub(r'\[@([\w-]+)\]\([^)]+\)\s*\([^)]*\)', replace_user, content)
    # Replace Pattern 2
    content = re.sub(r'\[@([\w-]+)\]\([^)]+\)', replace_user, content)

    # Print the resulting discord changelog
    print("\n================ DISCORD CHANGELOG ================\n")
    print(content)
    print("\n===================================================\n")

if __name__ == "__main__":
    main()
