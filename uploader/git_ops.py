import hashlib
import subprocess


def run(cmd: list[str], cwd: str | None = None, check: bool = True):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and result.returncode != 0:
        print(f"[ERROR] Command failed: {' '.join(cmd)}")
        if result.stdout:
            print("[stdout]")
            print(result.stdout.strip())
        if result.stderr:
            print("[stderr]")
            print(result.stderr.strip())
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(cmd)}")
    return result


def git_index_sha256(path: str, repo_path: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "show", f":{path}"],
            cwd=repo_path,
            capture_output=True,
            text=False,
        )
        if result.returncode != 0:
            return None
        return hashlib.sha256(result.stdout or b"").hexdigest()
    except Exception:
        return None


def git_sync(repo_path: str, remote: str, branch: str):
    run(["git", "fetch", remote, branch], cwd=repo_path, check=True)
    run(["git", "pull", "--rebase", "--autostash", remote, branch], cwd=repo_path, check=True)


def git_push_with_retry(repo_path: str, remote: str, branch: str):
    try:
        run(["git", "push", remote, branch], cwd=repo_path, check=True)
    except Exception:
        run(["git", "fetch", remote, branch], cwd=repo_path, check=True)
        run(["git", "pull", "--rebase", "--autostash", remote, branch], cwd=repo_path, check=True)
        run(["git", "push", remote, branch], cwd=repo_path, check=True)
