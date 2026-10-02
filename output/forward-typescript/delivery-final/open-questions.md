# 待确认问题

对应快照：`912d11741f8af748ba77d2c8b3d03b8eb86565cfeab2ed82e812b66f6a15eb08`。已确认的业务决定不重复询问。

## Q1 · 谁实际调用 submit 和 work，config.yml 在哪里加载？

责任类型：technical

影响：决定这是库样例、常驻服务还是定时任务，当前不能确认HTTP入口或30秒调度。

下一步证据：提供宿主启动文件、路由装配和调度器注册代码。

提出依据：`api.ts:3` [code]; `worker.ts:3` [code]; `config.yml:1` [config]

## Q2 · deliver 的真实实现、超时、失败分类和幂等约定是什么？

责任类型：technical

影响：回调可能访问任何目标。缺少实现，不能判断外部调用超时、重复副作用或安全边界。

下一步证据：提供回调绑定位置和实现；无需提供凭据值。

提出依据：`worker.ts:3` [code]

## Q3 · accepted 要承诺“已入内存”还是“可靠受理”，reference 重复时业务如何处理？

责任类型：business

影响：现有 API 不返任务ID或状态，enqueue没有按reference去重；是否需要持久化、幂等与状态查询取决于业务契约。

下一步证据：确认受理承诺、重复提交口径及允许丢失/重试边界。

提出依据：`api.ts:3` [code]; `queue.ts:1` [code]

