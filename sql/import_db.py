#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : import_db.py
@Function: 虚拟数据导入工具（迁移自 SmartVoyage）
- 将 data/ 目录下的 CSV 虚拟数据导入 MySQL
- 方便在没有真实API的情况下演示系统功能
"""
import pandas as pd
import pymysql
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from configs.llm_config import mysql_config

# CSV 虚拟数据文件路径（相对于本文件）
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CSV_FILES = {
    "train_tickets": os.path.join(DATA_DIR, "train_tickets.csv"),
    "flight_tickets": os.path.join(DATA_DIR, "flight_tickets.csv"),
    "concert_tickets": os.path.join(DATA_DIR, "concert_tickets.csv"),
    "weather_data": os.path.join(DATA_DIR, "weather_data.csv"),
}


def insert_csv_to_table(connection, table_name, csv_path, batch_size=500):
    """读取CSV并插入数据库"""
    if not os.path.exists(csv_path):
        print(f"⚠️  文件不存在，跳过: {csv_path}")
        return

    print(f"开始导入 {table_name} ...")
    df = pd.read_csv(csv_path)
    df = df.drop(columns=['id'], errors='ignore')
    columns = list(df.columns)
    column_str = ",".join(columns)
    placeholder = ",".join(["%s"] * len(columns))
    sql = f"INSERT IGNORE INTO {table_name} ({column_str}) VALUES ({placeholder})"
    cursor = connection.cursor()
    data = df.values.tolist()
    total = len(data)

    for i in range(0, total, batch_size):
        batch = data[i:i + batch_size]
        cursor.executemany(sql, batch)
        connection.commit()
        print(f"{table_name} 已导入 {min(i + batch_size, total)}/{total} 条")

    cursor.close()
    print(f"{table_name} 导入完成（共{total}条）\n")


def main():
    print("=== Etraval-agent 虚拟数据导入工具 ===")
    print(f"数据库: {mysql_config['host']}:{mysql_config.get('port', 3306)}/{mysql_config['database']}")

    conn = pymysql.connect(**mysql_config)
    try:
        # 先执行建表
        schema_path = os.path.join(os.path.dirname(__file__), "mysql_schema.sql")
        if os.path.exists(schema_path):
            print("执行建表脚本...")
            with open(schema_path, 'r', encoding='utf-8') as f:
                sql_script = f.read()
            # 逐条执行（跳过 DROP/CREATE DATABASE）
            statements = [s.strip() for s in sql_script.split(';') if s.strip()]
            cursor = conn.cursor()
            for stmt in statements:
                if stmt.upper().startswith('CREATE TABLE'):
                    cursor.execute(stmt + ';')
            conn.commit()
            cursor.close()
            print("建表完成\n")

        # 导入 CSV 数据
        for table_name, csv_path in CSV_FILES.items():
            insert_csv_to_table(conn, table_name, csv_path)

        print("✅ 全部数据导入完成！")

    except Exception as e:
        print(f"❌ 导入失败: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
