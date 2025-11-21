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
# PING_TARGET = "8.8.8.8"          # 用于延迟和丢包测试
PING_TARGET = "1.1.1.1"          # 用于延迟和丢包测试
NETWORK_IFACE = "eth0"           # 用于吞吐量采集的网口（树莓派一般 eth0 或 wlan0）
PING_INTERVAL = 1                 # 秒
SPEEDTEST_INTERVAL = 60           # 秒
# --------------------------------------------

# 创建目录
os.makedirs(DB_DIR, exist_ok=True)

# 连接数据库
conn = sqlite3.connect(DB_FILE)
cur = conn.cursor()

# 创建表，增加吞吐量列
cur.execute("""
CREATE TABLE IF NOT EXISTS network_data (
    timestamp TEXT PRIMARY KEY,
    download_mbps REAL,
    upload_mbps REAL,
    latency_ms REAL,
    jitter_ms REAL,
    packet_loss REAL,
    throughput_rx_mbps REAL,
    throughput_tx_mbps REAL
)
""")
conn.commit()

# -------------------- Ping 相关 --------------------
def parse_ping_rtt(line):
    match = re.search(r'=\s*([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)', line)
    if match:
        return float(match.group(2))
    return None

def run_ping():
    try:
        result = subprocess.run(
            ["ping", "-c", "4", PING_TARGET],
            capture_output=True, text=True, check=True
        )
        avg_latency = packet_loss = None
        for line in result.stdout.splitlines():
            if "packet loss" in line:
                packet_loss = float(line.split("%")[0].split()[-1])
            if "rtt min/avg/max/mdev" in line:
                avg_latency = parse_ping_rtt(line)
        return avg_latency, packet_loss
    except subprocess.CalledProcessError as e:
        print("Ping 执行失败:", e)
        return None, None

# -------------------- Speedtest 相关 --------------------
def run_speedtest():
    try:
        result = subprocess.run(
            ["speedtest-cli", "--json"],
            capture_output=True, text=True, check=True
        )
        data = json.loads(result.stdout)
        download = data.get("download", 0) / 1e6
        upload = data.get("upload", 0) / 1e6
        jitter = data.get("ping", None)
        return download, upload, jitter
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print("Speedtest 执行失败或解析失败:", e)
        return None, None, None

# -------------------- 吞吐量采集 --------------------
def get_iface_throughput(iface, interval, last_rx=None, last_tx=None):
    try:
        with open(f"/sys/class/net/{iface}/statistics/rx_bytes") as f:
            rx = int(f.read())
        with open(f"/sys/class/net/{iface}/statistics/tx_bytes") as f:
            tx = int(f.read())
        if last_rx is None or last_tx is None:
            return None, None, rx, tx
        rx_mbps = (rx - last_rx) * 8 / (interval * 1e6)
        tx_mbps = (tx - last_tx) * 8 / (interval * 1e6)
        return rx_mbps, tx_mbps, rx, tx
    except Exception as e:
        print("获取吞吐量失败:", e)
        return None, None, last_rx, last_tx

# -------------------- 主循环 --------------------
if __name__ == "__main__":
    print("Starlink 网络层采集启动...")

    last_speedtest = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
    last_rx = last_tx = None

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

        # 网口吞吐量
        throughput_rx, throughput_tx, last_rx, last_tx = get_iface_throughput(
            NETWORK_IFACE, PING_INTERVAL, last_rx, last_tx
        )

        # 写入数据库
        cur.execute("""
        INSERT OR REPLACE INTO network_data 
        (timestamp, download_mbps, upload_mbps, latency_ms, jitter_ms, packet_loss, throughput_rx_mbps, throughput_tx_mbps)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, download, upload, latency, jitter, packet_loss, throughput_rx, throughput_tx))
        conn.commit()

        print(f"[{timestamp}] latency={latency}ms packet_loss={packet_loss}% "
              f"download={download}Mbps upload={upload}Mbps jitter={jitter}ms "
              f"throughput_rx={throughput_rx}Mbps throughput_tx={throughput_tx}Mbps")

        time.sleep(PING_INTERVAL)
