# 相机与镜头价格监控

本地运行的相机与镜头价格监控系统。它将报价字段标准化、保存 SQLite 历史记录，并明确区分国行、港行/水货、二手、套机、保修和现金价。对需要登录、验证码或人工确认的来源不会绕过安全机制，也不会把失败误报为采集成功。

## 当前能力

- 产品和别名配置：机身位于 `config/products.yaml`，Sony E 与 Canon RF 镜头位于独立的 `config/lenses.yaml`；可直接扩充。
- 港币原价和抓取当日人民币参考价分开保存；赠品不会被自动折算为现金降价。
- SQLite 报价历史、原始响应快照、日汇率、来源健康和持久化通知状态；异常低价需人工确认，不能成为可信历史低价。
- Price.com.hk、Canon 中国/香港、Sony 香港公开适配器；Price.com.hk 可区分水货/行货、现金价、保修、库存和独立商户。
- 可信分段历史、24h 至全部历史趋势、预测回测、促销/发布标记、二手 α1 筛选、市场对比与购买建议。
- 本地 FastAPI 暗色仪表盘；可设置产品、公开链接、采集频率、目标价、购买地区和事件；支持 Webhook、PushPlus、Telegram、邮件、Windows 桌面通知。

## Windows 本地运行

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
python -m pytest -v
python -m uvicorn camera_tracker.api:app --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000`，API 文档在 `http://127.0.0.1:8000/docs`。

在另一个 PowerShell 窗口启动后台采集（仅抓取 `config/watches.yaml` 中明确配置且公开可访问的页面）：

```powershell
python -m camera_tracker.worker
```

Worker 启动后会立即执行一轮已启用来源的采集，随后再按 `config/sources.yaml` 的间隔与随机抖动持续运行。

仅验证一轮公开来源、数据库写入和来源状态而不进入常驻模式：`python -m camera_tracker.worker --once`。

截至本次本地实测，默认公开配置可在一轮中写入 Canon 中国、Canon 香港、Canon 香港在线商城、Sony 香港和 Price.com.hk 的报价；页面限流或结构变化时仍以来源失败状态呈现，不保证外部页面始终可访问。

注册为登录后常驻的 Windows 任务（以项目根目录为当前目录执行）：

```powershell
.\scripts\Register-CameraPriceTrackerTask.ps1
Start-ScheduledTask -TaskName CameraPriceTrackerWorker
```

脚本会优先使用项目 `.venv\Scripts\python.exe`；如使用其他解释器，可传入 `-PythonExe "C:\path\to\python.exe"`。

查看任务：`Get-ScheduledTask -TaskName CameraPriceTrackerWorker`；删除任务：`Unregister-ScheduledTask -TaskName CameraPriceTrackerWorker -Confirm:$false`。

Worker 日志写入 `data/tracker.log`；Windows 上可用 `Get-Content .\data\tracker.log -Wait` 实时查看。Docker 部署仍使用 `docker compose logs -f`。

升级本地安装：停止 Worker/任务后执行 `git pull`、激活虚拟环境、运行 `pip install -e ".[dev]"` 和 `python -m pytest -q`，然后重新启动 API 与 Worker。升级前可先运行 `.scripts\Backup-CameraPriceTracker.ps1`。

对于京东、天猫、拼多多、闲鱼等存在登录墙或验证码的页面，请使用 API `POST /api/import/csv` 导入用户取得的报价，或等待平台公开接口；系统不会尝试绕过限制。

数据源状态页会在首次采集前列出配置中标记为“需要人工处理”的来源（如京东、天猫），并提示手动导入/公开接口的降级路径，不会把禁用或受限来源显示为采集成功。

二手导入 CSV 可选附加列为 `shutter_count`、`cosmetic_grade`、`packaging_status`、`warranty_remaining_days`。初代 α1 的二手专页可用最高预算与最高快门数筛选这些手动导入的可信报价。

仪表盘“手动报价导入”支持直接粘贴 CSV；必填列为 `product_id,platform,shop_name,url,price,condition,market_variant,warranty_type,bundle_type`，二手字段可按需附加。该入口只保存用户粘贴的报价，不读取账号、Cookie 或浏览器数据。

