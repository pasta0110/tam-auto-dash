import hashlib
import os


def file_sha256(path: str):
    try:
        if not path or not os.path.exists(path):
            return None
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def meta_hash_status(meta_order_hash: str, meta_delivery_hash: str, order_path: str, delivery_path: str):
    if not (meta_order_hash and meta_delivery_hash):
        return None
    cur_o = file_sha256(order_path)
    cur_d = file_sha256(delivery_path)
    if not (cur_o and cur_d):
        return None
    return (cur_o == meta_order_hash) and (cur_d == meta_delivery_hash)

