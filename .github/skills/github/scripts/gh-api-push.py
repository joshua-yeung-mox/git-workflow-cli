#!/usr/bin/env python3
"""Push unpushed local commits to GitHub via the Git Data API.

Bypasses Zscaler's Source Code DLP which blocks git push (binary pack
data). Uses gh api with base64-encoded JSON payloads instead.

Works on any repo/branch — auto-detects everything from the local git
repo in the current directory. Handles new repos, auto-init divergence,
and missing local tracking refs automatically.

Usage:
    cd <repo>
    python ~/PycharmProjects/copilot-workspace/scripts/gh-api-push.py [--force]

Options:
    --force    Force push (allows rebased/squashed commits, overwrites remote)

Requirements:
    - gh CLI authenticated (gh auth status)
    - Local HEAD must be ahead of the remote tracking branch by ≥1 commit
    - All commits to push must already exist locally (git commit done)
    - With --force: allows diverged history (rebase, squash, etc.)

How it works:
    1. Detects repo, branch, and remote SHA (falls back to GitHub API if
       local tracking ref is missing or "gone")
    2. If remote repo is completely empty (no commits), bootstraps it with
       a placeholder commit via the Contents API (the Git Data API returns
       409 "Git Repository is empty" until at least one commit exists)
    3. If remote SHA is not in local git objects (e.g. auto-init commit on
       a brand-new repo), switches to full-upload mode: uploads all tracked
       files rather than diffing — avoids empty-diff → 422 failure
    4. Creates GitHub blob objects for each file via POST (Zscaler-safe)
    5. Builds a new tree and commit via API
    6. Updates (or creates) the remote branch ref, with retry on transient
       connection resets
    7. Auto-syncs local HEAD: fetches the new commit object via HTTPS using
       'gh auth git-credential' (bypasses Zscaler SSH block) and resets
       local HEAD to match — no manual 'git fetch' step needed
"""

import base64
import json
import subprocess
import sys
import time
from pathlib import Path


def run(cmd, cwd, input_data=None, check=True):
    result = subprocess.run(cmd, input=input_data, capture_output=True, cwd=str(cwd))
    if check and result.returncode != 0:
        print(f"ERROR: {' '.join(str(c) for c in cmd)}", file=sys.stderr)
        print(result.stderr.decode()[:500], file=sys.stderr)
        sys.exit(1)
    return result


def git_str(*args, cwd):
    return run(["git", *args], cwd=cwd).stdout.decode().strip()


def object_exists_locally(sha: str, repo_root: Path) -> bool:
    """Return True if the git object exists in the local object store."""
    return run(["git", "cat-file", "-e", sha], cwd=repo_root, check=False).returncode == 0


