# 一致性评估智能体 - 测试服务器部署

## 用途

构建/推送 Docker 镜像，在测试服务器上拉起容器，用于集成测试和演示。

## 状态

**待完善** — 当前阶段仅搭建前后端基础结构，测试服务器部署脚本将在后续部署阶段按《智能体通用测试部署与快速启动规范》生成。

## 计划内容

- `docker/Dockerfile.backend` — 后端镜像
- `docker/Dockerfile.frontend` — 前端镜像
- `docker/docker-compose.test.yml` — 测试服务器编排
- `docker-build-test.ps1` — 测试镜像构建脚本
- `docker-push-test.ps1` — 镜像推送脚本
- `remote-build-images.ps1` — 远程 Docker Engine 构建
- `deploy-test-server.sh` — 测试服务器部署脚本

## 目标部署地址

| 服务 | 端口 |
|------|------|
| 前端 | 18094 |
| 后端 | 17618 |
| Flower 监控 | 15556 |

标准首页入口统一为 `https://www.nstl.gov.cn/ai/agent/claim_consistency/`，本地直连端口时为 `https://www.nstl.gov.cn:18094/ai/agent/claim_consistency/`。

## 前置条件（后续）

- Docker 20.10+
- 访问镜像仓库 `docker-hosted.example.invalid/nstl` 的权限
- 测试服务器 `NSTL-overlay` 网络
- 测试环境 MongoDB / Redis 连通性
