"""財務模組（骨架）。

對應既有 ERP 的 routes/finance.py：應收應付、發票、月結、固定支出。
先放一個佔位頁面，實際功能之後再依討論結果搬過來 / 重寫。
"""
from flask import Blueprint, render_template
from flask_login import login_required

finance_bp = Blueprint("finance", __name__, url_prefix="/finance")


@finance_bp.route("/")
@login_required
def index():
    return render_template("stub.html", title="財務管理", note="應收應付 / 發票 / 月結 / 固定支出 — 待實作")
