#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author  : Vincent
@Time    : 2026/6/20
@File    : spider_weather.py
@Function: 和风天气 API 数据爬虫（迁移自 SmartVoyage）
- 定时拉取北京/上海/广州/深圳 30天预报
- 写入 MySQL（weather_data 表）
- 可被天气 MCP Server 调用
"""
import requests
import mysql.connector
from datetime import datetime, timedelta
import schedule
import time
import json
import gzip
import pytz
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from configs.llm_config import weather_api, mysql_config

# 城市代码
city_codes = {
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280101",
    "深圳": "101280601"
}
TZ = pytz.timezone('Asia/Shanghai')


def connect_db():
    return mysql.connector.connect(**mysql_config)


def fetch_weather_data(city, location):
    headers = {
        "X-QW-Api-Key": weather_api["key"],
        "Accept-Encoding": "gzip"
    }
    url = f"{weather_api['base_url']}/weather/30d?location={location}"
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        if response.headers.get('Content-Encoding') == 'gzip':
            data = gzip.decompress(response.content).decode('utf-8')
        else:
            data = response.text
        return json.loads(data)
    except Exception as e:
        print(f"请求 {city} 天气数据失败: {e}")
        return None


def get_latest_update_time(cursor, city):
    cursor.execute("SELECT MAX(update_time) FROM weather_data WHERE city = %s", (city,))
    result = cursor.fetchone()
    return result[0] if result[0] else None


def should_update_data(latest_time, force_update=False):
    if force_update:
        return True
    if not latest_time:
        return True
    current_time = datetime.now(TZ)
    latest_time = latest_time.replace(tzinfo=TZ)
    return (current_time - latest_time).total_seconds() / 3600 >= 24


def store_weather_data(conn, cursor, city, data):
    if not data or data.get("code") != "200":
        print(f"{city} 数据无效，跳过存储。")
        return
    daily_data = data.get("daily", [])
    update_time = datetime.fromisoformat(data.get("updateTime", datetime.now().isoformat()).replace("+08:00", "+08:00")).replace(tzinfo=TZ)
    for day in daily_data:
        fx_date = datetime.strptime(day["fxDate"], "%Y-%m-%d").date()
        values = (
            city, fx_date,
            day.get("sunrise"), day.get("sunset"),
            day.get("moonrise"), day.get("moonset"),
            day.get("moonPhase"), day.get("moonPhaseIcon"),
            day.get("tempMax"), day.get("tempMin"),
            day.get("iconDay"), day.get("textDay"),
            day.get("iconNight"), day.get("textNight"),
            day.get("wind360Day"), day.get("windDirDay"), day.get("windScaleDay"), day.get("windSpeedDay"),
            day.get("wind360Night"), day.get("windDirNight"), day.get("windScaleNight"), day.get("windSpeedNight"),
            day.get("precip"), day.get("uvIndex"),
            day.get("humidity"), day.get("pressure"),
            day.get("vis"), day.get("cloud"),
            update_time
        )
        insert_query = """
        INSERT INTO weather_data (
            city, fx_date, sunrise, sunset, moonrise, moonset, moon_phase, moon_phase_icon,
            temp_max, temp_min, icon_day, text_day, icon_night, text_night,
            wind360_day, wind_dir_day, wind_scale_day, wind_speed_day,
            wind360_night, wind_dir_night, wind_scale_night, wind_speed_night,
            precip, uv_index, humidity, pressure, vis, cloud, update_time
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            sunrise=VALUES(sunrise), sunset=VALUES(sunset), temp_max=VALUES(temp_max), temp_min=VALUES(temp_min),
            text_day=VALUES(text_day), text_night=VALUES(text_night),
            wind_dir_day=VALUES(wind_dir_day), wind_scale_day=VALUES(wind_scale_day),
            precip=VALUES(precip), humidity=VALUES(humidity), update_time=VALUES(update_time)
        """
        try:
            cursor.execute(insert_query, values)
            print(f"{city} {fx_date} 数据插入成功: {day.get('textDay')}")
        except mysql.connector.Error as e:
            print(f"{city} {fx_date} 数据库错误: {e}")
    conn.commit()
    print(f"{city} 事务提交完成。")


def update_weather(force_update=False):
    conn = connect_db()
    cursor = conn.cursor()
    for city, location in city_codes.items():
        latest_time = get_latest_update_time(cursor, city)
        if should_update_data(latest_time, force_update):
            print(f"开始更新 {city} 天气数据...")
            data = fetch_weather_data(city, location)
            if data:
                store_weather_data(conn, cursor, city, data)
        else:
            print(f"{city} 数据已为最新。")
    cursor.close()
    conn.close()


def setup_scheduler():
    schedule.every().day.at("04:00").do(update_weather)
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    # 首次启动：建表 + 更新
    with mysql.connector.connect(**mysql_config) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS weather_data (
            id INT AUTO_INCREMENT PRIMARY KEY,
            city VARCHAR(50) NOT NULL,
            fx_date DATE NOT NULL,
            sunrise TIME, sunset TIME,
            moonrise TIME, moonset TIME,
            moon_phase VARCHAR(20), moon_phase_icon VARCHAR(10),
            temp_max INT, temp_min INT,
            icon_day VARCHAR(10), text_day VARCHAR(20),
            icon_night VARCHAR(10), text_night VARCHAR(20),
            wind360_day INT, wind_dir_day VARCHAR(20),
            wind_scale_day VARCHAR(10), wind_speed_day INT,
            wind360_night INT, wind_dir_night VARCHAR(20),
            wind_scale_night VARCHAR(10), wind_speed_night INT,
            precip DECIMAL(5,1), uv_index INT,
            humidity INT, pressure INT, vis INT, cloud INT,
            update_time DATETIME,
            UNIQUE KEY unique_city_date (city, fx_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()
    update_weather()
    setup_scheduler()
