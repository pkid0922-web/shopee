"""銷售模組（骨架）。

對應既有 ERP 的 routes/sales.py：銷貨單、揀貨單、代出貨單、銷貨退回。
先放一個佔位頁面，實際功能之後再依討論結果搬過來 / 重寫。
"""
from flask import Blueprint, render_template
from flask_login import login_required

sales_bp = Blueprint("sales", __name__, url_prefix="/sales")


@sales_bp.route("/")
@login_required
def index():
    return render_template("stub.html", title="銷售管理", note="銷貨單 / 揀貨單 / 代出貨單 / 銷貨退回 — 待實作")
