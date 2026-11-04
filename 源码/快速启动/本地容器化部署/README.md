# 一致性评估智能体 - 本地容器化部署

## 用途

在本机使用 Docker 复现测试环境容器形态，用于开发联调和容器化验证。

## 状态

**待完善** — 当前阶段仅搭建前后端基础结构，Docker Compose 和镜像构建文件将在后续部署阶段按《智能体通用测试部署与快速启动规范》生成。

## 计划内容

- `docker/Dockerfile.backend` — 后端镜像（python:3.11-slim-bookworm）
- `docker/Dockerfile.frontend` — 前端镜像（node:20-alpine 构建 + nginx:1.27-alpine 运行）
- `docker/docker-compose.yml` — 本地容器编排（backend + frontend + celery_worker + celery_flower）
- `docker/nginx/conf/nginx.conf.template` — Nginx 反向代理模板
- `start-local-containers.ps1` — 本地容器一键启动脚本
- `stop-local-containers.ps1` — 本地容器停止脚本

## 前置条件（后续）

- Docker Desktop 20.10+
- NSTL 内网/VPN（用于访问测试环境 MongoDB 和 Redis）
- 项目根目录 `.env` 文件
