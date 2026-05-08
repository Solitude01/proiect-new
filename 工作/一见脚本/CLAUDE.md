# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

"一见" 项目的运维脚本集合，核心功能是**分布式 XPU（昆仑 R200 加速卡）集群资源巡检**。通过中心节点 SSH 免密连接所有边缘节点，远程执行采集脚本并汇总结果。

## 仓库结构

### XPU 集群巡检（主项目）

| 文件 | 用途 |
|------|------|
| `需求.md` | 集群架构说明和需求描述 |
| `xpu_central_check.sh` | 中心调度脚本的当前可执行版本 |
| `xpu_central_check.sh.txt` | 中心调度脚本的文本归档，部署于中心节点 `/usr/local/bin/xpu_central_check.sh` |
| `xpu_check.sh.txt` | 边缘采集脚本，由中心脚本通过 SSH 推送到各节点 `/tmp/xpu_check.sh` 执行 |
| `output.txt` | 某次实际运行的输出样例 |
| `readme.md` | 对象存储位置、执行方式备忘 |

**注意：** `.sh.txt` 后缀是因为脚本通过 `cat` heredoc 方式写入目标服务器，实际部署后为 `.sh` 文件。`xpu_central_check.sh`（无 `.txt`）是可直接执行的版本。

### 模型包查询 (`模型包查询/`)

MySQL 5.7 查询命令备忘，用于查询 K8s 中 `xdbmysql57-0` Pod 的 `windmill` 数据库内模型包（`model` 表）的资源分配情况。

- **数据库**: MySQL 5.7.38（不支持窗口函数，需用用户变量模拟序号）
- **连接方式**: `kubectl exec -it -n middleware xdbmysql57-0 -- /mysql/bin/mysql --defaults-file=/mysql/etc/user.root.cnf -D windmill --default-character-set=utf8mb4`
- `查询指令.md` 包含 3 组常用 SQL 查询：模型包 vGPU/GPU 分布、特定条件筛选、全资源明细汇总

### 网络请求分析 (`网络请求/`)

Firefox HAR（HTTP Archive）导出文件，记录 `10.10.99.159:8412` 上 vistudio-proxy-api 和 windmill API 的请求/响应详情，用于调试 API 调用链和模型仓库交互。

## 集群架构

```
中心节点 10.10.99.159
  ├── SSH 免密 → 广芯边缘 (10.65.233.21, 10.65.233.46)
  ├── SSH 免密 → 无锡边缘 (10.20.7.165, 10.20.7.166)
  ├── SSH 免密 → 南通边缘 (10.30.4.33, 10.30.4.34)
  ├── SSH 免密 → 深圳边缘 (10.10.99.78)
  └── SSH 免密 → 深圳转换服 (10.10.108.239)
```

每台边缘节点运行 Kubernetes，搭载昆仑 R200 XPU 加速卡，通过 `xpu_smi` 命令获取硬件级资源使用情况。

## 数据流

1. **中心脚本** (`xpu_central_check.sh`) 并行/串行 SSH 到所有目标节点
2. 将内嵌的**边缘脚本**通过 stdin 写入目标节点的 `/tmp/xpu_check.sh` 并执行
3. 边缘脚本采集两部分数据：
   - **K8s 视角**：通过 `kubectl get nodes/pods` 获取 XPU 资源的申请量（limits）
   - **硬件视角**：通过 `xpu_smi` 获取每张卡的实际显存、利用率、温度
4. 边缘脚本输出 6 个 section，其中 section 6 输出 `##XPUSMI##` 前缀的 TSV 行，供中心端聚合解析
5. 中心脚本收集所有节点的 `##XPUSMI##` 行，按边缘节点维度生成全局资源总表

## 关键配置

中心脚本 (`xpu_central_check.sh`) 中的节点配置通过关联数组定义：

- `IP_TO_GROUP` — IP 到边缘分组的映射
- `NODE_LABEL` — IP 到节点标签的映射
- `ORDERED_IPS` — 采集顺序
- `ORDERED_GROUPS_STR` — 总表输出顺序（用 `|` 分隔以避免中文 split 歧义）

环境变量控制：
- `SSH_USER`（默认 root）
- `SSH_TIMEOUT`（默认 15s）
- `CMD_TIMEOUT`（默认 120s）
- `PARALLEL`（默认 1，设为 0 切换串行模式）

## 修改脚本时的注意事项

- 节点 IP 配置同时存在于 `IP_TO_GROUP`、`NODE_LABEL`、`ORDERED_IPS` 三处，新增节点需同步更新
- `##XPUSMI##` 行格式是中心聚合的协议，修改字段需同步更新 `parse_all_xpusmi()` 和 `print_total_table()` 中的 awk 解析逻辑
- 边缘脚本通过 bash heredoc (`<<<`) 传递，内部避免使用会提前展开的变量；已在中心脚本中用 `cat <<'SCRIPT_BODY'`（带引号）避免变量展开
- 边缘脚本在目标节点 `/tmp` 下创建临时文件，通过 `trap ... EXIT` 确保清理
- `query_model_lookup()` 通过 kubectl exec 查询 MySQL 获取 endpoint↔模型中文名映射；修改 SQL 字段需同步更新 Section 7 中 `lookup_model()` 的 awk 解析和 printf 格式化
- `MODEL_LOOKUP_FILE` 在 `RESULT_DIR` 下创建为临时 TSV，随 `trap ... EXIT` 自动清理
