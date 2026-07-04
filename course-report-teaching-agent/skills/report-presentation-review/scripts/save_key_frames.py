#!/usr/bin/env python3
"""Post-process a course-report-evaluation response: save each key-frame thumbnail
(base64) to an image FILE under the real outputs dir and replace the heavy base64 with
a compact `frame_path`, so the agent can drop the frames straight into the PDF gallery
without carrying ~20KB base64 blobs through its context.

Reads the raw JSON response on stdin, prints the rewritten JSON on stdout. Kept as a
standalone file (NOT an inline heredoc) because `curl | python3 - <<'PY'` makes the
heredoc win stdin, so the piped response never reaches the script.
"""

import base64
import json
import os
import sys


def main() -> int:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except Exception:
        # Not JSON (e.g. an error page) — pass through untouched so the caller still sees it.
        sys.stdout.write(raw)
        return 0

    # Desktop bundle chats run with REAL paths and reject the virtual /mnt mount, so
    # resolve the real outputs dir from ALLO_OUTPUTS_DIR (injected into the sandbox bash
    # env); fall back to the virtual path only when that env is absent (server mode).
    out_base = os.environ.get("ALLO_OUTPUTS_DIR") or "/mnt/user-data/outputs"
    out_dir = os.path.join(out_base, "关键帧证据")
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError:
        out_dir = None

    saved = 0
    images: list[dict] = []
    for dim in data.get("oral_assessable_dimensions") or []:
        if not isinstance(dim, dict):
            continue
        name = str(dim.get("dimension") or "维度")
        for kf in dim.get("key_frames") or []:
            if not isinstance(kf, dict):
                continue
            thumb = kf.get("thumbnail") or ""
            if isinstance(thumb, str) and thumb.startswith("data:") and out_dir:
                b64 = thumb.split(",", 1)[-1]
                raw_tc = str(kf.get("timecode") or "")
                tc = raw_tc.replace(":", "-") or "帧"
                fpath = os.path.join(out_dir, f"{name}_{tc}_{saved}.jpg")
                try:
                    with open(fpath, "wb") as fh:
                        fh.write(base64.b64decode(b64))
                    kf["frame_path"] = fpath
                    why = str(kf.get("why") or "").strip()
                    caption = f"**{name}** · {raw_tc}" + (f" · {why}" if why else "")
                    images.append({"data": fpath, "caption": caption})
                    saved += 1
                except Exception:
                    pass
            kf.pop("thumbnail", None)  # never echo the heavy base64

    # Write a READY-TO-USE PDF section object so the agent只需读它、原样塞进 report.json
    # 的 sections(放在雷达之前),不用自己逐张挑帧 —— 弱模型也不会漏帧。
    if out_dir and images:
        block = {"heading": "关键帧证据", "blocks": [{"type": "gallery", "cols": 2, "images": images}]}
        try:
            gb_path = os.path.join(out_dir, "gallery_block.json")
            with open(gb_path, "w", encoding="utf-8") as fh:
                json.dump(block, fh, ensure_ascii=False, indent=2)
            data["_gallery_block_path"] = gb_path
        except OSError:
            pass

    data["_key_frames_saved"] = saved
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
