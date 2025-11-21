#!/bin/bash
echo "启动 Starlink 数据采集..."
sleep 10  # 等待外置硬盘挂载

# 激活物理层虚拟环境
cd /home/hanlincai/Desktop/starlink-grpc-tools
source venv/bin/activate

nohup python3 dish_grpc_sqlite.py -t 5 /media/hanlincai/PSSD/starlink_data_new/starlink_all.sqlite status obstruction_detail alert_detail location ping_drop ping_run_length ping_latency ping_loaded_latency usage power bulk_history

# python3 dish_grpc_sqlite.py -t 5 -d /media/hanlincai/PSSD/starlink_data_new/starlink_all.sqlite \
# status obstruction_detail alert_detail location ping_drop ping_run_length ping_latency ping_loaded_latency usage power bulk_history \
# > /home/hanlincai/Desktop/starlink-grpc-tools/dish_log.txt 2>&1 &

# 启动网络层采集
cd /home/hanlincai/Desktop/network_layer
nohup python3 starlink_network_data.py 

# python3 starlink_network_data.py \
# > /home/hanlincai/Desktop/network_layer/network_log.txt 2>&1 &

echo "✅ 物理层与网络层采集程序均已启动。"
