"""stdio の線をそのまま書き写す中継 (ラボ 6)。

    python wire_tee.py <記録ファイル> <コマンド> [引数...]

ホスト (MCP の Client) ⇄ この中継 ⇄ 本物のサーバ、とつなぐ。中継は 1 行ずつ素通しし、
同じ行を記録ファイルに「→ (ホストからサーバへ)」「← (サーバからホストへ)」の印つきで書く。
中身には手を加えない (SDK が実際に送った JSON-RPC がそのまま残る)。
"""
from __future__ import annotations

import subprocess
import sys
import threading


def main() -> None:
    log_path, cmd = sys.argv[1], sys.argv[2:]
    child = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    log = open(log_path, "a", encoding="utf-8")
    lock = threading.Lock()

    def pump(src, dst, mark: str) -> None:
        for raw in iter(src.readline, b""):
            with lock:
                log.write(mark + " " + raw.decode("utf-8", "replace").rstrip("\r\n") + "\n")
                log.flush()
            dst.write(raw)
            dst.flush()
        try:
            dst.close()
        except OSError:
            pass

    up = threading.Thread(target=pump, args=(sys.stdin.buffer, child.stdin, "→"), daemon=True)
    down = threading.Thread(target=pump, args=(child.stdout, sys.stdout.buffer, "←"), daemon=True)
    up.start(); down.start()
    down.join()                      # サーバが閉じたら終わる
    child.wait()


if __name__ == "__main__":
    main()