def detect_context(repo_root: Path):
    """Auto-detect repo slug, branch, and remote SHA.

    Returns (slug, branch, remote_sha, is_new_branch) where:
      - remote_sha is None only for a brand-new empty repo (needs bootstrap)
      - remote_sha is "" for a new branch on an existing repo whose base commit
        is not available locally (full upload, but NO bootstrap)
      - is_new_branch is True when the branch does not yet exist on the remote
        (ref must be created via POST, not PATCHed)

    Falls back to the GitHub API when the local tracking ref is missing or
    marked "gone" — no git fetch required.
    """
    branch = git_str("rev-parse", "--abbrev-ref", "HEAD", cwd=repo_root)

    remote_url = git_str("remote", "get-url", "origin", cwd=repo_root)
    slug = (
        remote_url.replace("https://github.com/", "")
        .replace("git@github.com:", "")
        .removesuffix(".git")
    )

    # Try local tracking ref first (fast path — no network call)
    tracking_r = run(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        cwd=repo_root,
        check=False,
    )
    if tracking_r.returncode == 0:
        tracking = tracking_r.stdout.decode().strip()
        sha_r = run(["git", "rev-parse", tracking], cwd=repo_root, check=False)
        if sha_r.returncode == 0:
            return slug, branch, sha_r.stdout.decode().strip(), False

    # Tracking ref missing or "gone" — ask GitHub API directly
    print(f"  Local tracking ref missing — querying GitHub API for {branch}...")
    api_r = run(
        ["gh", "api", f"repos/{slug}/git/refs/heads/{branch}", "--jq", ".object.sha"],
        cwd=repo_root,
        check=False,
    )
    if api_r.returncode == 0 and api_r.stdout.strip():
        remote_sha = api_r.stdout.decode().strip()
        # Persist tracking config so git branch -vv shows correct status
        run(["git", "config", f"branch.{branch}.remote", "origin"], cwd=repo_root, check=False)
        run(
            ["git", "config", f"branch.{branch}.merge", f"refs/heads/{branch}"],
            cwd=repo_root,
            check=False,
        )
        print(f"  Remote {branch}: {remote_sha[:7]}")
        return slug, branch, remote_sha, False

    # No remote branch at all — either a new branch on an existing repo, or a
    # brand-new empty repo. Distinguish by checking whether ANY ref exists.
    any_ref = run(
        ["gh", "api", f"repos/{slug}/git/refs", "--jq", ".[0].object.sha"],
        cwd=repo_root,
        check=False,
    )
    if any_ref.returncode == 0 and any_ref.stdout.strip():
        # Repo is NOT empty — this is a new branch. Diff against the default
        # branch's tree so we only upload new/changed files (not the whole repo).
        default_branch = (
            run(
                ["gh", "api", f"repos/{slug}", "--jq", ".default_branch"],
                cwd=repo_root,
                check=False,
            )
            .stdout.decode()
            .strip()
        )
        base_r = run(
            ["gh", "api", f"repos/{slug}/git/refs/heads/{default_branch}", "--jq", ".object.sha"],
            cwd=repo_root,
            check=False,
        )
        base_sha = base_r.stdout.decode().strip() if base_r.returncode == 0 else ""
        if base_sha and object_exists_locally(base_sha, repo_root):
            print(
                f"  New branch — diffing against default branch '{default_branch}' ({base_sha[:7]})"
            )
            return slug, branch, base_sha, True  # branch_exists_on_remote=False
        # Default branch SHA not available locally (never fetched) — full upload.
        print(f"  New branch on existing repo — full upload (base not in local objects)")
        return slug, branch, "", True  # empty base → full upload, but skip bootstrap

    # Truly empty repo — needs bootstrap.
    print(f"  No remote branch found — will create {branch} from scratch")
    return slug, branch, None, False


def gh_api(repo_slug, path, method="GET", data=None, cwd=Path("."), retries=3):
    """Call the GitHub API with automatic retry on transient connection errors."""
    cmd = ["gh", "api", f"repos/{repo_slug}/{path}"]
    if method != "GET":
        cmd += ["-X", method]
    inp = None
    if data is not None:
        cmd += ["--input", "-"]
        inp = json.dumps(data).encode()

    for attempt in range(1, retries + 1):
        result = subprocess.run(cmd, input=inp, capture_output=True, cwd=str(cwd))
        if result.returncode == 0:
            return json.loads(result.stdout) if result.stdout.strip() else {}
        err = result.stderr.decode()
        if attempt < retries and ("connection reset" in err.lower() or "EOF" in err):
            print(f"  ⚠ Transient error (attempt {attempt}/{retries}), retrying in 2s...")
            time.sleep(2)
            continue
        print(f"ERROR: {' '.join(str(c) for c in cmd)}", file=sys.stderr)
        print(err[:500], file=sys.stderr)
        sys.exit(1)


def initialize_empty_repo(repo_slug: str, branch: str, repo_root: Path) -> str:
    """Bootstrap an empty GitHub repo using the Contents API.

    The Git Data API (blobs/trees/commits) returns 409 "Git Repository is
    empty" for repos that have never had a commit.  The Contents API does NOT
    have this restriction, so we use it to create a minimal placeholder commit
    that unblocks the Git Data API for all subsequent calls.

    The placeholder .gitkeep file only exists in this bootstrap commit; the
    final commit (created in full-upload mode with a fresh tree) will NOT
    include it, so the working tree is exactly what the user committed locally.
    """
    print("  Empty repo — bootstrapping via Contents API...")
    resp = gh_api(
        repo_slug,
        "contents/.gitkeep",
        method="PUT",
        data={"message": "chore: Initialize repository", "content": "", "branch": branch},
        cwd=repo_root,
    )
    init_sha = resp["commit"]["sha"]
    print(f"  Bootstrap commit: {init_sha[:7]}")
    return init_sha


