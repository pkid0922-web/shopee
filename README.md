# 雲端進銷存系統

將現有本機端 ERP（[`G:/我的雲端硬碟/ERP`](../../ERP)，Flask + SQLite）雲端化，並與蝦皮出貨工作台（Chrome 擴充功能）直接串接，讓進貨、銷貨、庫存、蝦皮訂單同步都在雲端集中管理。

## 現況盤點（本專案的起點）

專案不是從零開始，而是在既有兩套工具上整合：

### 1. 既有 ERP（待雲端化）— `G:/我的雲端硬碟/ERP`
Flask + SQLAlchemy + SQLite，模組已經相當完整：
- **基礎資料**：商品 `Product`、供應商 `Vendor`、客戶 `Customer`、員工 `Employee`、角色權限 `Role`、分類 `Category`、單位 `Unit`、公司資料 `CompanyProfile`
- **銷售**：`SalesOrder` / `SalesOrderItem`、揀貨單 `PickingSlip`、代出貨單 `DropShipOrder`、銷貨退回 `ReturnOrder`
- **採購**：`PurchaseOrder`、請購單 `PurchaseRequest`、進貨退出 `PurchaseReturnOrder`
- **財務**：應收付款紀錄 `PaymentRecord` / `VendorPaymentRecord`、發票紀錄 `InvoiceRecord`、固定支出 `FixedExpense`、月結（`billing_year` / `billing_month`）
- 路由拆成 `routes/basics.py`、`sales.py`、`purchases.py`、`finance.py`，以 Jinja 模板渲染頁面

### 2. 蝦皮訂單擷取 — 出貨工作台（Chrome 擴充功能）— `蝦皮數據/蝦皮訂單擷取`
Manifest V3 擴充功能，在 `seller.shopee.tw` 頁面上運作：
- `capture.js` / `content.js`：側錄蝦皮賣家中心的 API 呼叫，擷取待出貨訂單
- `background.js`：整理訂單資料、可直接呼叫蝦皮 API 執行出貨（`ship` 指令）
- `bridge.js`：讓 **claude.ai** 網頁能透過 `postMessage` 呼叫擴充功能（讀訂單 / 觸發出貨），目前是「Claude 對話頁 + 擴充功能」組成工作台
- 目前多店鋪並行：已看到 `shop_id` 1254814115、534500855、1803879515 三家蝦皮店鋪的資料
- 訂單資料含 `order_sn`（訂單編號）、`package_number`（包裹號）、商品明細（`item_id`/`model_id`/名稱/數量）、`payment_info`（金額、付款方式）、`status_info`（狀態、出貨期限 `ship_by_date`）等

## 整合方向（已確認）

1. **取代並雲端化既有 ERP**：把 `G:/ERP` 的資料模型搬到雲端資料庫，功能延續、介面重做，等於既有系統的雲端升級版，而不是另起一套平行系統。
2. **蝦皮工作台直接呼叫新系統 API**：在擴充功能裡新增「同步到雲端系統」動作，擷取到訂單後直接 `POST` 到新系統的訂單匯入 API，即時、不用手動搬資料。原本 `orders.json` 匯出與 claude.ai bridge 的功能保留備用，但不是主要路徑。

## 技術架構（建議）

沿用 Flask/Python（風險最低、可直接搬遷既有 models 與路由邏輯），把「本機」的部分換成「雲端」：

| 項目 | 現況（本機） | 雲端化後 |
|---|---|---|
| 後端框架 | Flask | Flask（保留，模組化為 API + 頁面） |
| ORM | SQLAlchemy | SQLAlchemy（不變） |
| 資料庫 | SQLite（本機檔案） | PostgreSQL（雲端代管，如 Railway / Render / Supabase） |
| 部署 | 本機執行 | Railway / Render / Fly.io（Flask 常見選擇） |
| 認證 | Flask-Login | Flask-Login（不變），加上給擴充功能用的 API Key |
| 蝦皮對接 | 擴充功能側錄 + 手動匯出 | 擴充功能直接呼叫雲端 API（見下） |

> 如果之後想要更現代化的前端（React/Next.js），可以之後把 Flask 縮成純 API，前端另外重寫；但第一步先求「能動、能上雲、資料不遺失」。

## 蝦皮工作台對接 API（規劃）

