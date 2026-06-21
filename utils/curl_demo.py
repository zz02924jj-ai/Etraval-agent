#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : curl_demo.py
@Function: 和风天气 API 调试脚本（迁移自 SmartVoyage）
"""
import requests
import json

API_KEY = "your_api_key_here"
url = "https://api.qweather.com/v7/weather/30d?location=101010100"  # 北京30天
headers = {
    "X-QW-Api-Key": API_KEY,
    "Accept-Encoding": "gzip"
}
try:
    print("正在请求API...")
    response = requests.get(url, headers=headers, timeout=10)
    parsed = json.loads(response.text)
    print("解析成功！")
    print(json.dumps(parsed, ensure_ascii=False, indent=2)[:1000])
except Exception as e:
    print(f"请求失败: {e}")
