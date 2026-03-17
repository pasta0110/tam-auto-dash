from dataclasses import dataclass
import os


@dataclass
class RuntimeConfig:
    repo_path: str
    git_remote: str
    git_branch: str
    run_meta_path: str
    uploader_status_path: str
    lock_file_path: str


def build_runtime_config(repo_path: str | None = None, remote: str | None = None, branch: str | None = None) -> RuntimeConfig:
    default_repo = os.getenv("TDU_REPO_PATH", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    default_remote = os.getenv("TDU_GIT_REMOTE", "origin")
    default_branch = os.getenv("TDU_GIT_BRANCH", "main")
    final_repo = os.path.abspath(repo_path or default_repo)
    final_remote = (remote or default_remote).strip() or "origin"
    final_branch = (branch or default_branch).strip() or "main"
    return RuntimeConfig(
        repo_path=final_repo,
        git_remote=final_remote,
        git_branch=final_branch,
        run_meta_path=os.path.join(final_repo, "erp_run_meta.json"),
        uploader_status_path=os.path.join(final_repo, "uploader_status.json"),
        lock_file_path=os.path.join(final_repo, ".uploader.lock"),
    )
