"""从 HowToCook 的公开 LFS 对象库补齐菜谱原图，校验后原子替换指针。"""

import hashlib
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LFS_BATCH_URL = "https://github.com/Anduin2017/HowToCook.git/info/lfs/objects/batch"


def request_bytes(request):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def download_object(obj, paths):
    action = obj.get("actions", {}).get("download")
    if not action:
        raise RuntimeError(f"LFS 对象不可下载：{obj['oid']}，{obj.get('error', {})}")
    data = request_bytes(urllib.request.Request(action["href"], headers=action.get("header", {})))
    if len(data) != obj["size"] or hashlib.sha256(data).hexdigest() != obj["oid"]:
        raise RuntimeError(f"图片大小或 SHA-256 不匹配：{obj['oid']}")
    for path in paths:
        temporary = path.with_name(path.name + ".download")
        try:
            temporary.write_bytes(data)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return len(paths)


def main():
    manifest = json.loads((PROJECT_ROOT / "docs/upstream-manifest.json").read_text())
    originals = {entry["path"]: entry for entry in manifest["files"]}
    pending = {}
    restored = 0
    for relative, image in manifest["lfs_objects"].items():
        path = PROJECT_ROOT / relative
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        if digest == image["oid"]:
            restored += 1
            continue
        if digest is not None and digest != originals[relative]["sha256"]:
            raise RuntimeError(f"文件已被修改，为避免覆盖而停止：{relative}")
        path.parent.mkdir(parents=True, exist_ok=True)
        group = pending.setdefault(image["oid"], {"size": image["size"], "paths": []})
        group["paths"].append(path)
    print(f"已就绪 {restored} 张；待补齐 {sum(len(g['paths']) for g in pending.values())} 张", flush=True)
    objects = [{"oid": oid, "size": group["size"]} for oid, group in pending.items()]
    jobs = []
    for start in range(0, len(objects), 100):
        body = json.dumps({"operation": "download", "transfers": ["basic"], "objects": objects[start:start + 100]}).encode()
        request = urllib.request.Request(LFS_BATCH_URL, data=body, headers={
            "Accept": "application/vnd.git-lfs+json",
            "Content-Type": "application/vnd.git-lfs+json",
            "User-Agent": "all-in-rag-practice",
        })
        response = json.loads(request_bytes(request))
        batch = response.get("objects", [])
        if {o["oid"] for o in batch} != {o["oid"] for o in objects[start:start + 100]}:
            raise RuntimeError("LFS 返回的对象列表不完整")
        jobs.extend(batch)
    failures = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(download_object, obj, pending[obj["oid"]]["paths"]): obj["oid"] for obj in jobs}
        for future in as_completed(futures):
            try:
                restored += future.result()
                if restored % 25 == 0:
                    print(f"已校验并补齐 {restored} 张", flush=True)
            except Exception as error:
                # 下载 URL 可能含临时签名，只输出对象与异常类型。
                failures.append(futures[future])
                print(f"下载失败：{futures[future]}（{type(error).__name__}）", flush=True)
    if failures:
        raise SystemExit(f"{len(failures)} 个对象未完成；重新运行可继续下载，其余文件已保留。")
    print(f"完成：{restored} 张原图均已通过大小和 SHA-256 校验。", flush=True)


if __name__ == "__main__":
    main()