新增一組給擴充功能呼叫的 REST API，用 API Key（每個蝦皮店鋪一把）驗證：

- `POST /api/shopee/orders/sync`
  擴充功能側錄到待出貨訂單後推送，內容含 `shop_id`、`order_sn`、`package_number`、商品明細（`item_id`/`model_id`/數量/單價）、買家資訊、`ship_by_date`。後端依 `order_sn` upsert，自動建立/更新 `SalesOrder`，比對商品（用 `item_id`/`model_id` 對應 `Product.code1`/`code2` 或條碼）並扣減庫存。
- `POST /api/shopee/shipments/report`
  出貨完成後回報物流單號 / 出貨狀態，更新對應 `SalesOrder` 狀態。
- 多店鋪：每筆訂單都帶 `shop_id`，新系統需支援「一個帳號管理多個蝦皮店鋪」，商品與庫存視需求決定是否分店鋪或共用。

## 開發階段規劃

1. **第一階段：雲端化既有 ERP**
   資料庫改用 PostgreSQL，部署到雲端主機，確認登入、商品、銷貨、採購、庫存、財務功能都能在雲端正常運作（等於「搬家」）。
2. **第二階段：蝦皮同步 API**
   新增 `/api/shopee/*` 端點與 API Key 機制，擴充功能改用直接推送，訂單自動變成 `SalesOrder` 並扣庫存。
3. **第三階段：出貨回寫與多店鋪管理**
   出貨結果回寫、多店鋪視覺化管理、低庫存警示、毛利報表強化。
4. **第四階段（視需求）**：前端現代化、更多通路整合。

## 專案結構（骨架已建立）

```
shopee/
├── app.py                  # Flask app factory + 入口（本機跑 / gunicorn 都用這支）
├── config.py                # 讀 DATABASE_URL（沒設就退回本機 SQLite）
├── extensions.py             # db / login_manager / migrate 共用實例
├── models.py                 # 沿用既有 ERP 的 SQLAlchemy models，新增 ShopeeShop / ShopeeOrderRaw
├── routes/
│   ├── auth.py               # 登入 / 登出（已可動）
│   ├── basics.py             # 總覽頁（已可動，讀真實資料庫統計）
│   ├── sales.py / purchases.py / finance.py   # 佔位頁，業務邏輯待下一階段實作
│   └── api_shopee.py         # 蝦皮工作台對接 API（已可動：ping / orders/sync）
├── templates/                 # layout / login / dashboard / stub
├── scripts/seed.py            # 建表 + 建立第一個管理員帳號
├── requirements.txt
├── .env.example
├── Procfile                   # Railway 部署用（web + release migrate）
└── docs/                      # 系統設計文件（之後補）
```

**目前已經可以跑起來的部分**（已本機驗證）：登入/登出、總覽頁讀資料庫、`/api/shopee/ping`、
`/api/shopee/orders/sync`（用 `X-API-Key` 驗證蝦皮賣場，依 `order_sn` upsert 進 `ShopeeOrderRaw`）。
銷售/採購/財務目前只有佔位頁，實際單據功能是下一步要討論、動工的部分。

## 開發環境設置

```bash
python -m venv .venv
./.venv/Scripts/python -m pip install -r requirements.txt
cp .env.example .env          # 本機開發可以不改，會自動用 SQLite

./.venv/Scripts/python scripts/seed.py   # 建表 + 建立管理員帳號 admin/admin123
./.venv/Scripts/python app.py             # 開發伺服器，預設 http://localhost:5000
```

部署到 Railway 時：新增一個 PostgreSQL 服務（Railway 會自動注入 `DATABASE_URL`），
設定 `SECRET_KEY` 環境變數，Railway 會用 `Procfile` 的 `web` / `release` 指令啟動。

## 待確認事項

- 蝦皮擴充功能的 API Key 要怎麼發放與儲存（目前規劃：每個蝦皮賣場一把，存在 `chrome.storage.local`）
- `ShopeeOrderRaw` 轉正式 `SalesOrder`（商品比對、扣庫存、成本計算）的業務規則
- 銷售 / 採購 / 財務三個模組要照原 ERP 邏輯搬過來，還是趁機重新設計流程

## 授權

內部使用專案，未定義開源授權條款。
