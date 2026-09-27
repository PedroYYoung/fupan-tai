# 复盘台 —— 部署与运维手册（第一批）

## 1. 本地开发 / 首次建仓

```bash
# 前端
npm install
npm run dev          # http://localhost:5173

# 数据（单日快照模式）
pip install -r requirements.txt
python scripts/build.py --date 20260925        # 指定交易日
python scripts/build.py --incremental          # 最近已收盘交易日
python scripts/build.py --date 20260925 --backfill-days 20   # 本地回补（勿在 CI 用）

# 演示数据（仓库已内置，可跳过）
python scripts/make_sample_data.py
```

## 2. Vercel 导入步骤

1. 把本仓库推送到 GitHub。
2. Vercel → Add New → Project → Import 该仓库。
3. Framework Preset 选 **Vite**（Build Command `npm run build`，Output `dist`，保持默认即可）。
4. 若开启口令：在 Environment Variables 添加 `VITE_GATE_HASH`（口令的 SHA-256 十六进制，64 位），添加后 **Redeploy** 一次才生效。
5. Deploy 完成，`https://<你的域名>/` 即可访问；`/data/*.json` 为静态文件直接托管，无需任何服务端。

> history 路由已通过 `vercel.json` 的 rewrites 兜底到 `/index.html`，静态数据文件优先于 rewrite，不受影响。

## 3. Windows 任务计划程序（本地每日 18:40 自动更新）

1. 「任务计划程序」→ 创建任务（不是基本任务）。
2. **常规**：名称 `fupan-data-update`；勾选「不管用户是否登录都要运行」；勾选「唤醒计算机运行此任务」；**取消**「只有在计算机使用交流电源时才启动此任务」。
3. **触发器**：新建 → 每天 18:40 → 启用。
4. **操作**：新建 → 程序：`C:\Python311\python.exe`（你的实际路径）→ 参数：`scripts\build.py --incremental` → 起始于：仓库根目录，如 `D:\fupan-tai`。
5. **设置**：勾选「如果任务失败，按以下频率重新启动」→ 1 次，间隔 5 分钟。
6. 右键任务 → 运行，验证 `data/` 有新文件且 `git status` 出现变更。
7. 配合 git 自动提交（可选）：在操作后追加第二条操作运行 `git_pull_commit_push.bat`（内容：`git add data/ && git commit -m "data: %date%" && git push`）。

Linux/NAS 用 crontab：`40 18 * * 1-5 cd /path/to/fupan-tai && python3 scripts/build.py --incremental`

## 4. 推送凭证方案（二选一）

### 方案 A：SSH Deploy Key（推荐单机）

```bash
ssh-keygen -t ed25519 -C "fupan-deploy" -f ~/.ssh/fupan_deploy   # 一路回车，可不设密码
cat ~/.ssh/fupan_deploy.pub
```
GitHub 仓库 → Settings → Deploy keys → Add deploy key → 粘贴公钥，**勾选 Allow write access**。
`~/.ssh/config` 追加：
```
Host github-fupan
  HostName github.com
  User git
  IdentityFile ~/.ssh/fupan_deploy
```
远程改用：`git remote set-url origin git@github-fupan:USER/REPO.git`

### 方案 B：PAT（简单但权限大）

GitHub → Settings → Developer settings → Personal access tokens → Fine-grained → 只勾选该仓库的 Contents: Read and write。
`git remote set-url origin https://<TOKEN>@github.com/USER/REPO.git`
（注意 PAT 明文在 remote URL 中，安全性低于 Deploy Key。）

## 5. 失败通知（PushPlus / Server酱）

- PushPlus：`python -m pip install requests` 后设置环境变量 `PUSHPLUS_TOKEN=<token>`。
- Server酱：设置环境变量 `SC_SENDKEY=<SendKey>`。
- GitHub Actions：仓库 Settings → Secrets → Actions 添加同名 secret，构建失败时自动推送。
- 本地任务计划：系统环境变量里配置上述变量即可，build.py 失败路径会调用。

## 6. GitHub Actions cron 被禁用的恢复方法

GitHub 会对 **60 天无仓库活动** 的仓库自动禁用 scheduled workflows。恢复：
仓库首页黄色横幅 → Enable，或 Actions 页 → update-data → Enable workflow。
README「已知限制」中有说明；也可让本地脚本每月产生一次 commit 保险。
