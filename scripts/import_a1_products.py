"""從鼎新A1「商品資料_Excel匯入格式」匯出的 Excel，匯入到本系統的 Product 資料表。

比對主鍵用「品號」（對應 Product.code1）——因為這批匯出裡有將近一半的商品
沒有條碼編號，barcode 不能拿來當唯一比對依據。已存在的商品（code1 相同）
會被更新，不存在的會新增。分類、單位會依名稱自動建立缺少的。

用法：
    python scripts/import_a1_products.py <匯出的xlsx路徑> [--dry-run]

--dry-run 只印出會做什麼變更，不會真的寫入資料庫。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import openpyxl

from app import create_app
from extensions import db
from models import Product, Category, Unit


def load_rows(xlsx_path):
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0][1:]  # 第一欄是空的標籤欄，忽略
    data_rows = rows[3:]  # 前兩列是「此列請勿刪除」的說明列
    records = []
    for r in data_rows:
        rec = dict(zip(header, r[1:]))
        if not rec.get("品號"):
            continue
        records.append(rec)
    return records


def get_or_create_category(name):
    if not name:
        return None
    cat = Category.query.filter_by(name=name).first()
    if not cat:
        cat = Category(name=name)
        db.session.add(cat)
        db.session.flush()
    return cat


def get_or_create_unit(name):
    name = name or "個"
    unit = Unit.query.filter_by(name=name).first()
    if not unit:
        unit = Unit(name=name)
        db.session.add(unit)
        db.session.flush()
    return unit


def to_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def to_int(v, default=0):
    try:
        return int(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("xlsx_path")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        records = load_rows(args.xlsx_path)
        print(f"讀到 {len(records)} 筆商品資料")

        created, updated, skipped = 0, 0, 0

        for rec in records:
            code1 = str(rec["品號"]).strip()
            name = (rec.get("品名") or "").strip()
            if not name:
                skipped += 1
                continue

            barcode = rec.get("條碼編號")
            barcode = str(barcode).strip() if barcode else None

            category = get_or_create_category(rec.get("商品分類"))
            unit = get_or_create_unit(rec.get("單位"))

            price = to_float(rec.get("零售價"))
            cost = to_float(rec.get("標準進價"))
            safety_stock = to_int(rec.get("安全存量"))
            stock = to_int(rec.get("庫存數量"))
            is_active = rec.get("停售日期") in (None, "")

            existing = Product.query.filter_by(code1=code1).first()
            # barcode 唯一，若這個條碼已經被「別的」商品用掉，就不要覆蓋，避免撞唯一鍵
            if barcode:
                barcode_owner = Product.query.filter_by(barcode=barcode).first()
                if barcode_owner and barcode_owner.code1 != code1:
                    barcode = None

            if existing:
                if not args.dry_run:
                    existing.name = name
                    existing.barcode = barcode
                    existing.category_id = category.id if category else None
                    existing.unit_id = unit.id if unit else None
                    existing.price = price
                    existing.cost = cost
                    existing.safety_stock = safety_stock
                    existing.stock = stock
                    existing.is_active = is_active
                updated += 1
            else:
                if not args.dry_run:
                    db.session.add(Product(
                        code1=code1,
                        barcode=barcode,
                        name=name,
                        category_id=category.id if category else None,
                        unit_id=unit.id if unit else None,
                        price=price,
                        cost=cost,
                        safety_stock=safety_stock,
                        stock=stock,
                        is_active=is_active,
                    ))
                created += 1

        if args.dry_run:
            print(f"[dry-run] 會新增 {created} 筆、更新 {updated} 筆、略過 {skipped} 筆（沒有商品名稱）")
        else:
            db.session.commit()
            print(f"完成：新增 {created} 筆、更新 {updated} 筆、略過 {skipped} 筆")


if __name__ == "__main__":
    main()
