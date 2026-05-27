# 基金实时单价自动更新

每天北京时间 **17:00** 自动获取 ETF 基金最新价格，更新到腾讯文档智能表格【001基金投资记录】的"实时单价"列。

## 工作原理

```
新浪财经 API  ──→  获取ETF最新价格  ──→  腾讯文档 Open API  ──→  更新智能表格
```

**基金列表**（从表格"基金编号-定期"字段自动读取）：

| 基金编号 | 名称 | 交易所 |
|---------|------|--------|
| 510310 | 沪深300ETF | 沪市 |
| 159338 | 中证A500 | 深市 |
| 159596 | A50ETF | 深市 |
| 513650 | 标普500ETF | 沪市 |
| 513500 | 标普500ETF-2 | 沪市 |
| 513870 | 纳斯达克ETF | 沪市 |
| 159119 | 800现金流 | 深市 |

## 前置准备

### 1. 腾讯文档开放平台注册

1. 访问 [腾讯文档开放平台](https://docs.qq.com/open) 注册成为开发者
2. 创建应用，获取 **Client ID** 和 **Client Secret**
3. 在应用中添加 OAuth 授权回调域

### 2. 获取 Refresh Token

首次需要手动获取 Refresh Token：

```bash
# 构造授权 URL（在浏览器中打开）
https://docs.qq.com/oauth/v2/authorize?client_id=YOUR_CLIENT_ID&response_type=code&scope=all&redirect_uri=YOUR_REDIRECT_URI

# 用授权码换取 token
curl -X POST https://docs.qq.com/oauth/v2/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "authorization_code",
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET",
    "code": "AUTH_CODE",
    "redirect_uri": "YOUR_REDIRECT_URI"
  }'
```

### 3. 配置 GitHub Secrets

在 GitHub 仓库的 **Settings → Secrets and variables → Actions** 中添加：

| Secret 名称 | 说明 |
|------------|------|
| `TENCENT_DOCS_CLIENT_ID` | 腾讯文档开放平台 Client ID |
| `TENCENT_DOCS_CLIENT_SECRET` | 腾讯文档开放平台 Client Secret |
| `TENCENT_DOCS_REFRESH_TOKEN` | OAuth Refresh Token（首次获取） |

## 本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 设置环境变量（Windows PowerShell）
$env:TENCENT_DOCS_CLIENT_ID = "your_client_id"
$env:TENCENT_DOCS_CLIENT_SECRET = "your_client_secret"
$env:TENCENT_DOCS_REFRESH_TOKEN = "your_refresh_token"

# 运行
python fund_price_updater.py
```

## 定时运行

GitHub Actions 已配置为 **北京时间周一至周五 17:00** 自动执行。

也可在 GitHub 仓库的 **Actions** 页面手动触发。

## 数据来源

- ETF 实时价格：[新浪财经](https://finance.sina.com.cn) 行情接口
- 表格操作：[腾讯文档 Open API](https://docs.qq.com/open/document/app/openapi/v2/smartsheet/overview.html)

## 注意事项

- 周末和节假日不执行更新（通过 GitHub Actions `1-5` 工作日配置 + 脚本内周六日检测）
- 价格为 ETF 在 **A股市场的交易价格**（非基金净值/NAV），15:00 收盘后即为当日收盘价
- 标普500ETF、纳斯达克ETF 虽跟踪美股指数，但其交易价格来自中国交易所（沪市513xxx），非美股实时价格
