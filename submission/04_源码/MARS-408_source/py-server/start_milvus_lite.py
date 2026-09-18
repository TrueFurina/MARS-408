"""启动嵌入式 Milvus Lite 服务器并保持运行"""
import os
import sys
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("milvus_lite")

def main():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "milvus_lite_data")
    os.makedirs(data_dir, exist_ok=True)

    import milvus_lite as ml
    uri = ml.server_manager_instance.start_and_get_uri(data_dir)
    logger.info(f"Milvus Lite 已启动: {uri}")

    # 输出 URI 到文件供其他进程读取
    uri_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".milvus_uri")
    with open(uri_file, "w") as f:
        f.write(uri)
    logger.info(f"URI 已写入: {uri_file}")

    # 更新 config.json
    import json
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    with open(cfg_path, "r") as f:
        cfg = json.load(f)
    cfg["milvus"]["uri"] = uri
    cfg["milvus"]["host"] = uri.replace("http://", "").split(":")[0]
    cfg["milvus"]["port"] = int(uri.split(":")[-1])
    cfg["milvus"]["enabled"] = True
    with open(cfg_path, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    logger.info(f"config.json 已更新")

    # 保持运行
    while True:
        time.sleep(30)

if __name__ == "__main__":
    main()
