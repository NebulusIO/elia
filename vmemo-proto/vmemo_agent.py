#!/usr/bin/env python3
"""
vmemo_agent.py — local-first Voice Memos watcher.
- Watches the Voice Memos Group Container for new .m4a files
- Extracts Apple's transcript from the "trsp" atom when present
- If missing, optionally transcribes with whisper-cpp (if installed)
- Generates a compact title, copies audio + writes transcript/metadata
- (Optional) Best-effort AppleScript rename inside the app UI
"""

import os, sys, time, json, shutil, subprocess, re, struct, datetime, pathlib, hashlib
from typing import Any, BinaryIO, Dict, List, Tuple

HOME = pathlib.Path.home()
APP_DIR = HOME / "Library" / "Application Support" / "vmemo"
STATE_PATH = APP_DIR / "state.json"
CONF_PATH = APP_DIR / "config.yaml"

DEFAULTS = {
    "recordings_dir": str(HOME / "Library" / "Group Containers" / "group.com.apple.VoiceMemos.shared" / "Recordings"),
    "out_dir": str(HOME / "VoiceMemos" / "Processed"),
    "rename_in_app": False,
    "title_words": 8,
    "whispercpp_path": "whisper-cpp",
    "whisper_model": str(HOME / "Library" / "Application Support" / "vmemo" / "models" / "ggml-base.en.bin"),
    "language": "en",
}

def load_config() -> Dict[str, Any]:
    d = DEFAULTS.copy()
    try:
        import yaml  # If user has PyYAML, great; otherwise parse trivially
        with open(CONF_PATH, "r") as f:
            cfg = yaml.safe_load(f) or {}
        d.update(cfg or {})
    except Exception:
        # Super-simple parser: key: value
        if CONF_PATH.exists():
            for line in CONF_PATH.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or ":" not in line:
                    continue
                k, v = line.split(":", 1)
                d[k.strip()] = v.strip().strip('"').strip("'")
    # Expand ~
    for k in ("recordings_dir", "out_dir", "whispercpp_path", "whisper_model"):
        if k in d and isinstance(d[k], str):
            d[k] = os.path.expanduser(d[k])
    return d

def load_state() -> Dict[str, Any]:
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {"processed": {}}

def save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))

def file_signature(p: pathlib.Path) -> str:
    st = p.stat()
    h = hashlib.sha1()
    h.update(str(p).encode())
    h.update(str(st.st_size).encode())
    h.update(str(int(st.st_mtime)).encode())
    return h.hexdigest()

def find_new_recordings(cfg: Dict[str, Any], state: Dict[str, Any]) -> List[Tuple[pathlib.Path, str]]:
    root = pathlib.Path(cfg["recordings_dir"]).expanduser()
    if not root.exists():
        return []
    files = sorted(root.glob("*.m4a"), key=lambda p: p.stat().st_mtime, reverse=True)
    new: List[Tuple[pathlib.Path, str]] = []
    for p in files:
        sig = file_signature(p)
        if sig not in state["processed"]:
            new.append((p, sig))
    return new

def wait_until_stable(p: pathlib.Path, timeout: int = 30, interval: float = 0.5) -> bool:
    deadline = time.time() + timeout
    last = -1
    while time.time() < deadline:
        sz = p.stat().st_size
        if sz == last and sz > 0:
            return True
        last = sz
        time.sleep(interval)
    return False

# ---- MP4 atom scanning to find "trsp" ----

def read_atom(f: BinaryIO) -> Tuple[int | None, str | None, int | None]:
    header = f.read(8)
    if len(header) < 8:
        return None, None, None
    size, atype = struct.unpack(">I4s", header)
    if size == 1:  # 64-bit size
        largesize = f.read(8)
        if len(largesize) < 8:
            return None, None, None
        (size64,) = struct.unpack(">Q", largesize)
        hlen = 16
        return size64, atype.decode("latin-1"), hlen
    else:
        return size, atype.decode("latin-1"), 8

def extract_trsp_json(path: pathlib.Path) -> str | None:
    with path.open("rb") as f:
        filesize = path.stat().st_size
        pos = 0
        while pos < filesize:
            r = read_atom(f)
            if r[0] is None: break
            size, atype, hlen = r
            data_len = int(size) - hlen
            if data_len < 0: break
            if atype == "trsp":
                data = f.read(data_len)
                # Sometimes trailing zeros; strip
                try:
                    # Find first '{' and last '}' to bound JSON
                    s = data.decode("utf-8", errors="ignore")
                    start = s.find("{")
                    end = s.rfind("}")
                    if start != -1 and end != -1 and end > start:
                        return s[start:end+1]
                except Exception:
                    pass
                return None
            else:
                f.seek(data_len, 1)
            pos = f.tell()
    return None

def flatten_trsp_text(trsp_json: str) -> str:
    try:
        obj = json.loads(trsp_json)
        parts = obj.get("attributedString", [])
        out = []
        for item in parts:
            if isinstance(item, str):
                out.append(item.strip())
        text = " ".join(out)
        # collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text
    except Exception:
        return ""

