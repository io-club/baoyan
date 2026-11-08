# 保研平台

一个自布署的保研信息与申请工作台，集中管理保研日历、导师信息、情报采集、任务调度、申请材料、套磁模板与邮件草稿，并提供可调用平台工具的 OpenHands Agent。

> 代码质量警告：完全的 AI slop，开发周期高达六个小时，请谨慎使用。

## 功能

- **保研日历**：管理活动、截止日期、标签、倒计时和提醒；支持从活动来源批量采集并续跑。
- **导师库**：保存学校、院系、研究所、研究方向、主页和联系方式；支持分类筛选、批量导入和 JSON 数据保留。
- **情报工作台**：采集小红书关键词结果、监听指定 QQ 群、手工录入情报，保留原始内容与附件，并按来源 ID 去重。
- **情报总结**：调用 OpenAI 兼容模型，对选中的情报生成摘要，并记录来源与处理状态。
- **套磁与草稿**：维护套磁模板和联系记录，使用导师真实字段渲染主题与正文，生成带附件的邮件草稿。
- **材料与口径**：管理申请材料、文件、申请对象及材料关联关系。
- **任务中心**：执行一次性任务、Cron 定时任务和长期运行服务，提供进度、日志、取消、重启策略和运行历史。
- **OpenHands Agent**：通过网关使用任务中心和业务 API，并在新会话中加载平台上下文。
- **统一设置**：在网页中管理访问口令、LLM、IMAP 和 Outlook OAuth 配置。

## 快速开始

### 前置条件

- Windows 10/11。
- PowerShell 5.1 或 PowerShell 7。
- Docker Desktop，使用 Linux 容器并已启动引擎。
- Node.js 22 与 npm。
- Go Task 为可选命令入口，不安装也可直接运行 PowerShell 脚本。

首次启动会下载 npm、Maven、Python 依赖和多个容器镜像，耗时取决于网络。宿主机不需要安装 Python、Java 或 Maven，这些构建分别在容器中完成。

### 启动

在项目根目录执行：

```powershell
.\start-local.ps1
```

启动脚本会生成 `.runtime/local.env`、构建前端和网关、构建业务镜像、启动依赖及业务服务、等待健康检查，并尝试同步 Agent 配置。

访问地址：

```text
http://localhost:18081
```

初始访问口令：

```text
baoyan-local-demo
```

首次登录后建议立即在“设置”中修改口令。

### 构建并测试

```powershell
.\start-local.ps1 -Test
```

该模式会在构建后额外执行任务服务、平台服务和小红书适配服务的测试。

### 停止、状态和日志

```powershell
.\stop-local.ps1
.\deploy\local-compose.ps1 ps
.\deploy\local-compose.ps1 logs
```

`stop-local.ps1` 只停止容器，不删除 `.runtime` 中的数据。

如果安装了 Go Task，可以使用等价入口：

```powershell
task deploy
task test
task stop
task status
task logs
task check
```

## 首次配置

登录后进入“设置”，依次完成需要使用的功能。配置完毕后最好重新启动。

### LLM

填写 OpenAI 兼容接口地址、模型名称和 API Key。接口地址通常以 `/v1` 结尾。配置保存到本地 Nacos，并尝试同步到 OpenHands；情报总结和 Agent 功能依赖这项配置。

如果启动时尚未配置模型，核心服务仍会正常运行，启动脚本只输出警告。

### 小红书

在“情报工作台”中选择“收集小红书”，输入关键词和本人登录后的完整 Cookie。Cookie 必须包含 `a1` 和 `web_session`。

Cookie 会过期。若采集返回 403，请先在浏览器中确认搜索正常，再重新复制当前请求的 Cookie。不要将 Cookie 发送到聊天、写入源码或提交到 Git。

### QQ 群

1. 在“情报工作台”选择“连接 QQ 群”。
2. 打开 NapCat WebUI，由账号持有人扫码登录。
3. 输入需要监听的群号和重启策略，再启动监视服务。

QQ 登录和扫码需要账号持有人亲自完成。

### 邮箱草稿

配置 IMAP 地址、账号和授权码后，平台可以将生成的 EML 同步到草稿箱。

Outlook OAuth 需要在本人 Microsoft Entra 应用中配置公共客户端 Client ID，然后在网页中完成设备授权。系统不请求 `SMTP.Send` 权限，也不存在发送邮件的 API。

### 更完整的接口说明见：

- [平台 API](docs/PLATFORM_API.md)
- [Agent API 目录](docs/AGENT_API_CATALOG.md)
- [小红书采集 API](docs/XHS_API.md)

## 数据和备份

运行数据位于：

```text
.runtime/
├── local.env                 # 本地服务密钥和路径
├── local-data/
│   ├── postgres/             # 业务与任务数据库
│   ├── redis/
│   ├── rabbitmq/
│   ├── minio/                # 附件、原始情报、邮件草稿
│   ├── nacos/                # LLM、邮箱、访问口令等配置
│   ├── tasks/logs/           # 任务日志
│   └── workspace/            # 任务工作区与采集检查点
├── cache/                    # npm、pip、Maven 缓存
└── tmp/
```

备份时应同时保存 `.runtime/local.env` 和 `.runtime/local-data`。两者都包含敏感信息，不能提交到 Git 或公开分享。

Compose 项目名固定为 `baoyan-local`。同一台电脑不要从两个不同项目目录同时启动同名 Compose 项目。

## 第三方组件和许可

小红书适配服务封装了 GitHub 项目 [`cv-cat/Spider_XHS`](https://github.com/cv-cat/Spider_XHS), MIT License。
