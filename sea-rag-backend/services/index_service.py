# services/index_service.py
from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any, Optional
import os
import argparse
import shutil
import re

from langchain_community.embeddings import HuggingFaceBgeEmbeddings
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import MarkdownHeaderTextSplitter
# LangChain imports
try:
    from langchain_core.documents import Document
except ImportError:
    from langchain.docstore.document import Document

import warnings
from langchain_core._api.deprecation import LangChainDeprecationWarning
warnings.filterwarnings("ignore", category=LangChainDeprecationWarning)

from langchain_community.vectorstores import FAISS
from dotenv import load_dotenv

load_dotenv(override=True)

# ---------------------------------------------------------------------------
# 全局配置
# ---------------------------------------------------------------------------
DATA_ROOT = Path(os.getenv("DATA_ROOT", "data")).resolve()
GLOBAL_INDEX_DIR = DATA_ROOT / "global_index"

def set_data_root(path: str):
    global DATA_ROOT, GLOBAL_INDEX_DIR
    DATA_ROOT = Path(path).resolve()
    GLOBAL_INDEX_DIR = DATA_ROOT / "global_index"

def workdir(file_id: str) -> Path:
    """获取指定文件的工作目录（中间产物存放地）"""
    p = DATA_ROOT / file_id
    p.mkdir(parents=True, exist_ok=True)
    return p

def markdown_path(file_id: str) -> Path:
    return workdir(file_id) / "output.md"

def get_original_pdf_name(file_id: str) -> str:
    """尝试确定原始 PDF 文件名。默认为 'original.pdf' 或 file_id。"""
    # 这是一个启发式方法。在实际系统中，我们应该查询数据库。
    # 目前，我们检查是否存在除了 output.md/original.pdf 之外的文件？
    # 或者直接返回 file_id 作为后备方案。
    wd = workdir(file_id)
    # 如果我们将文件名保存在了侧边栏文件中，我们将读取它。
    # 目前，为了重构索引服务，我们假设 raw_pdf_ingestion 可能存在。
    # 如果没有找到更好的名称，我们将返回 file_id 作为源名称。
    return f"{file_id}.pdf"

# ---------------------------------------------------------------------------
# 嵌入模型 (Embeddings)
# ---------------------------------------------------------------------------
def load_embeddings():
    """加载嵌入模型 (BGE 或 OpenAI)"""
    # print("[*] 正在加载嵌入模型...")
    try:
        model_name = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-small-zh-v1.5")
        # 检查本地模型是否存在或直接尝试加载
        embed = HuggingFaceBgeEmbeddings(
            model_name=model_name, 
            model_kwargs={'device': 'cpu'}, 
            encode_kwargs={'normalize_embeddings': True}
        )
        return embed
    except Exception as e:
        print(f"❌ 本地嵌入加载失败: {e}")
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            print("[*] 降级使用 OpenAI Embeddings...")
            return OpenAIEmbeddings(model="text-embedding-3-small")
        else:
            print("⚠️ 警告: 未找到 API Key。正在使用 FakeEmbeddings。")
            from langchain_community.embeddings import FakeEmbeddings 
            return FakeEmbeddings(size=512)