def transcribe_with_whisper_cpp(cfg: Dict[str, Any], path: pathlib.Path) -> str | None:
    exe = cfg.get("whispercpp_path", "whisper-cpp")
    model = cfg.get("whisper_model")
    lang = cfg.get("language", "en")
    if not shutil.which(exe):
        return None
    if not model or not pathlib.Path(model).expanduser().exists():
        return None
    # Use ffmpeg to pipe 16kHz mono WAV to whisper-cpp for better reliability
    cmd = [
        "bash", "-lc",
        f"""ffmpeg -loglevel error -y -i \"{path}\" -ar 16000 -ac 1 -f wav - | """
        f"""GGML_METAL_PATH_RESOURCES=\"$(brew --prefix whisper-cpp 2>/dev/null)/share/whisper-cpp\" """
        f"""{exe} --model \"{model}\" --language {lang} --output-txt --output-file - -"""
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60*15)
        if res.returncode == 0 and res.stdout:
            # whisper-cpp prints transcript to stdout with timestamps; strip if needed
            txt = res.stdout
            # remove timestamps like [00:00:00.000 --> 00:00:01.000]
            txt = re.sub(r"\[\d{2}:\d{2}:\d{2}\.\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}\.\d{3}\]\s*", "", txt)
            txt = re.sub(r"\s+", " ", txt).strip()
            return txt
    except Exception as e:
        pass
    return None

def slugify_title(s: str, max_words: int = 8) -> str:
    if not s:
        return ""
    # Keep alphanumerics and spaces
    s = re.sub(r"[^A-Za-z0-9' ]+", " ", s)
    # collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    # split and cap words
    words = s.split()[:max_words]
    title = " ".join(words)
    # Capitalize first letter
    if title:
        title = title[0].upper() + title[1:]
    # file-safe slug
    slug = re.sub(r"[^\w\- ]", "", title).strip()
    slug = re.sub(r"\s+", " ", slug)
    return slug

def export_artifacts(
    cfg: Dict[str, Any],
    src: pathlib.Path,
    title: str,
    transcript_txt: str,
    trsp_json: str | None,
) -> Tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    out_root = pathlib.Path(cfg["out_dir"]).expanduser()
    date_folder = datetime.datetime.fromtimestamp(src.stat().st_mtime).strftime("%Y-%m-%d")
    folder = out_root / date_folder
    folder.mkdir(parents=True, exist_ok=True)

    # Prefix with timestamp to avoid collisions
    ts = datetime.datetime.fromtimestamp(src.stat().st_mtime).strftime("%Y%m%d-%H%M%S")
    base = f"{ts} — {title or 'Untitled'}".strip()
    base = re.sub(r"[/\\:]+", "—", base)  # safety

    audio_dst = folder / f"{base}.m4a"
    txt_dst = folder / f"{base}.txt"
    json_dst = folder / f"{base}.json"

    if not audio_dst.exists():
        shutil.copy2(src, audio_dst)
    txt_dst.write_text((transcript_txt or "").strip() + "\n")
    meta = {
        "source_path": str(src),
        "exported_path": str(audio_dst),
        "created": ts,
        "title": title,
        "transcript_chars": len(transcript_txt or ""),
        "has_native_trsp": bool(trsp_json),
    }
    if trsp_json:
        meta["native_trsp"] = json.loads(trsp_json)
    json_dst.write_text(json.dumps(meta, indent=2))
    return audio_dst, txt_dst, json_dst

def attempt_in_app_rename(new_title: str) -> bool:
    scpt = APP_DIR / "vmemo_rename.applescript"
    if not scpt.exists():
        return False
    try:
        subprocess.run(["osascript", str(scpt), new_title], check=False)
        return True
    except Exception:
        return False

def process_one(cfg: Dict[str, Any], path: pathlib.Path) -> Tuple[bool, str]:
    # Wait until file stops growing
    if not wait_until_stable(path):
        return False, "file-not-stable"

    trsp_json = extract_trsp_json(path)
    if trsp_json:
        transcript_txt = flatten_trsp_text(trsp_json)
    else:
        transcript_txt = None

    if not transcript_txt:
        # fallback to whisper-cpp if available
        transcript_txt = transcribe_with_whisper_cpp(cfg, path)

    # Title heuristic
    title = slugify_title(transcript_txt or "", cfg.get("title_words", 8))
    if not title:
        # Use date + duration fallback (no duration without parsing m4a deeper, use size)
        title = "Voice Memo"

    # Export artifacts
    audio_dst, txt_dst, json_dst = export_artifacts(cfg, path, title, transcript_txt or "", trsp_json)

    # Optional rename in app
    if cfg.get("rename_in_app"):
        attempt_in_app_rename(title)

    return True, str(audio_dst)

def main() -> None:
    cfg = load_config()
    state = load_state()

    # One-shot mode (for CI/testing)
    if "--once" in sys.argv:
        new = find_new_recordings(cfg, state)
        for p, sig in new:
            ok, info = process_one(cfg, p)
            if ok:
                state["processed"][sig] = {"ts": int(time.time()), "path": str(p)}
                save_state(state)
                print(f"Processed: {p} -> {info}")
        return

    print("vmemo_agent starting...")
    while True:
        try:
            new = find_new_recordings(cfg, state)
            for p, sig in new:
                ok, info = process_one(cfg, p)
                if ok:
                    state["processed"][sig] = {"ts": int(time.time()), "path": str(p)}
                    save_state(state)
                    print(f"Processed: {p} -> {info}")
            time.sleep(5)
        except Exception as e:
            print("Error:", e, file=sys.stderr)
            time.sleep(5)

if __name__ == "__main__":
    main()
