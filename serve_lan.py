"""公司內網伺服器啟動腳本。

用 waitress（純 Python、Windows 原生支援，正式環境用，
不像 Flask 內建開發伺服器那樣單執行緒、不穩定）把系統
綁在 0.0.0.0，同一個內網（辦公室 WiFi / 有線）裡的其他電腦
都可以用這台主機的區網 IP 連進來，例如 http://192.168.1.108:5000

用法：
    .venv\\Scripts\\python serve_lan.py
"""
import os

from waitress import serve

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"雲端進銷存系統（內網模式）啟動中，port={port}")
    print("同網段的其他電腦可以用這台主機的區網 IP 連進來，例如：")
    print(f"    http://<這台電腦的區網IP>:{port}")
    serve(app, host="0.0.0.0", port=port, threads=8)
