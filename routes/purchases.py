"""採購模組（骨架）。

對應既有 ERP 的 routes/purchases.py：採購單、請購單、進貨退出。
先放一個佔位頁面，實際功能之後再依討論結果搬過來 / 重寫。
"""
from flask import Blueprint, render_template
from flask_login import login_required

purchases_bp = Blueprint("purchases", __name__, url_prefix="/purchases")


@purchases_bp.route("/")
@login_required
def index():
    return render_template("stub.html", title="採購管理", note="採購單 / 請購單 / 進貨退出 — 待實作")
