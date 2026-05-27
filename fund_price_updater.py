#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基金实时单价自动更新脚本
========================
从新浪财经获取ETF基金最新价格，更新到腾讯文档智能表格中。

基金列表（从表格"基金编号-定期"字段获取）:
  - 510310  沪深300ETF     (沪市)
  - 159338  中证A500       (深市)
  - 159596  A50ETF         (深市)
  - 513650  标普500ETF     (沪市)
  - 513500  标普500ETF-2   (沪市)
  - 513870  纳斯达克ETF    (沪市)
  - 159119  800现金流      (深市)

运行方式:
    python fund_price_updater.py

定时运行 (GitHub Actions):
    北京时间每个交易日 17:00 自动执行

依赖环境变量:
    TENCENT_DOCS_CLIENT_ID     腾讯文档开放平台 Client ID
    TENCENT_DOCS_CLIENT_SECRET 腾讯文档开放平台 Client Secret
    TENCENT_DOCS_REFRESH_TOKEN 腾讯文档 OAuth Refresh Token (可选，优先使用)
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests

# ============================================================
# 配置
# ============================================================

# 腾讯文档智能表格信息
SMARTSHEET_FILE_ID = "DQm9Za1hYeFBnS2dG"
SMARTSHEET_SHEET_ID = "OFl45n"

# 基金编号-定期 字段ID
FIELD_FUND_CODE = "fH2UyD"
# 实时单价 字段ID
FIELD_REALTIME_PRICE = "frbTIJ"

# 北京时间时区
BEIJING_TZ = timezone(timedelta(hours=8))

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============================================================
# 新浪财经 - ETF实时价格获取
# ============================================================

def get_etf_price_sina(fund_code: str) -> Optional[float]:
    """
    通过新浪财经接口获取ETF最新价格。
    
    Args:
        fund_code: 基金代码（如 510310, 159338）
    
    Returns:
        最新价格 (float)，获取失败返回 None
    """
    # 判断交易所前缀: 51/56 开头为沪市(sh)，其他为深市(sz)
    code_str = str(fund_code).zfill(6)
    if code_str.startswith(("51", "56")):
        prefix = "sh"
    else:
        prefix = "sz"

    url = f"http://hq.sinajs.cn/list={prefix}{code_str}"
    headers = {"Referer": "https://finance.sina.com.cn"}

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "gbk"
        text = resp.text

        # 解析返回格式: var hq_str_sh510310="名称,今开,昨收,当前价,最高,最低,..."
        if '=""' in text or text.strip() == "":
            logger.warning(f"基金 {fund_code} 返回空数据，可能非交易日")
            return None

        # 提取引号内的数据
        data_str = text.split('"')[1] if '"' in text else ""
        if not data_str:
            logger.warning(f"基金 {fund_code} 数据解析失败: {text[:100]}")
            return None

        fields = data_str.split(",")
        if len(fields) < 4:
            logger.warning(f"基金 {fund_code} 返回字段不足: {fields}")
            return None

        name = fields[0]
        current_price = float(fields[3])

        logger.info(f"[{fund_code}] {name} 最新价: {current_price:.3f}")
        return current_price

    except requests.RequestException as e:
        logger.error(f"基金 {fund_code} 网络请求失败: {e}")
        return None
    except (ValueError, IndexError) as e:
        logger.error(f"基金 {fund_code} 数据解析异常: {e}")
        return None


# ============================================================
# 腾讯文档 Open API - 认证
# ============================================================

TENCENT_DOCS_OAUTH_URL = "https://docs.qq.com/oauth/v2/token"
TENCENT_DOCS_API_BASE = "https://docs.qq.com/openapi/smartsheet/v2"


