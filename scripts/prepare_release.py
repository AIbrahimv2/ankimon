import os
import json
import subprocess
import argparse
import requests
from typing import List, Dict, Optional

def run_command(command: List[str], check: bool = True) -> str:
    result = subprocess.run(command, capture_output=True, text=True, check=check)
    return result.stdout.strip()

def get_previous_tag(current_version: str) -> Optional[str]:
    try:
        # Find all -E pattern tags, sort by creation date
        tags = run_command(["git", "for-each-ref", "--sort=-creatordate", "--format=%(refname:short)", "refs/tags"]).split("\n")
        # Filter for -E tags and exclude current version
        version_tags = [t for t in tags if t.endswith("-E") and t != current_version]
        return version_tags[0] if version_tags else None
    except Exception as e:
        print(f"Error finding previous tag: {e}")
        return None

def fetch_prs_since_tag(repo: str, previous_tag: str, token: str) -> List[Dict]:
    url = f"https://api.github.com/repos/{repo}/compare/{previous_tag}...main"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    commits = response.json().get("commits", [])
    
    pr_numbers = set()
    pull_requests = []
    
    for commit in commits:
        sha = commit["sha"]
        pr_url = f"https://api.github.com/repos/{repo}/commits/{sha}/pulls"
        pr_resp = requests.get(pr_url, headers=headers)
        if pr_resp.status_code == 200:
            for pr in pr_resp.json():
                if pr["merged_at"] and pr["number"] not in pr_numbers:
                    pr_numbers.add(pr["number"])
                    pull_requests.append(pr)
    
    return pull_requests

def update_manifest(version: str):
    path = "src/Ankimon/manifest.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["version"] = version
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Updated {path} to {version}")

def update_contributors(pull_requests: List[Dict]):
    path = ".all-contributorsrc"
    if not os.path.exists(path):
        return
    
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    existing_logins = {c["login"] for c in data.get("contributors", [])}
    new_found = False
    
    for pr in pull_requests:
        user = pr.get("user", {})
        login = user.get("login")
        if login and login != "github-actions[bot]" and login not in existing_logins:
            print(f"Adding new contributor: {login}")
            data["contributors"].append({
                "login": login,
                "name": login,
                "avatar_url": f"https://github.com/{login}.png",
                "profile": f"https://github.com/{login}",
                "contributions": ["code"]
            })
            existing_logins.add(login)
            new_found = True
            
    if new_found:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

