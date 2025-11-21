#!/usr/bin/env python3
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import datetime
import os

# -------------------- 配置 --------------------
PHY_DB = "/media/hanlincai/PSSD/starlink_data_new/1107_backup/starlink_all_1107_2_A_network_layer.sqlite"
NET_DB = "/media/hanlincai/PSSD/starlink_network_layer/1107_backup/starlink_network_1107_2B_net_layer.sqlite"
OUTPUT_DIR = "/media/hanlincai/PSSD"
os.makedirs(OUTPUT_DIR, exist_ok=True)
# ---------------------------------------------

def read_sqlite_table(db_path, table):
    """读取 sqlite 表为 DataFrame"""
    try:
        with sqlite3.connect(db_path) as conn:
            df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
        print(f"[OK] Loaded {table} ({len(df)} rows)")
        return df
    except Exception as e:
        print(f"[WARN] Failed to read {table}: {e}")
        return pd.DataFrame()

# -------------------- 读取网络层 --------------------
net = read_sqlite_table(NET_DB, "network_data")
if not net.empty:
    net["timestamp"] = pd.to_datetime(net["timestamp"], utc=True)
else:
    raise RuntimeError("network_data 表为空")

# -------------------- 读取物理层 --------------------
phy = read_sqlite_table(PHY_DB, "status")
if not phy.empty:
    if "time" in phy.columns:
        phy["timestamp"] = pd.to_datetime(phy["time"], unit="s", utc=True)
    elif "timestamp" in phy.columns:
        phy["timestamp"] = pd.to_datetime(phy["timestamp"], utc=True)
    else:
        raise RuntimeError("物理层表中找不到时间戳列 (time/timestamp)")
else:
    raise RuntimeError("status 表为空")

# -------------------- 关键字段检查 --------------------
if "snr" not in phy.columns:
    phy["snr"] = None
if "obstruction_percent" not in phy.columns:
    phy["obstruction_percent"] = None

# -------------------- 合并 --------------------
df = pd.merge_asof(
    net.sort_values("timestamp"),
    phy.sort_values("timestamp"),
    on="timestamp",
    direction="nearest",
    tolerance=pd.Timedelta(seconds=5)
)

print(f"[INFO] 合并后样本数: {len(df)}")
df.dropna(subset=["latency_ms"], inplace=True)

# -------------------- 可视化 --------------------
plt.figure(figsize=(12, 6))
plt.plot(df["timestamp"], df["latency_ms"], label="Latency (ms)", color="tab:blue")
plt.ylabel("Latency (ms)", color="tab:blue")
plt.xlabel("Time (UTC)")
plt.twinx()
plt.plot(df["timestamp"], df["snr"], label="SNR (dB)", color="tab:orange", alpha=0.7)
plt.ylabel("SNR (dB)", color="tab:orange")
plt.title("Network Latency vs SNR")
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, "latency_vs_snr.png"))
plt.close()

plt.figure(figsize=(12, 6))
plt.plot(df["timestamp"], df["throughput_rx_mbps"], label="RX Throughput", color="tab:green")
plt.plot(df["timestamp"], df["throughput_tx_mbps"], label="TX Throughput", color="tab:red")
plt.legend()
plt.xlabel("Time (UTC)")
plt.ylabel("Throughput (Mbps)")
plt.twinx()
plt.plot(df["timestamp"], df["snr"], label="SNR", color="tab:orange", alpha=0.5)
plt.ylabel("SNR (dB)")
plt.title("Throughput vs SNR")
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, "throughput_vs_snr.png"))
plt.close()

plt.figure(figsize=(12, 6))
plt.scatter(df["obstruction_percent"], df["download_mbps"], alpha=0.6, label="Download vs Obstruction")
plt.xlabel("Obstruction (%)")
plt.ylabel("Download Speed (Mbps)")
plt.title("Speedtest Download vs Obstruction")
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, "download_vs_obstruction.png"))
plt.close()

print(f"\n✅ 可视化完成！图像已保存到：{OUTPUT_DIR}")