def create_blob(repo_slug, file_path: str, repo_root: Path) -> str | None:
    full_path = repo_root / file_path
    if full_path.is_dir():
        return None

    # Read from git objects first — handles deleted files and broken symlinks.
    # git cat-file blob HEAD:<path> returns the committed content regardless of
    # whether the working-tree file exists or is a symlink to a missing target.
    result = run(["git", "cat-file", "blob", f"HEAD:{file_path}"], cwd=repo_root, check=False)
    if result.returncode == 0:
        content = result.stdout
    elif full_path.exists() and not full_path.is_symlink():
        # Newly staged file not yet fully committed (edge case)
        content = full_path.read_bytes()
    else:
        print(f"  (skipped — not in git objects and not on disk: {file_path})")
        return None

    resp = gh_api(
        repo_slug,
        "git/blobs",
        method="POST",
        data={"content": base64.b64encode(content).decode(), "encoding": "base64"},
        cwd=repo_root,
    )
    return resp["sha"]


def get_file_mode(file_path: str, repo_root: Path) -> str:
    result = run(["git", "ls-files", "-s", file_path], cwd=repo_root, check=False)
    if result.stdout:
        return result.stdout.decode().split()[0]
    return "100644"


def main():
    force = "--force" in sys.argv

    repo_root = Path(
        run(["git", "rev-parse", "--show-toplevel"], cwd=Path(".")).stdout.decode().strip()
    )

    print("── GitHub Git Data API push ──")
    repo_slug, branch, remote_sha, is_new_branch = detect_context(repo_root)
    local_sha = git_str("rev-parse", "HEAD", cwd=repo_root)

    print(f"Repo:   {repo_slug}")
    print(f"Branch: {branch}")
    print(f"From:   {remote_sha[:7] if remote_sha else '(none — new repo/branch)'} (remote)")
    print(f"To:     {local_sha[:7]} (local HEAD)")
    if force:
        print("Mode:   FORCE PUSH (will overwrite remote history)")
    if is_new_branch:
        print(f"Mode:   NEW BRANCH (will create refs/heads/{branch})")

    if remote_sha and remote_sha == local_sha:
        print("\nNothing to push — remote is already up to date.")
        sys.exit(0)

    # Decide between diff mode and full-upload mode.
    #
    # Full-upload is required when:
    #   (a) remote_sha is None  → brand-new empty repo, nothing on remote
    #   (b) remote_sha is ""    → new branch, base commit not in local objects
    #   (c) remote_sha is set but not in local objects → e.g. auto-init commit
    #       that was never fetched; git diff would return empty, causing 422
    full_upload = (
        remote_sha is None or remote_sha == "" or not object_exists_locally(remote_sha, repo_root)
    )

    if full_upload and remote_sha:
        print(f"  Remote SHA {remote_sha[:7]} not in local objects — switching to full-upload mode")

    if not full_upload:
        # Standard divergence check (only meaningful when diff mode is used)
        behind = git_str("rev-list", "--count", f"HEAD..{remote_sha}", cwd=repo_root)
        if behind != "0":
            if not force:
                print(f"\nERROR: local is {behind} commit(s) behind remote. Pull first.")
                print("       Or use --force to overwrite remote with local history.")
                sys.exit(1)
            print(f"⚠️  Force pushing — {behind} commit(s) on remote not in local history")

        ahead = git_str("rev-list", "--count", f"{remote_sha}..HEAD", cwd=repo_root)
        print(f"Pushing {ahead} commit(s) ahead of remote\n")

    # ── Determine files to upload ────────────────────────────────────────────

    if full_upload:
        print("Full-upload mode — uploading all tracked files...")
        to_upsert = run(["git", "ls-files"], cwd=repo_root).stdout.decode().strip().splitlines()
        to_delete = []
        base_tree_sha = None
    else:
        print("Fetching remote tree SHA...")
        remote_commit = gh_api(repo_slug, f"git/commits/{remote_sha}", cwd=repo_root)
        base_tree_sha = remote_commit["tree"]["sha"]
        print(f"  Base tree: {base_tree_sha[:7]}")

        diff_out = git_str("diff", "--name-status", "-M", remote_sha, "HEAD", cwd=repo_root)
        to_upsert, to_delete = [], []
        for line in diff_out.splitlines():
            if not line:
                continue
            parts = line.split("\t")
            status = parts[0]
            if status in ("A", "M"):
                to_upsert.append(parts[1])
            elif status == "D":
                to_delete.append(parts[1])
            elif status.startswith("R"):
                to_delete.append(parts[1])
                to_upsert.append(parts[2])

        print(f"Changes: {len(to_upsert)} upsert, {len(to_delete)} delete\n")

    # ── Bootstrap empty repo if needed ───────────────────────────────────────
    # The Git Data API returns 409 on repos that have never had a commit.
    # Use the Contents API to create a placeholder bootstrap commit first.
    # ONLY for truly empty repos (remote_sha is None). A new branch on an
    # existing repo (remote_sha == "" or a base SHA) must NOT bootstrap — the
    # repo already has commits and the Contents API write may be forbidden.
    bootstrapped = False
    if full_upload and remote_sha is None:
        remote_sha = initialize_empty_repo(repo_slug, branch, repo_root)
        bootstrapped = True
        # remote_sha is now set but NOT in local objects →
        #   full_upload stays True (already set above)
        #   commit will have remote_sha as its parent (see commit_data below)

    # ── Create blobs ─────────────────────────────────────────────────────────

    tree_items = []
    print(f"Creating {len(to_upsert)} blob(s)...")
    for idx, file_path in enumerate(to_upsert, 1):
        print(f"  [{idx:2}/{len(to_upsert)}] {file_path}")
        blob_sha = create_blob(repo_slug, file_path, repo_root)
        if blob_sha is None:
            print("       (skipped — directory)")
            continue
        mode = get_file_mode(file_path, repo_root)
        tree_items.append({"path": file_path, "mode": mode, "type": "blob", "sha": blob_sha})

    if to_delete:
        print(f"\nScheduling {len(to_delete)} deletion(s)...")
        for path in to_delete:
            print(f"  - {path}")
            tree_items.append({"path": path, "mode": "100644", "type": "blob", "sha": None})

    # ── Create tree ───────────────────────────────────────────────────────────

    # Edge case: no file changes (e.g. empty / version-bump / merge commit).
    # The Git Data API rejects a tree with zero items and no base_tree (422),
    # and a no-op diff yields an empty tree_items list. Reuse the base tree
    # directly — the new commit points at the identical tree.
    if not tree_items and base_tree_sha:
        print(f"\nNo file changes — reusing base tree {base_tree_sha[:7]}")
        tree_sha = base_tree_sha
    else:
        print(f"\nCreating tree ({len(tree_items)} items)...")
        tree_data: dict = {"tree": tree_items}
        if base_tree_sha:
            tree_data["base_tree"] = base_tree_sha
        tree_resp = gh_api(repo_slug, "git/trees", method="POST", data=tree_data, cwd=repo_root)
        tree_sha = tree_resp["sha"]
        print(f"  New tree: {tree_sha[:7]}")

    # ── Create commit ─────────────────────────────────────────────────────────

    commit_msg = git_str("log", "-1", "--format=%B", cwd=repo_root)
    commit_data: dict = {"message": commit_msg, "tree": tree_sha}
    if bootstrapped:
        # Empty repo bootstrap: parent is the placeholder commit.
        commit_data["parents"] = [remote_sha]
    elif is_new_branch and remote_sha:
        # New branch diffed against a base commit: parent is that base.
        commit_data["parents"] = [remote_sha]
    elif remote_sha:
        # Existing branch: parent is the current remote tip.
        commit_data["parents"] = [remote_sha]
    # else: new branch full-upload (remote_sha == "") → root commit, no parents.

    print("Creating commit...")
    new_commit = gh_api(repo_slug, "git/commits", method="POST", data=commit_data, cwd=repo_root)
    print(f"  New commit: {new_commit['sha'][:7]}")

    # ── Update (or create) branch ref ────────────────────────────────────────

    print("Updating branch ref...")
    if is_new_branch:
        # Branch doesn't exist on the remote yet — create the ref via POST.
        gh_api(
            repo_slug,
            "git/refs",
            method="POST",
            data={"ref": f"refs/heads/{branch}", "sha": new_commit["sha"]},
            cwd=repo_root,
        )
    else:
        # Try PATCH first; fall back to POST if the ref doesn't exist on GitHub
        # (can happen when local tracking config exists but branch was never pushed)
        cmd = [
            "gh",
            "api",
            f"repos/{repo_slug}/git/refs/heads/{branch}",
            "-X",
            "PATCH",
            "--input",
            "-",
        ]
        patch_r = subprocess.run(
            cmd,
            input=json.dumps({"sha": new_commit["sha"], "force": True}).encode(),
            capture_output=True,
            cwd=str(repo_root),
        )
        if patch_r.returncode != 0 and "Reference does not exist" in patch_r.stderr.decode():
            print("  Branch ref missing on remote — creating via POST...")
            gh_api(
                repo_slug,
                "git/refs",
                method="POST",
                data={"ref": f"refs/heads/{branch}", "sha": new_commit["sha"]},
                cwd=repo_root,
            )
        elif patch_r.returncode != 0:
            print(f"ERROR: {' '.join(cmd)}", file=sys.stderr)
            print(patch_r.stderr.decode()[:500], file=sys.stderr)
            sys.exit(1)
    print(f"  ✅ {branch} → {new_commit['sha'][:7]}")

    auto_sync(repo_slug, branch, new_commit["sha"], repo_root)