def generate_changelogs(version: str, pull_requests: List[Dict], highlights: str, nicknames: Dict):
    version_no_v = version.lstrip('v')
    os.makedirs("assets/changelogs", exist_ok=True)
    
    repo_url = "https://github.com/h0tp-ftw/ankimon"
    
    categories = {
        "enhancement": [],
        "bug": [],
        "documentation": [],
        "other": []
    }
    
    discord_categories = {
        "enhancement": [],
        "bug": [],
        "documentation": [],
        "other": []
    }
    
    contributors = set()
    
    for pr in pull_requests:
        labels = [l["name"].lower() for l in pr.get("labels", [])]
        if any(l in labels for l in ["ignore-for-changelog", "exclude-from-changelog"]):
            continue
            
        login = pr["user"]["login"]
        contributors.add(login)
        nick_data = nicknames.get(login, {})
        nickname = nick_data.get("nickname", login)
        discord_id = nick_data.get("discord_id")
        
        # GitHub Entry
        pr_link = f"[#{pr['number']}]({repo_url}/pull/{pr['number']})"
        user_link = f"[@{login}](https://github.com/{login})"
        entry = f"- {pr['title']} {pr_link} {user_link}"
        
        # Discord Entry
        user_mention = f"<@{discord_id}>" if discord_id else f"@{nickname}"
        d_entry = f"- {pr['title']} #{pr['number']} {user_mention}"
        
        cat = "other"
        if any(l in labels for l in ["enhancement", "feature", "type: enhancement"]):
            cat = "enhancement"
        elif any(l in labels for l in ["bug", "fix", "type: bug"]):
            cat = "bug"
        elif any(l in labels for l in ["documentation", "docs", "type: documentation"]):
            cat = "documentation"
            
        categories[cat].append(entry)
        discord_categories[cat].append(d_entry)
        
    # Build GitHub Changelog
    github_path = f"assets/changelogs/{version_no_v}.md"
    with open(github_path, "w", encoding="utf-8") as f:
        f.write(f"## 🌟 Ankimon v{version_no_v} 🌟\n\n")
        
        thank_you = "Thank you to all contributors! <3"
        if contributors:
            c_links = [f"[@{u}](https://github.com/{u}) ({nicknames.get(u, {}).get('nickname', u)})" for u in sorted(contributors)]
            thank_you = f"A huge thank you to {', '.join(c_links)} for their contributions to this update! <3"
        
        f.write(f"{thank_you}\n\n")
        f.write("### What's new\n")
        f.write(f"{highlights if highlights else '[JULES_HIGHLIGHTS]'}\n\n")
        f.write("— h0tp 💖\n\n***\n\n")
        f.write(f"## 📜 Full changelog — v{version_no_v}\n\n")
        
        if categories["enhancement"]:
            f.write("### ✨ Features & Improvements!\n\n")
            f.write("\n".join(categories["enhancement"]) + "\n\n")
        if categories["bug"]:
            f.write("### 🐛 Bug Fixes & Stability!\n\n")
            f.write("\n".join(categories["bug"]) + "\n\n")
        if categories["documentation"]:
            f.write("### 📚 Documentation!\n\n")
            f.write("\n".join(categories["documentation"]) + "\n\n")
        if categories["other"]:
            f.write("### 🔧 Other Changes!\n\n")
            f.write("\n".join(categories["other"]) + "\n\n")
            
        f.write("***\n\nMake a backup, but *your progress should NOT BE LOST from updating* - put a bug report if you lose your files\n\n")
        f.write("Backup guide ➡️ https://discord.com/channels/1241773562629718148/1303759380768096318\n\n***\n")

    # Build Discord Changelog
    discord_path = f"assets/changelogs/{version_no_v}-discord.md"
    with open(discord_path, "w", encoding="utf-8") as f:
        f.write(f"## 🌟 Ankimon v{version_no_v} 🌟\n\n")
        
        d_contributors = []
        all_have_ids = True
        for u in sorted(contributors):
            d_id = nicknames.get(u, {}).get("discord_id")
            if d_id:
                d_contributors.append(f"<@{d_id}>")
            else:
                d_contributors.append(f"@{u}")
                all_have_ids = False
        
        thank_you_text = ", ".join(d_contributors)
        if not all_have_ids or not d_contributors:
            thank_you_text = "[JULES_DISCORD_CONTRIBUTORS]"
            
        f.write(f"A huge thank you to {thank_you_text} for their contributions to this update! <3\n\n")
        f.write("### What's new\n")
        f.write(f"{highlights if highlights else '[JULES_HIGHLIGHTS]'}\n\n")
        f.write("— h0tp 💖\n\n---\n\n")
        f.write(f"## 📜 Full changelog — v{version_no_v}\n\n")
        
        if discord_categories["enhancement"]:
            f.write("### ✨ Features & Improvements!\n\n")
            f.write("\n".join(discord_categories["enhancement"]) + "\n\n")
        if discord_categories["bug"]:
            f.write("### 🐛 Bug Fixes & Stability!\n\n")
            f.write("\n".join(discord_categories["bug"]) + "\n\n")
        if discord_categories["other"]:
            f.write("### 🔧 Other Changes!\n\n")
            f.write("\n".join(discord_categories["other"]) + "\n\n")
            
        f.write(f"---\n\n**Download**: <https://github.com/h0tp-ftw/ankimon/releases/download/{version}/Ankimon.ankiaddon>\n\n")
        f.write("Make a backup, but *your progress should NOT BE LOST from updating* - put a bug report if you lose your files\n")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--highlights", default="")
    parser.add_argument("--psa", default="")
    parser.add_argument("--token", required=True)
    parser.add_argument("--repo", default="h0tp-ftw/ankimon")
    args = parser.parse_args()
    
    prev_tag = get_previous_tag(args.version)
    print(f"Previous tag: {prev_tag}")
    
    prs = []
    if prev_tag:
        prs = fetch_prs_since_tag(args.repo, prev_tag, args.token)
    else:
        print("No previous tag found, skipping PR fetch.")
        
    nicknames = {}
    nick_path = ".github/contributor-nicknames.json"
    if os.path.exists(nick_path):
        with open(nick_path, "r", encoding="utf-8") as f:
            nicknames = json.load(f)
            
    update_manifest(args.version)
    update_contributors(prs)
    generate_changelogs(args.version, prs, args.highlights, nicknames)
    
    print("Release preparation complete!")

if __name__ == "__main__":
    main()
