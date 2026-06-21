#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : generate_demo_data.py
@Function: 生成 Etraval-agent 演示数据
- 覆盖 2026年6月-7月 4个城市的天气
- 高铁票：深圳-广州/北京/上海/成都/西安/武汉
- 机票：深圳-北京/上海/成都/西安/广州
- 演唱会票：周杰伦/刀郎/张学友/五月天 多城市
"""

import csv
import os
import random
from datetime import datetime, timedelta

random.seed(42)

DATA_DIR = os.path.join(os.path.dirname(__file__), "sql", "data")
os.makedirs(DATA_DIR, exist_ok=True)

today = datetime(2026, 6, 20)


# ==================== 1. 天气数据 ====================

def gen_weather():
    print("生成天气数据...")
    cities_weather = {
        "北京": {"temp_range": (22, 38), "weathers": ["晴", "多云", "阴", "雷阵雨", "小雨", "晴", "多云"]},
        "上海": {"temp_range": (24, 36), "weathers": ["多云", "阴", "小雨", "中雨", "晴", "多云", "阴"]},
        "广州": {"temp_range": (26, 35), "weathers": ["多云", "雷阵雨", "中雨", "阵雨", "晴", "多云", "阵雨"]},
        "深圳": {"temp_range": (27, 34), "weathers": ["多云", "阵雨", "雷阵雨", "晴", "多云", "小雨", "晴"]},
    }

    rows = []
    id_ = 1
    for city, info in cities_weather.items():
        temp_min, temp_max = info["temp_range"]
        weathers = info["weathers"]
        for day_offset in range(15):  # 15天预报
            fx_date = today + timedelta(days=day_offset)
            w = weathers[day_offset % len(weathers)]
            t_min = temp_min + random.randint(-2, 3)
            t_max = temp_max + random.randint(-3, 2)
            humidity = random.randint(35, 85)
            wind_dir = random.choice(["北风", "南风", "东风", "西风", "东南风", "西南风", "东北风", "西北风"])
            precip = round(random.uniform(0, 8) if "雨" in w else 0, 1)
            rows.append({
                "id": id_, "city": city, "fx_date": fx_date.strftime("%Y-%m-%d"),
                "sunrise": "05:30:00", "sunset": "19:00:00",
                "moonrise": "--", "moonset": "--",
                "moon_phase": "", "moon_phase_icon": "",
                "temp_max": t_max, "temp_min": t_min,
                "icon_day": "", "text_day": w,
                "icon_night": "", "text_night": w,
                "wind360_day": 0, "wind_dir_day": wind_dir, "wind_scale_day": "1-3", "wind_speed_day": 3,
                "wind360_night": 0, "wind_dir_night": wind_dir, "wind_scale_night": "1-3", "wind_speed_night": 3,
                "precip": precip, "uv_index": random.randint(3, 11),
                "humidity": humidity, "pressure": random.randint(990, 1010),
                "vis": random.randint(15, 30), "cloud": random.randint(10, 80),
                "update_time": today.strftime("%Y-%m-%d %H:%M:%S"),
            })
            id_ += 1
    return rows


# ==================== 2. 高铁票 ====================

TRAIN_NUMBERS = ["G101", "G203", "G305", "G407", "G509", "G611", "G713", "G815", "G901"]
SEAT_TYPES = ["二等座", "一等座", "商务座"]

def gen_trains():
    print("生成高铁票数据...")
    routes = [
        ("深圳", "广州", 0.5, 1.5, 80, 200),
        ("深圳", "北京", 8, 12, 800, 1200),
        ("深圳", "上海", 6, 10, 600, 1000),
        ("深圳", "成都", 7, 11, 500, 900),
        ("深圳", "西安", 8, 12, 600, 1100),
        ("深圳", "武汉", 4, 6, 400, 700),
        ("广州", "深圳", 0.5, 1.5, 80, 200),
        ("广州", "北京", 8, 12, 800, 1200),
        ("上海", "北京", 4, 7, 500, 800),
        ("北京", "上海", 4, 7, 500, 800),
        ("广州", "上海", 6, 10, 600, 1000),
        ("成都", "西安", 3, 5, 200, 400),
    ]

    rows = []
    id_ = 1
    for dep, arr, min_h, max_h, min_p, max_p in routes:
        for day_offset in range(7):  # 未来7天
            date = today + timedelta(days=day_offset)
            for _ in range(random.randint(3, 6)):  # 每天3-6趟
                h = random.randint(6, 20)
                m = random.choice([0, 5, 10, 15, 20, 30, 45])
                dep_time = date.replace(hour=h, minute=m)
                travel_h = random.randint(int(min_h * 2), int(max_h * 2)) / 2
                arr_time = dep_time + timedelta(hours=travel_h)
                tn = random.choice(TRAIN_NUMBERS)
                seat = random.choice(SEAT_TYPES)
                base_price = random.randint(min_p, max_p)
                if seat == "一等座":
                    price = int(base_price * 1.6)
                elif seat == "商务座":
                    price = int(base_price * 2.5)
                else:
                    price = base_price
                total = random.randint(400, 1200)
                remaining = random.randint(5, total)
                rows.append({
                    "id": id_, "departure_city": dep, "arrival_city": arr,
                    "departure_time": dep_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "arrival_time": arr_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "train_number": f"{tn}{random.randint(100,999)}",
                    "seat_type": seat,
                    "total_seats": total, "remaining_seats": remaining,
                    "price": float(price),
                    "created_at": today.strftime("%Y-%m-%d %H:%M:%S"),
                })
                id_ += 1
    return rows


# ==================== 3. 机票 ====================

FLIGHT_NUMBERS = ["CZ", "MU", "CA", "HU", "MF", "ZH", "3U"]

def gen_flights():
    print("生成机票数据...")
    routes = [
        ("深圳", "北京", 2.5, 3.5, 600, 2000),
        ("深圳", "上海", 2, 3, 500, 1800),
        ("深圳", "成都", 2.5, 3.5, 500, 1600),
        ("深圳", "西安", 3, 4, 400, 1500),
        ("深圳", "广州", 1, 1.5, 300, 800),
        ("北京", "上海", 2, 2.5, 500, 1500),
        ("北京", "广州", 3, 4, 600, 2000),
        ("上海", "成都", 3, 4, 500, 1800),
        ("广州", "北京", 3, 4, 600, 2000),
        ("深圳", "武汉", 2, 2.5, 400, 1200),
    ]

    rows = []
    id_ = 1
    for dep, arr, min_h, max_h, min_p, max_p in routes:
        for day_offset in range(7):
            date = today + timedelta(days=day_offset)
            for _ in range(random.randint(2, 5)):
                h = random.randint(6, 22)
                m = random.choice([0, 10, 20, 30, 40, 50])
                dep_time = date.replace(hour=h, minute=m)
                travel = random.randint(int(min_h * 60), int(max_h * 60))
                arr_time = dep_time + timedelta(minutes=travel)
                fn = random.choice(FLIGHT_NUMBERS)
                cabin = random.choice(["经济舱", "商务舱", "公务舱"])
                base = random.randint(min_p, max_p)
                if cabin == "商务舱":
                    price = int(base * 1.8)
                elif cabin == "公务舱":
                    price = int(base * 2.5)
                else:
                    price = base
                total = random.randint(120, 250)
                remaining = random.randint(1, total)
                rows.append({
                    "id": id_, "departure_city": dep, "arrival_city": arr,
                    "departure_time": dep_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "arrival_time": arr_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "flight_number": f"{fn}{random.randint(1000,9999)}",
                    "cabin_type": cabin,
                    "total_seats": total, "remaining_seats": remaining,
                    "price": float(price),
                    "created_at": today.strftime("%Y-%m-%d %H:%M:%S"),
                })
                id_ += 1
    return rows


# ==================== 4. 演唱会票 ====================

def gen_concerts():
    print("生成演唱会票数据...")
    concerts = [
        ("周杰伦", "深圳", "深圳大运中心体育馆", 380, 1880),
        ("周杰伦", "广州", "广州天河体育场", 380, 1880),
        ("周杰伦", "上海", "上海体育场", 480, 2080),
        ("周杰伦", "北京", "国家体育场（鸟巢）", 480, 2080),
        ("刀郎", "广州", "广州体育馆", 280, 1280),
        ("刀郎", "深圳", "深圳体育馆", 280, 1280),
        ("刀郎", "成都", "成都凤凰山体育公园", 280, 1280),
        ("张学友", "广州", "广州国际体育演艺中心", 380, 1680),
        ("张学友", "深圳", "深圳湾体育中心", 380, 1680),
        ("张学友", "上海", "梅赛德斯-奔驰文化中心", 480, 1980),
        ("五月天", "北京", "国家体育场（鸟巢）", 355, 1555),
        ("五月天", "上海", "上海体育场", 355, 1555),
        ("五月天", "深圳", "深圳大运中心体育馆", 355, 1555),
        ("邓紫棋", "广州", "广州大学城体育中心", 380, 1580),
        ("邓紫棋", "深圳", "深圳湾体育中心", 380, 1580),
        ("林俊杰", "北京", "凯迪拉克中心", 380, 1880),
        ("林俊杰", "上海", "梅赛德斯-奔驰文化中心", 380, 1880),
        ("薛之谦", "广州", "广州天河体育场", 317, 1717),
        ("薛之谦", "深圳", "深圳大运中心体育馆", 317, 1717),
        ("Taylor Swift", "上海", "上海体育场", 580, 3280),
    ]

    ticket_types = ["看台", "内场", "VIP"]
    rows = []
    id_ = 1
    for artist, city, venue, min_p, max_p in concerts:
        for day_offset in [7, 14, 21, 28, 35]:  # 未来多个周末
            date = today + timedelta(days=day_offset)
            if date.weekday() >= 5:  # 周末
                start = date.replace(hour=19, minute=30)
                end = date.replace(hour=22, minute=0)
                for ttype in ticket_types:
                    price = int(min_p + (max_p - min_p) * {"看台": 0, "内场": 0.4, "VIP": 0.8}[ttype])
                    total = random.randint(300, 600)
                    remaining = random.randint(10, total)
                    rows.append({
                        "id": id_, "artist": artist, "city": city, "venue": venue,
                        "start_time": start.strftime("%Y-%m-%d %H:%M:%S"),
                        "end_time": end.strftime("%Y-%m-%d %H:%M:%S"),
                        "ticket_type": ttype,
                        "total_seats": total, "remaining_seats": remaining,
                        "price": float(price),
                        "created_at": today.strftime("%Y-%m-%d %H:%M:%S"),
                    })
                    id_ += 1
    return rows


# ==================== 5. 写入 CSV ====================

def write_csv(filename, fieldnames, rows):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {filename}: {len(rows)} 条")


if __name__ == "__main__":
    print("=" * 50)
    print("Etraval-agent 演示数据生成器")
    print(f"基准日期: {today.strftime('%Y-%m-%d')}")
    print("=" * 50)

    # 天气
    weather = gen_weather()
    wf = ["id","city","fx_date","sunrise","sunset","moonrise","moonset","moon_phase","moon_phase_icon",
          "temp_max","temp_min","icon_day","text_day","icon_night","text_night",
          "wind360_day","wind_dir_day","wind_scale_day","wind_speed_day",
          "wind360_night","wind_dir_night","wind_scale_night","wind_speed_night",
          "precip","uv_index","humidity","pressure","vis","cloud","update_time"]
    write_csv("weather_data.csv", wf, weather)

    # 高铁
    trains = gen_trains()
    tf = ["id","departure_city","arrival_city","departure_time","arrival_time",
          "train_number","seat_type","total_seats","remaining_seats","price","created_at"]
    write_csv("train_tickets.csv", tf, trains)

    # 机票
    flights = gen_flights()
    ff = ["id","departure_city","arrival_city","departure_time","arrival_time",
          "flight_number","cabin_type","total_seats","remaining_seats","price","created_at"]
    write_csv("flight_tickets.csv", ff, flights)

    # 演唱会
    concerts = gen_concerts()
    cf = ["id","artist","city","venue","start_time","end_time",
          "ticket_type","total_seats","remaining_seats","price","created_at"]
    write_csv("concert_tickets.csv", cf, concerts)

    print(f"\n✅ 全部生成完成！数据已写入 {DATA_DIR}")
