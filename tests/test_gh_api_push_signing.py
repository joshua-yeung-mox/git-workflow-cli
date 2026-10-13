"""Tests for SSH commit signing in gh-api-push.

Org ruleset `force_signed_commit_signature` rejects unsigned API-created
commits (422 "Reference update failed"). The shim must sign the commit it
creates via the Git Data API, using the local repo's SSH signing key, over
GitHub's canonical payload:

    tree <sha>\n
    parent <sha>\n            (0 or more)
    author <name> <email> <unix_ts> <tz>\n
    committer <name> <email> <unix_ts> <tz>\n
    \n
    <message>

Author/committer identity + timestamps MUST come from the local commit so
GitHub's payload reconstruction matches the signed bytes byte-for-byte.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "skills"
    / "github"
    / "scripts"
    / "gh-api-push.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("gh_api_push", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load_module()


# ── canonical payload ────────────────────────────────────────────────────────


def test_payload_single_parent(mod):
    payload = mod.build_canonical_payload(
        tree="86784b082ef9734b61847890591d509774b1134c",
        parents=["29ce5119184d004df76d702abfae7cfa250c2e92"],
        message="subject\n\nbody\n",
        author=("joshua.yeung", "joshua.yeung@moxbank.com", 1791886184, "+0800"),
        committer=("joshua.yeung", "joshua.yeung@moxbank.com", 1791886184, "+0800"),
    )
    assert payload == (
        "tree 86784b082ef9734b61847890591d509774b1134c\n"
        "parent 29ce5119184d004df76d702abfae7cfa250c2e92\n"
        "author joshua.yeung <joshua.yeung@moxbank.com> 1791886184 +0800\n"
        "committer joshua.yeung <joshua.yeung@moxbank.com> 1791886184 +0800\n"
        "\n"
        "subject\n\nbody\n"
    )


def test_payload_merge_commit_two_parents(mod):
    payload = mod.build_canonical_payload(
        tree="t" * 40,
        parents=["a" * 40, "b" * 40],
        message="merge\n",
        author=("n", "e@x", 100, "+0000"),
        committer=("n", "e@x", 100, "+0000"),
    )
    assert payload.count("parent ") == 2
    assert f"parent {'a'*40}\nparent {'b'*40}\n" in payload


def test_payload_root_commit_no_parents(mod):
    payload = mod.build_canonical_payload(
        tree="t" * 40,
        parents=[],
        message="root\n",
        author=("n", "e@x", 100, "+0000"),
        committer=("n", "e@x", 100, "+0000"),
    )
    assert "parent" not in payload
    assert payload.startswith(f"tree {'t'*40}\nauthor")


# ── ISO-8601 → (unix_ts, tz) conversion ─────────────────────────────────────


def test_iso_to_unix_tz_positive_offset(mod):
    unix, tz = mod.iso_to_unix_tz("2026-10-13T18:09:44+08:00")
    assert unix == 1791886184
    assert tz == "+0800"


def test_iso_to_unix_tz_negative_offset(mod):
    unix, tz = mod.iso_to_unix_tz("2026-10-13T10:09:44-05:30")
    assert tz == "-0530"


def test_iso_to_unix_tz_zulu(mod):
    unix, tz = mod.iso_to_unix_tz("2026-10-13T10:09:44Z")
    assert tz == "+0000"


# ── signing-key resolution ──────────────────────────────────────────────────


def test_resolve_signing_key_pub_stripped(mod, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.signingkey", "/keys/my_key.pub"],
        check=True,
    )
    assert mod.resolve_signing_key(repo) == "/keys/my_key"


def test_resolve_signing_key_not_configured(mod, tmp_path, monkeypatch):
    """With global+system config isolated and nothing set, → None."""
    import os

    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    repo = tmp_path / "repo2"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    # no user.signingkey anywhere (subprocesses inherit the isolated env) → None
    assert mod.resolve_signing_key(repo) is None


def test_ssh_sign_produces_armored_signature(mod, tmp_path):
    """Sign with the real user key if available; else generate a throwaway key.

    Verifies (a) output is an armored SSH signature, and (b) the signature
    verifies against the exact payload bytes with namespace git.
    """
    key = tmp_path / "k"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
        check=True,
        capture_output=True,
    )
    payload = b"tree " + b"t" * 40 + b"\n\nmsg\n"
    sig = mod.ssh_sign(key, payload)
    assert sig is not None
    assert sig.startswith("-----BEGIN SSH SIGNATURE-----")
    assert sig.rstrip().endswith("-----END SSH SIGNATURE-----")

    # round-trip verify via allowed_signers file (the format ssh-keygen -Y
    # verify requires; a bare pubkey path is rejected)
    allowed = tmp_path / "allowed.txt"
    allowed.write_text(f"test {Path(f'{key}.pub').read_text().strip()}\n")
    sigfile = tmp_path / "sig"
    sigfile.write_text(sig)
    v = subprocess.run(
        [
            "ssh-keygen",
            "-Y",
            "verify",
            "-f",
            str(allowed),
            "-I",
            "test",
            "-n",
            "git",
            "-s",
            str(sigfile),
        ],
        input=payload,
        capture_output=True,
    )
    assert v.returncode == 0, v.stderr.decode()


# ── integration: payload matches what git itself signs ──────────────────────


def test_payload_matches_git_own_signature(mod, tmp_path):
    """Create a real signed commit locally; our payload must equal git's
    signed bytes (the commit object minus the gpgsig header)."""
    key = tmp_path / "k"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
        check=True,
        capture_output=True,
    )
    repo = tmp_path / "repo3"
    repo.mkdir()
    for cmd in (
        ["git", "init", "-q", str(repo)],
        ["git", "-C", str(repo), "config", "user.name", "Test User"],
        ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
        ["git", "-C", str(repo), "config", "user.signingkey", str(key)],
        ["git", "-C", str(repo), "config", "gpg.format", "ssh"],
        ["git", "-C", str(repo), "config", "commit.gpgsign", "true"],
    ):
        subprocess.run(cmd, check=True, capture_output=True)
    (repo / "f.txt").write_text("hello")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "signed commit\n\nbody line\n"],
        check=True,
        capture_output=True,
    )

    # local commit facts
    tree = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD^{tree}"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    author_iso = subprocess.run(
        ["git", "-C", str(repo), "log", "-1", "--format=%aI"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    committer_iso = subprocess.run(
        ["git", "-C", str(repo), "log", "-1", "--format=%cI"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    message_raw = subprocess.run(
        ["git", "-C", str(repo), "log", "-1", "--format=%B"],
        capture_output=True,
        text=True,
    ).stdout
    # normalize like the implementation: %B appends one newline beyond the
    # stored message; the stored form is exactly one trailing newline
    message = message_raw.rstrip("\n") + "\n" if message_raw.strip() else ""

    raw = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "commit", "HEAD"],
        capture_output=True,
        text=True,
    ).stdout
    assert "gpgsig" in raw, "precondition: commit is signed"

    # our canonical payload (root commit, no parents)
    a_unix, a_tz = mod.iso_to_unix_tz(author_iso)
    c_unix, c_tz = mod.iso_to_unix_tz(committer_iso)
    payload = mod.build_canonical_payload(
        tree=tree,
        parents=[],
        message=message,
        author=("Test User", "test@example.com", a_unix, a_tz),
        committer=("Test User", "test@example.com", c_unix, c_tz),
    )

    # git's signed bytes: headers (before gpgsig) + blank line + message
    # (the gpgsig header sits between the headers and the message; the
    # signature covers headers + "\n\n" + message)
    headers_end = raw[: raw.index("gpgsig ")]
    message_part = raw[raw.index("gpgsig ") :]
    message_part = message_part[
        message_part.index("-----END SSH SIGNATURE-----") + len("-----END SSH SIGNATURE-----") :
    ]
    git_payload = headers_end + message_part.lstrip("\n")
    # headers_end already ends with a newline; git's payload has ONE blank
    # line (i.e. "\n\n") between committer and message
    git_payload = headers_end.rstrip("\n") + "\n\n" + message_part.lstrip("\n")

    assert payload == git_payload
