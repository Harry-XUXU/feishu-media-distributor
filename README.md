# Feishu Media Distributor

飞书电子表格媒体文件批量下载工具。

**用途：从飞书电子表格里自动抓出所有视频/图片，批量下载到本地。**

## 解决什么问题

影视制作团队用飞书电子表格管理分镜头——每一行是一个镜头，单元格里嵌着视频素材。  
剪辑师需要把表格里上百个视频一个个手动下载，再分发。这个工具把整个过程自动化了。

## 快速开始

```bash
# 安装依赖
pip install requests

# 下载（需要先获取 token，见下方认证流程）
python src/downloader.py \
  -t <user_access_token> \
  -s <spreadsheet_token> \
  -o ./videos
```

## 认证流程（飞书 OAuth）

下载电子表格中的附件需要使用 **user_access_token**（不能用 tenant_token）。

### 1. 获取 tenant_access_token

```bash
curl -X POST 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal' \
  -H 'Content-Type: application/json' \
  -d '{"app_id": "<你的App ID>", "app_secret": "<你的App Secret>"}'
```

### 2. 发起设备授权

```bash
curl -X POST 'https://accounts.feishu.cn/oauth/v1/device_authorization' \
  -H 'Content-Type: application/json' \
  -d '{
    "client_id": "<你的App ID>",
    "client_secret": "<你的App Secret>",
    "scope": "sheets:spreadsheet drive:drive offline_access"
  }'
```

返回结果中包含 `verification_uri_complete`——在浏览器打开这个链接完成授权。

### 3. 换取 user_access_token

```bash
curl -X POST 'https://open.feishu.cn/open-apis/authen/v2/oauth/token' \
  -H 'Content-Type: application/json' \
  -d '{
    "client_id": "<你的App ID>",
    "client_secret": "<你的App Secret>",
    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
    "device_code": "<第2步返回的 device_code>"
  }'
```

返回的 `access_token` 就是 `-t` 参数需要的 user_access_token。

## 参数说明

| 参数 | 必需 | 说明 |
|------|------|------|
| `-t, --token` | ✅ | 飞书 User Access Token |
| `-s, --spreadsheet` | ✅ | 电子表格 token（从 URL 提取） |
| `--sheet-id` | ❌ | 工作表 ID，默认 1 |
| `-o, --output` | ❌ | 输出目录，默认 `./downloads` |
| `-c, --column` | ❌ | 目标列关键词，默认 `分镜视频` |
| `--dry-run` | ❌ | 只列出文件，不下载 |

## 飞书应用权限

在飞书开放平台 → 应用权限管理，确保开通：

- `sheets:spreadsheet` — 查看电子表格
- `sheets:spreadsheet:readonly` — 只读电子表格
- `drive:drive` — 查看云空间文件
- `drive:drive:readonly` — 只读云空间文件
- `offline_access` — 刷新 token

## Token 类型区别

| Token | 用途 | 能读附件？ |
|-------|------|-----------|
| `tenant_access_token` | 应用身份 | ❌ |
| `user_access_token` | 用户身份 | ✅ |

**这是踩坑总结——飞书文档没说清楚，花了不少时间试出来的。**

## 常见错误

| 错误码 | 原因 | 解决 |
|--------|------|------|
| `99991672` | 应用缺少权限 | 在飞书开放平台开通相应权限 |
| `90215` | sheet_id 不存在 | 检查 URL 中的 `?sheet=` 参数 |
| `authorization_pending` | 用户未完成授权 | 轮询等待 |
| `invalid_grant` | device_code 过期 | 重新发起设备授权 |

## 项目结构

```
feishu-media-distributor/
├── README.md
├── requirements.txt
└── src/
    └── downloader.py    # 主脚本
```

## License

MIT