# ---------------------------------------------------------------------------
# 文本切分与元数据注入
# ---------------------------------------------------------------------------
def split_markdown_with_page_tracking(md_text: str, file_id: str, source: str) -> List[Document]:
    """
    切分 Markdown 内容，并注入 'file_id', 'source' 和 'page'（页码）元数据。
    依赖于 pdf_service 注入的 '<!-- PAGE_BREAK: n -->' 标记。
    """
    
    # 1. 根据分页标记进行切分
    # 正则表达式查找 <!-- PAGE_BREAK: (\d+) -->
    # 我们使用捕获组来保留分隔符，以便知道页码
    page_splits = re.split(r'(<!--\s*PAGE_BREAK:\s*(\d+)\s*-->)', md_text)
    
    documents = []
    
    # 初始页码（第一个分隔符之前的内容）
    current_page = 1 
    
    # page_splits 结果结构: [text_before, marker_full, page_num, text_after, marker_full, page_num, ...]
    # 这种结构建议我们要小心遍历。
    
    # 如果文件以没有任何分隔符的文本开始，该文本属于第 1 页（默认）。
    
    # 让我们处理这个列表。
    # 待切分的文本缓冲区
    current_text_buffer = ""
    
    # 第一个元素总是文本（可能为空）
    if len(page_splits) > 0:
        current_text_buffer = page_splits[0]
    
    # 辅助函数：处理并切分缓冲区文本
    def process_buffer(text, page):
        if not text.strip():
            return
        
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        
        # 使用递归字符切分器作为主切分器，或者作为 Header 切分后的补充。
        # 这里为了稳健性，直接使用递归切分，确保所有文本（包括引用块）都能被捕获。
        # 尤其是当 PDF 解析的 Header 结构不完美时，HeaderSplitter 可能会漏掉内容或分块过大。
        
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n\n", "\n", " ", ""]
        )
        docs = text_splitter.create_documents([text])
        
        for d in docs:
            # 注入元数据
            d.metadata["file_id"] = file_id
            d.metadata["source"] = source
            d.metadata["page"] = int(page)
            # 清理内容
            d.page_content = d.page_content.strip()
            if d.page_content:
                 documents.append(d)

    # 处理第一个块（逻辑：如果第一个块为空，意味着文件以分隔符开始？）
    # 如果没有找到分隔符，长度为 1。
    if len(page_splits) == 1:
        process_buffer(current_text_buffer, 1)
        return documents

    # 遍历三元组 (marker, page_num, text)
    # i 的范围: 从 1 开始, 步长为 3
    
    # 首先处理初始缓冲区
    process_buffer(current_text_buffer, 1)

    for i in range(1, len(page_splits), 3):
        # marker = page_splits[i]   # <!-- PAGE_BREAK: 2 -->
        page_num_str = page_splits[i+1] # 2
        content = page_splits[i+2]      # Text...
        
        current_page = int(page_num_str)
        process_buffer(content, current_page)
        
    return documents

# ---------------------------------------------------------------------------
# 全局索引管理
# ---------------------------------------------------------------------------
def get_global_index(embeddings) -> FAISS:
    """加载全局索引或创建新索引"""
    if GLOBAL_INDEX_DIR.exists() and (GLOBAL_INDEX_DIR / "index.faiss").exists():
        # print(f"[*] 正在从 {GLOBAL_INDEX_DIR} 加载全局索引")
        return FAISS.load_local(str(GLOBAL_INDEX_DIR), embeddings, allow_dangerous_deserialization=True)
    else:
        print(f"[*] 正在 {GLOBAL_INDEX_DIR} 创建新的全局索引")
        # 初始化时需要至少一段文本。
        # 我们可以实现一个干净的“空创建”逻辑，但这里更容易的是返回 None 并让调用者处理，
        # 或者用 1 个虚拟文档创建。
        # 策略：调用者处理 'if index is None: create from docs'
        return None

def build_faiss_index(file_id: str) -> Dict[str, Any]:
    """
    重构后：将文件内容添加到全局索引（增量更新）。
    虽然概念上改名为“索引服务”，但为了保持兼容性，函数名暂时保留。
    """
    md_file = markdown_path(file_id)
    if not md_file.exists():
        return {"ok": False, "error": f"未找到_MARKDOWN_文件: {md_file}"}
    
    try:
        md_text = md_file.read_text(encoding="utf-8")
    except Exception as e:
        return {"ok": False, "error": f"读取错误: {e}"}

    # 准备元数据
    source_name = get_original_pdf_name(file_id)
    
    # 带元数据的切分
    docs = split_markdown_with_page_tracking(md_text, file_id, source_name)
    if not docs:
        return {"ok": False, "error": "切分后无文档 (NO_DOCS_AFTER_SPLIT)"}

    print(f"[*] 正在为 {file_id} 添加 {len(docs)} 个切片到全局索引...")
    
    embeddings = load_embeddings()
    global_index = get_global_index(embeddings)
    
    if global_index is None:
        # 创建新的
        global_index = FAISS.from_documents(docs, embedding=embeddings)
    else:
        #要在现有的基础上追加
        global_index.add_documents(docs)
    
    # 保存
    GLOBAL_INDEX_DIR.mkdir(parents=True, exist_ok=True)
    global_index.save_local(str(GLOBAL_INDEX_DIR))
    print(f"[*] 全局索引已保存至 {GLOBAL_INDEX_DIR}")
    
    return {"ok": True, "chunks": len(docs), "index_path": str(GLOBAL_INDEX_DIR)}

