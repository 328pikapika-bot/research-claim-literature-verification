# 一致性评估智能体 - 本地源码启动

## 前置条件

1. Python 3.11+
2. hosts 中配置本地域名：

```text
127.0.0.1 www.nstl.gov.cn
```

## 启动方式

双击项目根目录的 `start-dev.bat`。

脚本会自动：

1. 安装后端 Python 依赖
2. 生成带 SAN 的本地 HTTPS 证书
3. 将本地 CA 导入当前 Windows 用户的受信任根证书库
4. 启动后端 FastAPI，端口 `17608`
5. 启动前端 HTTPS 静态文件服务和 API 反向代理，端口 `18094`
6. 打开首页

## 访问地址

| 服务 | 地址 |
|------|------|
| 首页（本地） | https://www.nstl.gov.cn:18094/ai/agent/claim_consistency/ |
| 首页（平台标准入口） | https://www.nstl.gov.cn/ai/agent/claim_consistency/ |
| 后端 API | http://127.0.0.1:17608 |
| API 文档 | http://127.0.0.1:17608/docs |
| 健康检查 | http://127.0.0.1:17608/system/health |

本地固定使用 `https://www.nstl.gov.cn:18094/ai/agent/claim_consistency/`，测试/平台环境使用 `https://www.nstl.gov.cn/ai/agent/claim_consistency/`，两者保持同一个首页路径。

## 架构

```text
浏览器 -> https://www.nstl.gov.cn:18094/ai/agent/claim_consistency/ (静态文件 + API 代理) -> :17608 (FastAPI)
```

## 常见问题

### 首页报 `net::ERR_CERT_AUTHORITY_INVALID`

通常是服务端使用的 `frontend\web_demo\cert.pem` 与系统信任库里的证书不是同一套，或旧证书缺少 SAN。重新运行：

```bat
python scripts\local\setup_https_cert.py --host www.nstl.gov.cn --host localhost --host 127.0.0.1 --force --trust
```

然后重启前端服务，并重新打开浏览器。

### 端口占用

```bat
netstat -ano | findstr "17608"
netstat -ano | findstr "18094"
taskkill /F /PID <PID>
```
