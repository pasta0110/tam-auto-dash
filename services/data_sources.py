from __future__ import annotations

import json
import os
from io import BytesIO

import pandas as pd
import requests


class LocalCsvSource:
    def read_csv(self, path: str) -> pd.DataFrame:
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)

    def read_json(self, path: str) -> dict:
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def mtime(self, path: str):
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        return os.path.getmtime(path)


class GithubRawSource:
    def __init__(self, timeout: int = 20):
        self.timeout = timeout

    def read_csv(self, url: str) -> pd.DataFrame:
        resp = requests.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return pd.read_csv(BytesIO(resp.content), encoding="utf-8-sig", low_memory=False)

    def read_json(self, url: str) -> dict:
        resp = requests.get(url, timeout=min(self.timeout, 15))
        resp.raise_for_status()
        return resp.json()

    def head_meta(self, url: str) -> dict:
        r = requests.head(url, timeout=10, allow_redirects=True)
        return {"last_modified": r.headers.get("Last-Modified"), "etag": r.headers.get("ETag")}

    def github_last_commit_time(self, owner: str, repo: str, path: str) -> str | None:
        api = f"https://api.github.com/repos/{owner}/{repo}/commits"
        r = requests.get(api, params={"path": path, "per_page": 1}, timeout=15)
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        return data[0]["commit"]["committer"]["date"]


class RepositoryDataSource:
    def __init__(self, local: LocalCsvSource | None = None, remote: GithubRawSource | None = None):
        self.local = local or LocalCsvSource()
        self.remote = remote or GithubRawSource()

    @staticmethod
    def _exc_text(exc: Exception) -> str:
        return f"{type(exc).__name__}: {exc}"

    def load_csv_with_diagnostics(self, local_path: str, remote_url: str) -> tuple[pd.DataFrame | None, dict]:
        diag = {
            "selected_source": None,
            "local_path": local_path,
            "remote_url": remote_url,
            "local_error": None,
            "remote_error": None,
        }
        try:
            df = self.local.read_csv(local_path)
            diag["selected_source"] = "local"
            return df, diag
        except Exception as e_local:
            diag["local_error"] = self._exc_text(e_local)

        try:
            df = self.remote.read_csv(remote_url)
            diag["selected_source"] = "remote"
            return df, diag
        except Exception as e_remote:
            diag["remote_error"] = self._exc_text(e_remote)
            return None, diag

    def load_csv_prefer_local(self, local_path: str, remote_url: str) -> tuple[pd.DataFrame, str]:
        try:
            return self.local.read_csv(local_path), "local"
        except Exception:
            return self.remote.read_csv(remote_url), "remote"

    def load_json_prefer_local(self, local_path: str, remote_url: str) -> tuple[dict, str]:
        try:
            return self.local.read_json(local_path), "local"
        except Exception:
            return self.remote.read_json(remote_url), "remote"
