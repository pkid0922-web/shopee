"""初始化資料庫：建表 + 建立第一個管理員帳號。

用法：
    python scripts/seed.py
會用環境變數 ADMIN_USERNAME / ADMIN_PASSWORD 建立管理員（沒設就用預設值 admin / admin123，
正式環境請務必用環境變數指定，或建立後立刻改密碼）。
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from werkzeug.security import generate_password_hash

from app import create_app
from extensions import db
from models import User, Role, CompanyProfile


def main():
    app = create_app()
    with app.app_context():
        db.create_all()

        if not Role.query.filter_by(name="admin").first():
            db.session.add(Role(
                name="admin",
                p_products=True, p_vendors=True, p_customers=True,
                p_sales=True, p_purchases=True, p_employees=True, p_finance=True,
            ))
            db.session.commit()

        admin_role = Role.query.filter_by(name="admin").first()
        username = os.environ.get("ADMIN_USERNAME", "admin")
        password = os.environ.get("ADMIN_PASSWORD", "admin123")

        if not User.query.filter_by(username=username).first():
            db.session.add(User(
                username=username,
                password=generate_password_hash(password),
                role_id=admin_role.id,
            ))
            print(f"已建立管理員帳號：{username} / {password}（請盡快登入後修改密碼）")
        else:
            print(f"帳號 {username} 已存在，略過建立")

        if not CompanyProfile.query.first():
            db.session.add(CompanyProfile(name="我的公司"))

        db.session.commit()
        print("資料庫初始化完成。")


if __name__ == "__main__":
    main()