class TencentDocsClient:
    """腾讯文档 Open API 客户端"""

    def __init__(self):
        self.client_id = os.environ.get("TENCENT_DOCS_CLIENT_ID")
        self.client_secret = os.environ.get("TENCENT_DOCS_CLIENT_SECRET")
        self.refresh_token = os.environ.get("TENCENT_DOCS_REFRESH_TOKEN")
        self.access_token: Optional[str] = None
        self.token_expires_at: float = 0

    def get_access_token(self) -> Optional[str]:
        """获取或刷新 access_token"""
        now = time.time()

        # 如果 token 未过期，直接返回
        if self.access_token and now < self.token_expires_at - 60:
            return self.access_token

        if not self.client_id or not self.client_secret:
            logger.error("缺少 TENCENT_DOCS_CLIENT_ID 或 TENCENT_DOCS_CLIENT_SECRET 环境变量")
            return None

        # 如果有 refresh_token，使用它刷新
        if self.refresh_token:
            payload = {
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
            }
        else:
            payload = {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }

        try:
            resp = requests.post(TENCENT_DOCS_OAUTH_URL, json=payload, timeout=15)
            data = resp.json()

            if resp.status_code != 200 or "access_token" not in data:
                logger.error(f"获取 access_token 失败: {data}")
                return None

            self.access_token = data["access_token"]
            expires_in = data.get("expires_in", 7200)
            self.token_expires_at = now + expires_in

            if "refresh_token" in data:
                self.refresh_token = data["refresh_token"]
                logger.info("获取到新的 refresh_token")

            logger.info(f"access_token 获取成功，有效期 {expires_in}s")
            return self.access_token

        except requests.RequestException as e:
            logger.error(f"OAuth 请求失败: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"OAuth 响应解析失败: {e}")
            return None

    def _headers(self) -> dict:
        """构造请求头"""
        token = self.get_access_token()
        if not token:
            raise RuntimeError("无法获取有效的 access_token")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Client-Id": self.client_id,
        }

    def list_records(self, file_id: str, sheet_id: str, limit: int = 200) -> list:
        """
        获取智能表格的所有记录。
        
        Returns:
            records 列表
        """
        url = f"{TENCENT_DOCS_API_BASE}/files/{file_id}/sheets/{sheet_id}/records"
        params = {"limit": limit}

        try:
            resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
            data = resp.json()

            if resp.status_code != 200:
                logger.error(f"获取记录失败 [{resp.status_code}]: {data}")
                return []

            records = data.get("records", [])
            logger.info(f"获取到 {len(records)} 条记录")
            return records

        except requests.RequestException as e:
            logger.error(f"获取记录网络错误: {e}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"记录数据解析失败: {e}")
            return []

    def update_records(self, file_id: str, sheet_id: str, records: list) -> bool:
        """
        批量更新智能表格记录。
        
        Args:
            records: [{"record_id": "xxx", "values": {"field_id": value}}, ...]
        
        Returns:
            更新是否成功
        """
        url = f"{TENCENT_DOCS_API_BASE}/files/{file_id}/sheets/{sheet_id}/records"

        payload = {"records": records}

        try:
            resp = requests.put(url, headers=self._headers(), json=payload, timeout=30)
            data = resp.json()

            if resp.status_code != 200:
                logger.error(f"更新记录失败 [{resp.status_code}]: {data}")
                return False

            logger.info(f"成功更新 {len(records)} 条记录")
            return True

        except requests.RequestException as e:
            logger.error(f"更新记录网络错误: {e}")
            return False
        except json.JSONDecodeError as e:
            logger.error(f"更新响应解析失败: {e}")
            return False


# ============================================================
# 主逻辑
# ============================================================

def is_trading_day() -> bool:
    """
    简单判断是否为交易日。
    排除周六、周日。更精确的判断需要接入交易日历。
    """
    today = datetime.now(BEIJING_TZ)
    return today.weekday() < 5  # 0=周一, 5=周六, 6=周日


def main():
    """主函数"""
    logger.info("=" * 50)
    logger.info("基金实时单价更新任务开始")
    logger.info(f"北京时间: {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')}")

    # 检查是否为交易日（周末跳过）
    if not is_trading_day():
        logger.info("今日为周末，非交易日，跳过更新")
        return

    # 1. 获取所有基金的最新价格
    logger.info("-" * 40)
    logger.info("步骤1: 获取ETF实时价格")

    td_client = TencentDocsClient()

    # 先从腾讯文档获取记录，筛选含有"基金编号-定期"字段的记录
    records = td_client.list_records(SMARTSHEET_FILE_ID, SMARTSHEET_SHEET_ID)
    if not records:
        logger.error("无法获取表格记录，请检查认证配置")
        sys.exit(1)

    # 筛选含有"基金编号-定期"且需要更新"实时单价"的记录
    fund_records = []
    for record in records:
        field_values = record.get("field_values", [])
        fund_code = None
        has_price_field = False

        for fv in field_values:
            if fv.get("field") == FIELD_FUND_CODE:
                fund_code = fv.get("number_value")
            if fv.get("field") == FIELD_REALTIME_PRICE:
                has_price_field = True

        if fund_code and has_price_field:
            fund_records.append({
                "record_id": record["record_id"],
                "fund_code": int(fund_code),
            })

    if not fund_records:
        logger.warning("未找到含有'基金编号-定期'的记录")
        return

    logger.info(f"找到 {len(fund_records)} 只基金待更新:")
    for fr in fund_records:
        logger.info(f"  record_id={fr['record_id']}, 基金编号={fr['fund_code']}")

    # 2. 从新浪财经获取价格
    logger.info("-" * 40)
    logger.info("步骤2: 从新浪财经获取最新价格")

    update_records = []
    for fr in fund_records:
        price = get_etf_price_sina(str(fr["fund_code"]))
        if price is not None:
            update_records.append({
                "record_id": fr["record_id"],
                "values": {FIELD_REALTIME_PRICE: round(price, 3)},
            })
        else:
            logger.warning(f"基金 {fr['fund_code']} (record_id={fr['record_id']}) 价格获取失败，跳过")

    if not update_records:
        logger.warning("没有可更新的价格数据")
        return

    # 3. 更新到腾讯文档
    logger.info("-" * 40)
    logger.info("步骤3: 更新腾讯文档智能表格")

    success = td_client.update_records(SMARTSHEET_FILE_ID, SMARTSHEET_SHEET_ID, update_records)

    # 4. 汇总报告
    logger.info("-" * 40)
    if success:
        logger.info("✓ 更新成功!")
        for ur in update_records:
            logger.info(f"  record_id={ur['record_id']}: 实时单价={ur['values'][FIELD_REALTIME_PRICE]}")
    else:
        logger.error("✗ 更新失败!")
        sys.exit(1)

    logger.info("=" * 50)
    logger.info("基金实时单价更新任务完成")


if __name__ == "__main__":
    main()
