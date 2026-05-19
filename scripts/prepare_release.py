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

def fetch_prs_since_tag(repo: str, previous_tag: str) -> List[Dict]:
    # Get the date of the previous tag
    tag_date = run_command(["git", "log", "-1", "--format=%cI", previous_tag])
    headers = {"Accept": "application/vnd.github.v3+json"}
    
    pull_requests = []
    page = 1
    
    while True:
        url = f"https://api.github.com/repos/{repo}/pulls?state=closed&base=main&sort=updated&direction=desc&per_page=100&page={page}"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        prs = response.json()
        
        if not prs:
            break
            
        for pr in prs:
            merged_at = pr.get("merged_at")
            if not merged_at or merged_at <= tag_date:
                continue
                
            # Filter out automated release PRs
            author = pr.get("user", {}).get("login", "")
            title = pr.get("title", "")
            if author == "github-actions[bot]" or author == "jules-invoke[bot]" or "bump version" in title.lower() or "release v" in title.lower():
                continue
                
            pull_requests.append(pr)
                
        # Since PRs are sorted by 'updated_at', if the oldest PR in this page was updated
        # before our tag_date, we can safely stop paginating.
        if prs[-1].get("updated_at", "") < tag_date:
            break
            
        page += 1
            
    return pull_requests

def update_manifest(version: str):
    path = "src/Ankimon/manifest.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["version"] = version
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
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
                "contributions": ["code"],
                "nickname": "",
                "discord_id": ""
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
    
    contributors = set()
    
    for pr in pull_requests:
        labels = [l["name"].lower() for l in pr.get("labels", [])]
        if any(l in labels for l in ["ignore-for-changelog", "exclude-from-changelog"]):
            continue
            
        login = pr["user"]["login"]
        contributors.add(login)
        nick_data = nicknames.get(login, {})
        
        # App Entry (needs explicit markdown links)
        pr_link = f"[#{pr['number']}]({repo_url}/pull/{pr['number']})"
        user_link = f"[@{login}](https://github.com/{login})"
        
        # Include nickname if it's different from the login and is not empty
        nick = nick_data.get("nickname")
        if nick and nick != login:
            user_link += f" ({nick})"
            
        entry = f"- {pr['title']} {pr_link} {user_link}"
        
        cat = "other"
        if any(l in labels for l in ["enhancement", "feature", "type: enhancement"]):
            cat = "enhancement"
        elif any(l in labels for l in ["bug", "fix", "type: bug"]):
            cat = "bug"
        elif any(l in labels for l in ["documentation", "docs", "type: documentation"]):
            cat = "documentation"
            
        categories[cat].append(entry)
        
    # Build App Changelog (assets/changelogs/<version>.md)
    github_path = f"assets/changelogs/{version_no_v}.md"
    with open(github_path, "w", encoding="utf-8") as f:
        f.write(f"## 🌟 Ankimon v{version_no_v} 🌟\n\n")
        
        thank_you = "Thank you to all contributors! <3"
        if contributors:
            c_links = []
            for u in sorted(contributors):
                nick = nicknames.get(u, {}).get('nickname')
                link = f"[@{u}](https://github.com/{u})"
                if nick and nick != u:
                    link += f" ({nick})"
                c_links.append(link)
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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--highlights", default="")
    parser.add_argument("--psa", default="")
    parser.add_argument("--repo", default="h0tp-ftw/ankimon")
    args = parser.parse_args()
    
    prev_tag = get_previous_tag(args.version)
    print(f"Previous tag: {prev_tag}")
    
    prs = []
    if prev_tag:
        prs = fetch_prs_since_tag(args.repo, prev_tag)
    else:
        print("No previous tag found, skipping PR fetch.")
        
    nicknames = {}
    all_contrib_path = ".all-contributorsrc"
    if os.path.exists(all_contrib_path):
        with open(all_contrib_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            for c in data.get("contributors", []):
                nicknames[c["login"]] = {
                    "nickname": c.get("nickname", ""),
                    "discord_id": c.get("discord_id", "")
                }
            
    update_manifest(args.version)
    update_contributors(prs)
    generate_changelogs(args.version, prs, args.highlights, nicknames)
    
    print("Release preparation complete!")

if __name__ == "__main__":
    main()
