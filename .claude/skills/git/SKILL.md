---
name: git
description: "Git 提交流程：更新文檔並提交所有變更"
disable-model-invocation: true
user-invocable: true
allowed-tools: Bash(git:*), Bash(markdownlint-cli2:*), Read, Write, Edit, Grep, Glob, Task
---

# Git 提交流程

執行完整的 Git 提交流程，包含文檔更新。

## 檔案說明

- **README.md**: Repo 說明文件
- **CLAUDE.md**: AI 運作時參考的說明
- **CHANGELOG.md**: 紀錄變更

## 執行步驟

1. 分析 repo 目前的變更內容（git status, git diff）
2. **Code Review**（根據變更規模調整深度）
   - **檢查項目**：
     - 🔒 安全：硬編碼密碼/token、SQL injection、command injection、敏感資訊外洩
     - 🐛 邏輯：空值處理、邊界條件、錯誤處理、race condition
     - ⚡ 效能：N+1 查詢、無限迴圈風險、記憶體洩漏
     - 📝 風格：命名一致性、死碼、過度複雜
   - **處理方式**：
     - 小型變更（< 50 行）：直接檢查
     - 中型變更（50-200 行）：逐檔案檢查
     - 大型變更（> 200 行）：使用 Task tool 啟動獨立 review agent
   - **阻擋條件**（發現以下問題必須修復後才能提交）：
     - 硬編碼的密碼、API key、token
     - 明顯的安全漏洞
     - 會導致服務中斷的邏輯錯誤
   - **例外規則**：
     - CDN header 認證 key（x-origin-auth, X-CDN-Secret 等）可忽略，這些是業務配置而非敏感憑證
3. 根據變更內容更新相關文檔：
   - 新功能或重大變更，更新 README.md
   - 影響 AI 操作的變更，更新 CLAUDE.md
     - **自動精簡分析**：
       - 檢查是否有過時的範例或冗長說明可移除
       - 將重複的配置範例改為簡短參考
       - 移除已退役環境的詳細說明（保留列表即可）
       - 目標：維持 CLAUDE.md 在 600-700 行以內
   - 更新 CHANGELOG.md 記錄本次變更
4. 建立 Git commit，commit message 應清楚描述變更內容
5. 推送到遠端 repo（git-hook 已配置，scripts/githooks/pre-push.sh 在 push 前使用 trivy 檢查）

## 注意事項

- Commit message 使用繁體中文
- CHANGELOG.md 格式遵循 Keep a Changelog 規範
- 確保不提交任何機密資訊（密碼、金鑰等）
