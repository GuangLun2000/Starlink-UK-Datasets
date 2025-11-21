#!/usr/bin/env python3
import os
import sqlite3
import subprocess
import json
import datetime
import time
import re
import math

# -------------------- 配置 --------------------
DB_DIR = "/media/hanlincai/PSSD/starlink_network_layer"
DB_FILE = os.path.join(DB_DIR, "starlink_network_layer_B.sqlite")

# PING_TARGET = "1.1.1.1"           # Cloudflare DNS（响应更稳定）
PING_TARGET = "8.8.8.8"
NETWORK_IFACE = "eth0"            # 树莓派有线网口（若用 WiFi 改成 wlan0）
PING_INTERVAL = 1                 # 秒
SPEEDTEST_INTERVAL = 120          # 每 2 分钟测速一次
MAX_RETRY = 10                     # Speedtest 最大重试次数
# --------------------------------------------

# 创建目录
os.makedirs(DB_DIR, exist_ok=True)

# 连接数据库
conn = sqlite3.connect(DB_FILE, timeout=10)
cur = conn.cursor()

# 创建表
cur.execute("""
CREATE TABLE IF NOT EXISTS network_data (
    timestamp TEXT PRIMARY KEY,
    download_mbps REAL,
    upload_mbps REAL,
    latency_ms REAL,
    jitter_ms REAL,
    packet_loss REAL,
    throughput_rx_mbps REAL,
    throughput_tx_mbps REAL,
    notes TEXT
)
""")
conn.commit()

# -------------------- Ping --------------------
def parse_ping_rtt(line):
    match = re.search(r'=\s*([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)', line)
    return float(match.group(2)) if match else None

def run_ping():
    try:
        result = subprocess.run(
            ["ping", "-c", "4", "-w", "5", PING_TARGET],
            capture_output=True, text=True
        )
        avg_latency = packet_loss = None
        for line in result.stdout.splitlines():
            if "packet loss" in line:
                packet_loss = float(line.split("%")[0].split()[-1])
            elif "rtt min/avg/max/mdev" in line:
                avg_latency = parse_ping_rtt(line)
        return avg_latency, packet_loss
    except Exception as e:
        print(f"Ping 执行异常: {e}")
        return None, None

# -------------------- Speedtest --------------------
def run_speedtest():
    """容错测速，失败自动重试"""
    for attempt in range(1, MAX_RETRY + 1):
        try:
            result = subprocess.run(
                ["speedtest-cli", "--json"],
                capture_output=True, text=True
            )
            if result.returncode != 0 or not result.stdout.strip():
                print(f"Speedtest 失败 (尝试 {attempt}/{MAX_RETRY})，状态码 {result.returncode}")
                time.sleep(5)
                continue

            data = json.loads(result.stdout)
            download = data.get("download", 0) / 1e6
            upload = data.get("upload", 0) / 1e6
            jitter = data.get("ping", None)
            return download, upload, jitter, "ok"
        except json.JSONDecodeError:
            print(f"Speedtest JSON 解析失败 (尝试 {attempt}/{MAX_RETRY})")
        except Exception as e:
            print(f"Speedtest 异常: {e}")
        time.sleep(5)
    return None, None, None, "speedtest_failed"

# -------------------- 吞吐量 --------------------
def get_iface_throughput(iface, interval, last_rx=None, last_tx=None):
    try:
        with open(f"/sys/class/net/{iface}/statistics/rx_bytes") as f:
            rx = int(f.read())
        with open(f"/sys/class/net/{iface}/statistics/tx_bytes") as f:
            tx = int(f.read())
        if last_rx is None or last_tx is None:
            return None, None, rx, tx
        rx_mbps = max((rx - last_rx) * 8 / (interval * 1e6), 0)
        tx_mbps = max((tx - last_tx) * 8 / (interval * 1e6), 0)
        return rx_mbps, tx_mbps, rx, tx
    except Exception as e:
        print("获取吞吐量失败:", e)
        return None, None, last_rx, last_tx

# -------------------- 主循环 --------------------
if __name__ == "__main__":
    print("🚀 Starlink 网络层数据采集启动中...")

    last_speedtest = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
    last_rx = last_tx = None

    while True:
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Ping 测试
        latency, packet_loss = run_ping()

        # Speedtest（间隔控制 + 自动容错）
        now = datetime.datetime.now(datetime.timezone.utc)
        if (now - last_speedtest).total_seconds() >= SPEEDTEST_INTERVAL:
            download, upload, jitter, note = run_speedtest()
            last_speedtest = now
        else:
            download = upload = jitter = None
            note = None

        # 吞吐量
        throughput_rx, throughput_tx, last_rx, last_tx = get_iface_throughput(
            NETWORK_IFACE, PING_INTERVAL, last_rx, last_tx
        )

        # 写入数据库
        cur.execute("""
        INSERT OR REPLACE INTO network_data
        (timestamp, download_mbps, upload_mbps, latency_ms, jitter_ms, packet_loss, throughput_rx_mbps, throughput_tx_mbps, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, download, upload, latency, jitter, packet_loss, throughput_rx, throughput_tx, note))
        conn.commit()

        # 打印状态
        print(f"[{timestamp}] latency={latency}ms packet_loss={packet_loss}% "
              f"download={download}Mbps upload={upload}Mbps jitter={jitter}ms "
              f"throughput_rx={throughput_rx}Mbps throughput_tx={throughput_tx}Mbps note={note}")

        time.sleep(PING_INTERVAL)
