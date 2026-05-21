# Lumira Atelier Backend · Fly.io Deploy Runbook

主公一次部署手册。第一次需要 ~30 分钟（账号注册 + 第一次 launch），之后每次 deploy 只要 `flyctl deploy` 一条命令 + 等 60 秒。

---

## 0. 前置 — 一次性 setup（5 分钟）

```bash
# 1. 安装 Fly CLI
brew install flyctl

# 2. 注册 Fly.io 账号（要绑卡，v1 流量内 $0）
flyctl auth signup        # 会自动弹浏览器；用 GitHub OAuth 最快

# 3. 验证登录
flyctl auth whoami
# → 输出主公邮箱说明 OK
```

绑卡说明：Fly.io 免费额度 = 3 个 256MB 容器 + 160 小时 shared-cpu/月 + 160GB 出站流量。我们的 v1 配置（shared-cpu-2x, 2GB RAM）**超出**免费额度，但 `auto_stop_machines = "stop"` 让 VM 闲时自动停机不计费。预估 v1 月费 **$3-8**（按 100 wizard/天估算），主公心里有数。

---

## 1. 首次部署（一次性 ~10 分钟）

```bash
cd lumira-backend

# 1.1 创建 Fly app（用本目录已有的 fly.toml）
flyctl launch --copy-config --no-deploy --name lumira-atelier-backend --region hkg
# 提示选项时一律回车（用 fly.toml 默认值）

# 1.2 写入生产 secrets（替换成真值）
flyctl secrets set \
    OPENAI_API_KEY="<relay-station-key-从 .env 取>" \
    OPENAI_BASE_URL="https://api.openbili.com/v1"

# 1.3 第一次 deploy（构建镜像 + 推到 Fly + 启动机器）
flyctl deploy

# 1.4 观察日志确认 uvicorn 起来
flyctl logs
# → 期望看到 "lumira_backend_starting env=production version=0.1.0"
# Ctrl+C 退出 logs（不会停服务）

# 1.5 拿到生产 URL
flyctl info | grep Hostname
# → 类似 lumira-atelier-backend.fly.dev

# 1.6 smoke check
curl https://lumira-atelier-backend.fly.dev/health
# → {"status":"ok","version":"0.1.0"}
```

把 step 1.5 的 URL 告诉 Claude — Claude 会把它写到 Cloudflare Worker 的 `LUMIRA_BACKEND_URL` secret 里。

---

## 2. 之后每次 deploy（< 60 秒）

```bash
cd lumira-backend
flyctl deploy
```

完了。Fly 会自动构建新镜像、滚动重启容器、跑 health check 通过才切流量。失败会自动回滚。

---

## 3. 常用运维命令

```bash
# 看实时日志
flyctl logs

# 看运行状态
flyctl status

# 看 VM 资源用量
flyctl scale show

# 升级 VM 规格（如 RAM 不够）
flyctl scale memory 4096    # → 4GB

# 重启
flyctl machine restart

# 看 secrets 列表（值不显示）
flyctl secrets list

# 临时进容器（debug 用）
flyctl ssh console

# 跑一次性命令（如 db migration）
flyctl ssh console -C "uv run python scripts/something.py"
```

---

## 4. 故障排查

### Deploy 卡在 "Waiting for health check"

- 看 `flyctl logs` 是否有 Python ImportError（多半是 optical 依赖装失败）
- 健康检查路径 `/health` 必须返回 200（看 `app/main.py`）
- VM 内存可能爆了：`flyctl scale memory 4096` 再 retry

### 502 Bad Gateway 从 Cloudflare Worker

- 99% 是后端 cold-start：第一次请求要 5-10s（VM 冷启动 + uvicorn worker init）
- `auto_stop_machines = "stop"` 是有意的省钱设计；如果不能接受，改成 `min_machines_running = 1` 让 VM 永远开着

### LLM 调用 timeout

- 中转站偶尔慢，跟 Fly 无关
- Cloudflare Worker 的 `maxDuration = 60` 已经设了
- backend 内 httpx timeout 在 `app/core/llm_relay.py`

### Optiland 计算超时

- shared-cpu-2x 2vCPU 在并发高时 CPU bound
- 升级到 `performance-cpu-2x` 2vCPU 但独占 → 但贵 5×
- 或者把 Optiland 调用包成 background task 排队（v2 工作）

---

## 5. 回滚

```bash
# 看历史 release
flyctl releases

# 回滚到上一个
flyctl releases rollback

# 或回滚到指定 version
flyctl releases rollback <version>
```

---

## 6. 删除（如果要弃用）

```bash
flyctl apps destroy lumira-atelier-backend
```

⚠ 这是不可逆操作 — 会删 VM + 释放域名。

---

## 7. 成本控制

```bash
# 看本月开销估算
flyctl dashboard      # 浏览器打开，到 Billing 页

# 临时停机省钱（仍计费几分钱/天 storage）
flyctl scale count 0

# 重新启动
flyctl scale count 1
```

阈值：超过 $30/月就该看流量、考虑：
- 把 `auto_stop_machines = "stop"` 留着
- 把 `min_machines_running` 降到 0
- 看 LLM 调用是不是被人滥用（加 IP rate limit）
