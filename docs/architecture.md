# 架构

`config/` 保存产品和来源频率；`adapters/` 每个来源单独解析为标准报价；`normalization.py` 计算最终到手价；`reliability.py` 阻止异常报价进入历史低价；`repository.py` 保存历史与快照；`forecasting.py` 仅在至少 30 天数据时输出保守预测；`notifications.py` 负责冷却去重；`api.py` 提供本地 API 与仪表盘。

后续新增平台必须实现独立适配器与固定 HTML/JSON 样本测试，不得在通用采集文件中堆放平台特定选择器。