可通过仪表盘“监控产品设置”或 `PUT /api/settings/products/{product_id}` 增加镜头和机身；然后通过“公开监控链接”或 `PUT /api/settings/watches` 写入合规公开页面链接、适配器和来源，重启 Worker 才会开始采集。

目标价在 `config/alerts.yaml` 中配置（人民币参考价）。Worker 支持目标价、显著降价、新可信历史低价、库存恢复、跨市场价差和连续三次来源失败提醒；同一产品事件默认冷却 6 小时，去重状态保存在 SQLite，Worker 重启后仍有效。目标价恢复到阈值以上后会重置该事件，下一次再次跌入目标区间可立即通知。跨市场提醒阈值位于 `config/settings.yaml` 的 `market_spread_threshold_cny`，只比较可信的新机大陆、香港行货或香港水货人民币参考价。通知可通过 `.env` 中的 `WEBHOOK_URL`、`PUSHPLUS_TOKEN`、`TELEGRAM_BOT_TOKEN` 与 `TELEGRAM_CHAT_ID`、SMTP（另设 `SMTP_TO`）发送。将 `WINDOWS_DESKTOP_NOTIFICATIONS=true` 后，还会使用 `plyer` 发送 Windows 桌面通知。

配置至少一个通知渠道后，可在仪表盘“通知测试”点击发送，或调用 `POST /api/notifications/test`。未配置渠道时接口会返回错误，不会显示虚假的发送成功。

## Docker

复制 `.env.example` 为 `.env` 后执行（仪表盘和后台采集服务会一同启动）：

```bash
docker compose up -d
```

查看日志：`docker compose logs -f`；停止：`docker compose down`；升级时执行 `docker compose pull && docker compose up -d --build`。容器会保存仪表盘修改的 `config/` 配置；备份时复制 `data/tracker.db`（停止服务后操作）。

Windows 上可在服务运行时创建 SQLite 一致性备份：

```powershell
.\scripts\Backup-CameraPriceTracker.ps1
```

## 采集合规与来源限制

适配器仅使用公开页面、官方 API 或用户本地手动导入的 Cookie。平台出现验证码、登录墙、访问频控或页面结构改变时，来源状态必须显示“需要人工处理”；可改用用户粘贴商品链接、手动导入、浏览器扩展或平台开放接口。不会破解验证码、绕过登录或保存账户密码。

Price.com.hk 既会记录聚合平台状态，也会为每个实际报价商户建立独立来源健康记录（`price_com_hk:商户名`）。这样可单独核查不同商户的行货/水货、现金价、保修与库存，不会将它们当作同一店铺报价。港币转换会优先复用当天保存的汇率；当天缺失时才获取并写入新的历史汇率。

## 预测说明

预测在数据覆盖不足 30 天时会明确显示“数据不足”。满足门槛后，系统通过滚动 MAE 在移动中位数和 EWMA 两个透明基线中选择，显示模型、误差、样本量和覆盖天数。618、双 11、双 12 与已知春节窗口仅在有足够历史对应样本时影响价格区间；否则只提示即将到来的节点，不虚构折扣。

趋势图支持 24 小时、7 天、30 天、90 天、180 天与全部历史，并按大陆新机、香港行货、香港水货或二手市场单独显示。默认“最佳可用分段”只选择其中一个可比市场，避免把不同保修和成色的价格混成一条线。

商品详情的“可信价格指标”分别显示官方可信低价、授权渠道低价、全市场可信低价、市场中位价、二手中位价、香港行货低价和香港水货低价；没有足够同口径数据时显示为空，不会用其他市场填充。

可在仪表盘“事件记录”或 `PUT /api/settings/events/{event_id}` 保存已确认的发布、预售、促销、官方定价、清仓和调价事件。事件只作图表和分析标记，不会自行改写历史价格；建议提供公开 HTTPS 来源链接。

购买建议会综合可信历史低位、预测、库存、保修、优惠复杂度、事件风险与地区价差。可在仪表盘“购买地区偏好”或 `PUT /api/settings/preferences` 设置 `cn`/`hk`，建议会据此说明跨市场节省空间。

## 定时任务

推荐通过 Windows 任务计划程序以当前用户运行采集命令；频率来自 `config/sources.yaml`。Worker 对每个失败来源实施随机抖动和指数退避（最多为基础间隔的 8 倍），退避期间不发起请求，成功后恢复正常频率。生产数据目录应设为定期备份目标。
