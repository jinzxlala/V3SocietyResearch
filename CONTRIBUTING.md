# 协作约定

## 核心规则

**不要在 `main` 上直接修改、直接提交、直接推送。**

`main` 只用于集成经过 review 的成果，始终保持可运行、可复现的状态。所有改动都要先落到自己的功能分支上，再通过 Pull Request 合并。

## 工作流

```bash
# 1. 同步最新的 main
git checkout main
git pull

# 2. 从 main 切出功能分支
git checkout -b <类型>/<简短描述>

# 3. 在分支上修改并提交
git add -A
git commit -m "<类型>: <说明>"

# 4. 推送分支（首次推送需要 -u）
git push -u origin <分支名>

# 5. 在 GitHub 上发起 Pull Request，等待 review 后合并
```

### 分支命名

| 前缀        | 用途             | 示例                          |
| ----------- | ---------------- | ----------------------------- |
| `feat/`     | 新功能、新分析   | `feat/economic-mobility-index` |
| `fix/`      | 修复错误         | `fix/sim-run-parser`          |
| `data/`     | 数据获取与清洗   | `data/add-population-manifest` |
| `docs/`     | 文档、周报       | `docs/weekly-w03`             |
| `exp/`      | 探索性尝试       | `exp/alt-weighting`           |

个人长期分支（如 `Serena`）用于日常实验，可以保留，但**合并进 `main` 依然要走 PR**。

### 提交信息

用 `<类型>: <说明>` 的形式，类型同分支前缀（`feat` / `fix` / `data` / `docs` / `exp` / `chore`）。

## 合并前检查

- [ ] 从 `main` 拉取过最新代码，无冲突
- [ ] 脚本能从干净环境跑通
- [ ] 没有提交大数据文件、密钥、个人路径
- [ ] 相关文档 / 周报已同步更新

## 建议在 GitHub 上开启的保护规则

仓库 Settings → Branches → Add branch protection rule，对 `main` 勾选：

- **Require a pull request before merging**（禁止直接推送）
- **Require approvals**（至少 1 人 review）
- **Require status checks to pass**（后续接入 CI 后再开）
- 可选：**Do not allow bypassing the above settings**（对自己也生效）

> 需要仓库 admin 权限才能配置。若暂时没有，就先靠本文件的人工约定。

## 目录结构

| 路径                  | 用途                                         |
| --------------------- | -------------------------------------------- |
| `config/`             | 参数配置、路径映射、版本固定文件             |
| `scripts/`            | 可执行脚本（数据抓取、清洗、建模、出图）     |
| `data/manifests/`     | 数据清单：来源、版本、校验和、字段说明       |
| `data/processed/`     | 清洗 / 加工后的中间产物（多为生成物）        |
| `reports/validation/` | 数据与结果的校验报告、异常记录               |
| `docs/weekly/`        | 周报与阶段性记录                             |

空目录用 `.gitkeep` 占位，保证克隆后结构完整。