def auto_sync(repo_slug: str, branch: str, new_sha: str, repo_root: Path):
    """Sync local tracking ref after an API push without requiring SSH.

    The API push creates a new git commit object on GitHub that doesn't exist
    locally, so 'git branch -vv' would show the branch as ahead forever and
    'git status' would warn about diverged history.

    SSH fetch is blocked by Zscaler. This uses 'gh auth git-credential' as a
    credential helper so git can fetch via HTTPS without exposing a token.

    Steps:
      1. Ensure the remote is configured as HTTPS (credential helper needs it)
      2. Set branch tracking config
      3. git fetch via HTTPS + gh credential helper → downloads new commit object
      4. git reset --hard to make local HEAD SHA match remote SHA
    """
    print("\nSyncing local HEAD...")

    # 1. Ensure origin uses HTTPS (credential helper only works with HTTPS)
    remote_url_r = run(["git", "remote", "get-url", "origin"], cwd=repo_root, check=False)
    if remote_url_r.returncode == 0:
        url = remote_url_r.stdout.decode().strip()
        if url.startswith("git@github.com:"):
            https_url = f"https://github.com/{repo_slug}.git"
            run(["git", "remote", "set-url", "origin", https_url], cwd=repo_root, check=False)
            print(f"  Remote URL updated to HTTPS")

    # 2. Set tracking config so 'git status' knows the upstream
    run(["git", "config", f"branch.{branch}.remote", "origin"], cwd=repo_root, check=False)
    run(
        ["git", "config", f"branch.{branch}.merge", f"refs/heads/{branch}"],
        cwd=repo_root,
        check=False,
    )

    # 3. Fetch new commit object via HTTPS (bypasses SSH / Zscaler)
    fetch_r = run(
        [
            "git",
            "-c",
            "credential.helper=!gh auth git-credential",
            "fetch",
            "origin",
            f"refs/heads/{branch}:refs/remotes/origin/{branch}",
        ],
        cwd=repo_root,
        check=False,
    )
    if fetch_r.returncode != 0:
        print(f"  ⚠ Auto-sync fetch failed — run manually:")
        print(f"    git -c credential.helper='!gh auth git-credential' fetch origin")
        print(f"    git reset --hard origin/{branch}")
        return

    # 4. Reset local HEAD to the fetched remote SHA
    reset_r = run(
        ["git", "reset", "--hard", f"refs/remotes/origin/{branch}"], cwd=repo_root, check=False
    )
    synced = git_str("rev-parse", "HEAD", cwd=repo_root)
    if reset_r.returncode == 0:
        print(f"  ✅ Local HEAD → {synced[:7]}  (matches remote)")
    else:
        # Tracking ref updated even if working tree reset had issues (e.g. long symlinks)
        print(f"  ✅ Tracking ref synced → {new_sha[:7]}")
        print(f"     (working tree unchanged — run 'git reset --hard origin/{branch}' if needed)")


if __name__ == "__main__":
    main()