def search_faiss(query: str, filters: Dict[str, Any] = None, k: int = 5) -> Dict[str, Any]:
    """
    搜索全局索引。
    'filters' 参数可用于元数据过滤 (例如 {'file_id': '...'})。
    """
    if not (GLOBAL_INDEX_DIR / "index.faiss").exists():
        return {"ok": False, "error": "全局索引未找到 (GLOBAL_INDEX_NOT_FOUND)"}

    embeddings = load_embeddings()
    try:
        vs = FAISS.load_local(str(GLOBAL_INDEX_DIR), embeddings, allow_dangerous_deserialization=True)
        
        # 如果提供了过滤器则应用
        # LangChain FAISS 支持 filter 参数？是的，通常支持。
        # 这取决于底层存储。如果使用 metadata，FAISS 是支持的。
        kwargs = {}
        if filters:
            # kwargs['filter'] = filters 
            # 注意：LangChain 基础版的 FAISS 实现可能需要特定设置才完全支持复杂过滤器，
            # 但通常基础的字典匹配是有效的。
            kwargs['filter'] = filters

        search_kwargs = {"k": k, **kwargs}
        hits = vs.similarity_search_with_score(query, **search_kwargs)
        
        results = []
        for doc, score in hits:
            results.append({
                "text": doc.page_content,
                "score": float(score),
                "metadata": doc.metadata, # 现在包含页码 (page) 和来源 (source)
            })
        return {"ok": True, "results": results}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ---------------------------------------------------------------------------
# 命令行接口 (CLI)
# ---------------------------------------------------------------------------

"""
构建命令

python services/index_service.py build --file_id test_001

检索命令

python services/index_service.py search --query "langchain" --file_id test_001
"""

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="全局索引服务 (重构版)")
    subparsers = parser.add_subparsers(dest="command", help="指令")

    # build
    build_parser = subparsers.add_parser("build", help="将文件添加到全局索引")
    build_parser.add_argument("--file_id", type=str, required=True, help="文件 ID")
    build_parser.add_argument("--data_root", type=str, default="data", help="数据根目录")

    # search
    search_parser = subparsers.add_parser("search", help="搜索全局索引")
    search_parser.add_argument("--query", type=str, required=True, help="查询语句")
    search_parser.add_argument("--file_id", type=str, help="可选：按文件 ID 过滤")
    search_parser.add_argument("--k", type=int, default=3, help="返回结果数量")
    search_parser.add_argument("--data_root", type=str, default="data", help="数据根目录")

    args = parser.parse_args()

    if args.command == "build":
        set_data_root(args.data_root)
        print(f"\n>>> 正在索引: {args.file_id}")
        res = build_faiss_index(args.file_id)
        print(f"结果: {res}")
    
    elif args.command == "search":
        set_data_root(args.data_root)
        print(f"\n>>> 正在搜索: {args.query}")
        filters = None
        if args.file_id:
            filters = {"file_id": args.file_id}
            print(f"    过滤器: {filters}")
            
        res = search_faiss(args.query, filters=filters, k=args.k)
        if res["ok"]:
            for i, r in enumerate(res["results"]):
                m = r['metadata']
                print(f"\n结果 {i+1} (匹配度: {r['score']:.4f}):")
                print(f"来源: {m.get('source')} (第 {m.get('page')} 页)")
                print(f"内容: {r['text'][:100]}...")
        else:
            print(f"❌ 错误: {res.get('error')}")
    else:
        parser.print_help()
