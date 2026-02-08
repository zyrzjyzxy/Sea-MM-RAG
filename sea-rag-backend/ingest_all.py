from __future__ import annotations
import os
import sys
import shutil
import json
import hashlib
import argparse
from pathlib import Path
from datetime import datetime

# 添加项目根目录到 path 以便导入 services
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.pdf_service import convert_pdf_to_markdown, set_data_root as set_pdf_data_root
from services.index_service import build_faiss_index, set_data_root as set_index_data_root

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
DATA_ROOT = Path("data").resolve()
INGESTION_DIR = Path("raw_pdf_ingestion").resolve()
REGISTRY_FILE = DATA_ROOT / "file_registry.json"

def setup_directories():
    INGESTION_DIR.mkdir(parents=True, exist_ok=True)
    print(f"✅ 确保导入目录存在: {INGESTION_DIR}")

def load_registry() -> dict:
    if REGISTRY_FILE.exists():
        try:
            with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ 无法加载注册表，将创建新的: {e}")
            return {}
    return {}

def save_registry(registry: dict):
    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=4, ensure_ascii=False)

def generate_file_id(filename: str) -> str:
    """
    生成文件 ID。
    策略：简单的将文件名去后缀，并替换非安全字符。
    为了防止文件名冲突（不同目录下同名文件），理想情况应该包含 hash。
    但在本阶段，为了可读性，我们优先使用文件名 stem。
    """
    stem = Path(filename).stem
    # 替换空格和特殊字符
    safe_id = "".join([c if c.isalnum() or c in "-_" else "_" for c in stem])
    return safe_id

def ingest_one_file(pdf_path: Path, registry: dict, strategy: str = "hi_res", force: bool = False):
    filename = pdf_path.name
    print(f"\n[{filename}] 开始处理...")

    # 1. 检查是否已处理
    # 我们用文件名作为 key 的一部分，或者扫描 registry values?
    # 简单起见，我们计算 file_id，看是否存在
    file_id = generate_file_id(filename)
    
    if file_id in registry and not force:
        entry = registry[file_id]
        if entry.get("status") == "indexed":
            print(f"  ⏭️  跳过: 已索引 (文件 ID: {file_id})")
            return

    # 2. 准备工作目录
    work_dir = DATA_ROOT / file_id
    work_dir.mkdir(parents=True, exist_ok=True)
    
    dest_pdf = work_dir / "original.pdf"
    
    # 3. 复制文件
    try:
        shutil.copy2(pdf_path, dest_pdf)
        print(f"  ✅ 文件已复制到: {dest_pdf}")
    except Exception as e:
        print(f"  ❌ 复制失败: {e}")
        return

    # 4. 解析 PDF (Markdown + VLM)
    try:
        print(f"  🔄 正在解析 PDF (策略: {strategy})...")
        convert_pdf_to_markdown(file_id, strategy=strategy)
    except Exception as e:
        print(f"  ❌ 解析失败: {e}")
        registry[file_id] = {
            "original_name": filename,
            "status": "failed_parse",
            "last_update": datetime.now().isoformat(),
            "error": str(e)
        }
        save_registry(registry)
        return

    # 5. 建立索引
    try:
        print("  🔄 正在建立向量索引...")
        res = build_faiss_index(file_id)
        if not res["ok"]:
            raise Exception(res.get("error"))
        print(f"  ✅ 索引成功! 切片数: {res.get('chunks')}")
    except Exception as e:
        print(f"  ❌ 索引失败: {e}")
        registry[file_id] = {
            "original_name": filename,
            "status": "failed_index",
            "last_update": datetime.now().isoformat(),
            "error": str(e)
        }
        save_registry(registry)
        return

    # 6. 更新注册表
    registry[file_id] = {
        "original_name": filename,
        "file_id": file_id,
        "status": "indexed",
        "last_update": datetime.now().isoformat(),
        "source_path": str(pdf_path)
    }
    save_registry(registry)
    print("  🎉 处理完成")

def main():
    # 设置全局变量引用，必须在任何使用之前
    global DATA_ROOT, INGESTION_DIR, REGISTRY_FILE

    parser = argparse.ArgumentParser(description="批量导入 PDF 工具 (第二阶段)")
    parser.add_argument("--source", type=str, default=str(INGESTION_DIR), help="PDF 源目录")
    parser.add_argument("--force", action="store_true", help="强制重新处理已存在的文件")
    parser.add_argument("--strategy", type=str, default="hi_res", choices=["fast", "hi_res"], help="解析策略: fast 或 hi_res (默认: hi_res)")
    parser.add_argument("--data_root", type=str, default="data", help="数据根目录")
    
    args = parser.parse_args()
    
    # 更新全局配置
    DATA_ROOT = Path(args.data_root).resolve()
    INGESTION_DIR = Path(args.source).resolve()
    REGISTRY_FILE = DATA_ROOT / "file_registry.json"
    
    set_pdf_data_root(str(DATA_ROOT))
    set_index_data_root(str(DATA_ROOT))
    
    print(f"{'='*50}")
    print(f"🚀 Sea-RAG 批量导入工具")
    print(f"   源目录:   {INGESTION_DIR}")
    print(f"   数据目录: {DATA_ROOT}")
    print(f"   注册表:   {REGISTRY_FILE}")
    print(f"{'='*50}")
    
    setup_directories()

    if not INGESTION_DIR.exists():
        print(f"❌ 源目录不存在: {INGESTION_DIR}")
        return

    # 加载注册表
    registry = load_registry()
    
    # 扫描
    pdf_files = list(INGESTION_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"⚠️  在源目录 '{INGESTION_DIR}' 未找到 PDF 文件。")
        print("    👉 请将需要处理的 .pdf 文件放入该目录，然后再次运行此脚本。")
    else:
        print(f"发现 {len(pdf_files)} 个 PDF 文件。")
    
    for pdf in pdf_files:
        ingest_one_file(pdf, registry, strategy=args.strategy, force=args.force)

if __name__ == "__main__":
    main()
