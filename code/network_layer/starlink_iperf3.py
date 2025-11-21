#!/usr/bin/env python3
import os
import sqlite3
import subprocess
import json
import datetime
import time
import re

# -------------------- 配置 --------------------
DB_DIR = "/media/hanlincai/PSSD/starlink_network_layer"
DB_FILE = os.path.join(DB_DIR, "starlink_network.sqlite")
PING_TARGET = "8.8.8.8"        # 用于延迟和丢包测试
# PING_TARGET = "192.168.100.1" 
PING_INTERVAL = 5             # 秒
SPEEDTEST_INTERVAL = 600          # 每 10 分钟测速一次
# --------------------------------------------

# 创建目录
os.makedirs(DB_DIR, exist_ok=True)

# 连接数据库
conn = sqlite3.connect(DB_FILE)
cur = conn.cursor()

# 创建表
cur.execute("""
CREATE TABLE IF NOT EXISTS network_data (
    timestamp TEXT PRIMARY KEY,
    download_mbps REAL,
    upload_mbps REAL,
    latency_ms REAL,
    jitter_ms REAL,
    packet_loss REAL
)
""")
conn.commit()

def parse_ping_rtt(line):
    """
    解析 rtt 行，返回平均延迟
    示例行:
    rtt min/avg/max/mdev = 20.123/25.456/30.789/20.274 ms
    """
    match = re.search(r'=\s*([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)', line)
    if match:
        avg_rtt = float(match.group(2))
        return avg_rtt
    return None

def run_ping():
    """通过 ping 获取延迟和丢包"""
    try:
        result = subprocess.run(
            ["ping", "-c", "4", PING_TARGET],
            capture_output=True, text=True, check=True
        )
        output = result.stdout
        avg_latency = None
        packet_loss = None
        for line in output.splitlines():
            if "packet loss" in line:
                # 提取丢包率
                packet_loss = float(line.split("%")[0].split()[-1])
            if "rtt min/avg/max/mdev" in line:
                avg_latency = parse_ping_rtt(line)
        return avg_latency, packet_loss
    except subprocess.CalledProcessError as e:
        print("Ping 执行失败:", e)
        return None, None

def run_speedtest():
    """通过 speedtest 测上下行带宽"""
    try:
        result = subprocess.run(
            ["speedtest-cli", "--json"],
            capture_output=True, text=True, check=True
        )
        data = json.loads(result.stdout)
        download = data.get("download", 0) / 1e6  # 转换为 Mbps
        upload = data.get("upload", 0) / 1e6
        jitter = data.get("ping", None)           # speedtest 返回的 ping
        return download, upload, jitter
    except subprocess.CalledProcessError as e:
        print("Speedtest 执行失败:", e)
        return None, None, None
    except json.JSONDecodeError as e:
        print("Speedtest 输出解析失败:", e)
        return None, None, None

if __name__ == "__main__":
    print("Starlink 网络层采集启动...")

    last_speedtest = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)

    while True:
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # ping 测试
        latency, packet_loss = run_ping()

        # speedtest 测试，每隔 SPEEDTEST_INTERVAL 秒执行一次
        now = datetime.datetime.now(datetime.timezone.utc)
        if (now - last_speedtest).total_seconds() >= SPEEDTEST_INTERVAL:
            download, upload, jitter = run_speedtest()
            last_speedtest = now
        else:
            download = upload = jitter = None

        # 写入数据库
        cur.execute("""
        INSERT OR REPLACE INTO network_data 
        (timestamp, download_mbps, upload_mbps, latency_ms, jitter_ms, packet_loss)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (timestamp, download, upload, latency, jitter, packet_loss))
        conn.commit()

        print(f"[{timestamp}] latency={latency}ms packet_loss={packet_loss}% "
              f"download={download}Mbps upload={upload}Mbps jitter={jitter}ms")

        time.sleep(PING_INTERVAL)
