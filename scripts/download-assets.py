"""Download pinned public assets; verify upstream LFS/release SHA256 values."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
REPO="stable-diffusion-v1-5/stable-diffusion-v1-5"
REV="451f4fe16113bff5a5d2269ed5ad43b0592e9a14"


def fetch_once(url, target, digest=None):
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.is_file():
        with target.open("rb") as stream: actual=hashlib.file_digest(stream,"sha256").hexdigest()
        if not digest or actual==digest:
            print("Cached:",target.name,flush=True); return
    part=target.with_name(target.name+".part")
    offset=part.stat().st_size if part.exists() else 0
    request=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0",**({"Range":f"bytes={offset}-"} if offset else {})})
    with urllib.request.urlopen(request,timeout=60) as response:
        mode="ab" if offset and response.status==206 else "wb"
        total=offset if mode=="ab" else 0; last=time.monotonic()
        with part.open(mode) as stream:
            while chunk:=response.read(1024*1024):
                stream.write(chunk); total+=len(chunk)
                if time.monotonic()-last>20:
                    print(f"{target.name}: {total/1024**2:.0f} MiB",flush=True); last=time.monotonic()
    with part.open("rb") as stream: actual=hashlib.file_digest(stream,"sha256").hexdigest()
    if digest and actual!=digest: raise ValueError(f"Checksum mismatch: {target}")
    part.replace(target); print("Verified:",target.name,actual,flush=True)


def fetch(url,target,digest=None):
    for attempt in range(8):
        try: return fetch_once(url,target,digest)
        except (OSError,TimeoutError) as exc:
            print(f"Retry {attempt+1}/8: {target.name}: {type(exc).__name__}",flush=True)
            if attempt==7: raise
            time.sleep(min(2**attempt,20))


def fetch_large(url,target,digest,size):
    """Parallel bounded HTTP ranges; existing sequential prefix is retained."""
    if target.is_file(): return fetch(url,target,digest)
    target.parent.mkdir(parents=True,exist_ok=True)
    part=target.with_name(target.name+".part")
    chunks=target.with_name(target.name+".chunks"); chunks.mkdir(exist_ok=True)
    layout=chunks/"layout.json"
    if layout.exists(): prefix=json.loads(layout.read_text())["prefix"]
    else:
        prefix=part.stat().st_size if part.exists() else 0
        layout.write_text(json.dumps({"prefix":prefix,"size":size}),encoding="utf-8")
    def block(bounds):
        start,end=bounds; dest=chunks/str(start)
        for attempt in range(8):
            offset=dest.stat().st_size if dest.exists() else 0
            if offset==end-start+1: return
            try:
                request=urllib.request.Request(url,headers={"Range":f"bytes={start+offset}-{end}","User-Agent":"Mozilla/5.0"})
                with urllib.request.urlopen(request,timeout=45) as r:
                    if r.status!=206 or not r.headers.get("Content-Range","").startswith(f"bytes {start+offset}-"):
                        raise ValueError("Server did not honor bounded range")
                    with dest.open("ab") as stream:
                        while data:=r.read(65536): stream.write(data)
                if dest.stat().st_size!=end-start+1: raise OSError("Incomplete range")
                print(f"Range verified: {start//1024**2}-{end//1024**2} MiB",flush=True); return
            except OSError:
                if attempt==7: raise
                time.sleep(min(2**attempt,10))
    step=16*1024**2
    bounds=[(start,min(start+step,size)-1) for start in range(prefix,size,step)]
    with ThreadPoolExecutor(max_workers=8) as pool: list(pool.map(block,bounds))
    with part.open("r+b" if part.exists() else "w+b") as stream:
        stream.truncate(prefix); stream.seek(prefix)
        for start,end in bounds:
            with (chunks/str(start)).open("rb") as source: shutil.copyfileobj(source,stream)
    with part.open("rb") as stream: actual=hashlib.file_digest(stream,"sha256").hexdigest()
    if actual!=digest: raise ValueError("Large model checksum mismatch")
    part.replace(target)
    for start,end in bounds: (chunks/str(start)).unlink()
    layout.unlink(); chunks.rmdir()
    print("Verified:",target.name,actual,flush=True)


def main():
    p=argparse.ArgumentParser(); p.add_argument("--only",choices=["all","fds","sd15","yolo","fid","blender"],default="all"); a=p.parse_args()
    if a.only in {"all","blender"}:
        fetch_large("https://download.blender.org/release/Blender4.5/blender-4.5.3-linux-x64.tar.xz",ROOT/"engines/downloads/blender.tar.xz","975c58fcb244273838534bba771e64ad87739216b0f9b39a888531a49a72d845",377397328)
    if a.only in {"all","fds"}:
        fetch("https://github.com/firemodels/fds/releases/download/FDS-6.11.1/FDS-6.11.1_SMV-6.11.2_lnx.sh",ROOT/"engines/downloads/fds.sh","ba8793b974150fdb778b3db0b69ab8db4e4668d5c52987a317e7f5ed58102ea0")
    if a.only in {"all","yolo"}:
        url="https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt"
        target=ROOT/"models/yolo11n.pt"; fetch(url,target,"0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1")
        with target.open("rb") as stream: digest=hashlib.file_digest(stream,"sha256").hexdigest()
        target.with_suffix(".provenance.json").write_text(json.dumps({"url":url,"sha256":digest,"role":"generic_COCO_initialization_not_fire_finetuned"},indent=2),encoding="utf-8")
    if a.only in {"all","fid"}:
        name="pt_inception-2015-12-05-6726825d.pth"
        url=f"https://github.com/mseitzer/pytorch-fid/releases/download/fid_weights/{name}"
        target=ROOT/"artifacts/torch-cache/hub/checkpoints"/name; fetch(url,target,"6726825d0af5f729cebd5821db510b11b1cfad8faad88a03f1befd49fb9129b2")
        with target.open("rb") as stream: digest=hashlib.file_digest(stream,"sha256").hexdigest()
        if not digest.startswith("6726825d"): raise ValueError("FID upstream hash prefix mismatch")
        target.with_suffix(".provenance.json").write_text(json.dumps({"url":url,"sha256":digest},indent=2),encoding="utf-8")
    if a.only in {"all","sd15"}:
        metadata=ROOT/"models/sd15/upstream.json"
        fetch(f"https://huggingface.co/api/models/{REPO}/revision/{REV}?blobs=true",metadata)
        info=json.loads(metadata.read_text(encoding="utf-8"))
        small={"model_index.json","feature_extractor/preprocessor_config.json","scheduler/scheduler_config.json","tokenizer/merges.txt","tokenizer/vocab.json","tokenizer/tokenizer_config.json","tokenizer/special_tokens_map.json","safety_checker/config.json","text_encoder/config.json","unet/config.json","vae/config.json","README.md","LICENSE","LICENSE.md"}
        files=[x for x in info["siblings"] if x["rfilename"] in small or x["rfilename"] in {"safety_checker/model.fp16.safetensors","text_encoder/model.fp16.safetensors","unet/diffusion_pytorch_model.fp16.safetensors","vae/diffusion_pytorch_model.fp16.safetensors"}]
        def download(item):
            name=item["rfilename"]
            url=f"https://huggingface.co/{REPO}/resolve/{REV}/{name}"
            lfs=item.get("lfs",{})
            if item.get("size",0)>1024**3: fetch_large(url,ROOT/"models/sd15"/name,lfs["sha256"],item["size"])
            else: fetch(url,ROOT/"models/sd15"/name,lfs.get("sha256"))
        with ThreadPoolExecutor(max_workers=3) as pool: list(pool.map(download,files))
        (ROOT/"models/sd15/provenance.json").write_text(json.dumps({"repository":REPO,"revision":REV,"files":files},indent=2),encoding="utf-8")


if __name__=="__main__": main()
