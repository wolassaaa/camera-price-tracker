# 交付验收审计

本文件区分代码/自动化验证与必须在用户环境中执行的外部验证，避免将不可复现的结果误报为已完成。

| 验收项 | 当前证据 | 状态 |
| --- | --- | --- |
| Windows 本地 Worker、任务计划与备份 | Worker、PowerShell 注册/备份脚本；脚本语法检查通过 | 可运行，需用户注册任务 |
| 公开来源与失败可见性 | `python -m camera_tracker.worker --once --database data/cli-verification.db` 实测写入 22 条：Canon 中国、Canon 香港、Canon 香港在线商城、Sony 香港、Price.com.hk 全部成功；Price.com.hk 写入 18 个独立商户；429/503 仍会保存为来源失败 | 已验证 |
| Price.com.hk 行货/水货/现金价/保修 | 固定样本、标准化字段、数据库迁移和回归测试 | 已验证 |
| 历史、预测、购买建议 | 可信分段历史、图表时间窗口、促销事件、滚动 MAE、可解释评分与测试 | 已验证 |
| 手动导入二手 | CSV 导入、快门数/成色/包装/保修、初代 α1 筛选 API 和界面 | 已验证 |
| 通知 | Webhook、PushPlus、Telegram、SMTP、Windows 桌面传输与去重单元测试；`POST /api/notifications/test` 和仪表盘测试入口 | 代码已验证；真实第三方推送需用户自己的密钥和接收端 |
| Docker Compose | Dockerfile 与 Compose 清单；配置卷可写 | 当前机器无 Docker CLI，未执行容器运行验证 |

运行前请执行 README 的 Windows 安装步骤，配置 `.env`，然后分别启动 API 与 Worker。若使用 Docker Desktop，执行 `docker compose up -d` 后检查 `docker compose logs -f`。
