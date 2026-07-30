"""SuperMOA — CLI 入口

启动方式：
  直接运行: python main.py
  托盘模式: 由 tray.py 在子线程调用 run_server()
"""
import argparse

from engine.auth import ensure_api_key, regenerate_api_key, get_current_key, mask_key
from engine.config import load_config, ensure_config, get_config_path


def main():
    """命令行直接启动"""
    parser = argparse.ArgumentParser(description="SuperMOA")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--regenerate-key", action="store_true", help="重新生成 API Key")
    args = parser.parse_args()

    # 首次启动：生成配置 + Key
    ensure_config()
    ensure_api_key()

    if args.regenerate_key:
        new_key = regenerate_api_key()
        print(f"\n新 API Key: {new_key}")
        print(f"masked: {mask_key(new_key)}\n")
        return

    config = load_config()
    host = args.host or config["gateway"].get("host", "127.0.0.1")
    port = args.port or config["gateway"].get("port", 12345)

    print("=" * 56)
    print("  SuperMOA — 多模型聚合推理系统")
    print("=" * 56)
    print(f"  API 端点 : http://{host}:{port}/v1/chat/completions")
    print(f"  配置页   : http://{host}:{port}/")
    print(f"  健康检查 : http://{host}:{port}/health")
    print(f"  API Key  : {mask_key(get_current_key())}")
    print(f"  配置文件 : {get_config_path()}")
    print("=" * 56)
    print("  按 Ctrl+C 停止")
    print()

    from app import run_server
    run_server(host, port)


if __name__ == "__main__":
    main()
