# services/rag_service.py
from __future__ import annotations
import os, asyncio, textwrap
import argparse
from typing import List, Dict, Any, Tuple, AsyncGenerator, Optional
from typing_extensions import TypedDict

from dotenv import load_dotenv
load_dotenv(override=True)

from langchain.chat_models import init_chat_model
from langchain_community.embeddings import HuggingFaceBgeEmbeddings
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from collections import defaultdict
from pathlib import Path

# 存储结构：sessions[session_id] = [{"role":"user|assistant","content":"..."}...]
_sessions: dict[str, list[dict]] = defaultdict(list)

def get_history(session_id: str) -> list[dict]:
    return _sessions.get(session_id, [])

def append_history(session_id: str, role: str, content: str) -> None:
    _sessions[session_id].append({"role": role, "content": content})

def clear_history(session_id: str) -> None:
    _sessions.pop(session_id, None)

# ---------------- 配置 ----------------
# 请根据实际情况调整模型名称
MODEL_NAME = os.getenv("CHAT_MODEL_NAME", "deepseek-ai/DeepSeek-V3")
SILICON_BASE_URL = os.getenv("SILICON_BASE_URL", "https://api.siliconflow.cn/v1")
MODEL_PROVIDER = "openai" # SiliconFlow 兼容 OpenAI 接口
TEMPERATURE = 0.3

K = 5 # 增加召回数量以支持多文档
SCORE_TAU_TOP1 = 0.50 # 稍微放宽阈值
SCORE_TAU_MEAN3 = 0.65

SCORE_TAU_MEAN3 = 0.65
DATA_ROOT = Path(os.getenv("DATA_ROOT", "data")).resolve()
GLOBAL_INDEX_DIR = DATA_ROOT / "global_index"

SYSTEM_INSTRUCTION = (
    "你是**海洋装备领域的资深技术与学术专家**（Marine Equipment Technical Expert）。\n"
    "你的核心职责是辅助用户进行海洋设备（如无人艇、水下航行器、传感器等）的原理研读、技术维护、故障排查及前沿文献解读。\n"
    "**行为准则**：\n"
    "1. **安全与严谨**：涉及实操维修时优先提示安全事项；涉及学术理论时保持严谨的学术态度。\n"
    "2. **依据上下文**：你的回答必须严格基于检索到的【上下文】（包括设备手册、技术文档、学术论文）。\n"
    "3. **引用溯源**：每一处关键结论、数据或观点都必须标注来源 `[文件名 (页码)]`。\n"
    "4. **图文并茂**：如果上下文中包含原理图、结构图、数据图表或故障指示图，**务必**在回答中直接引用展示。\n"
    "5. **无中生有是禁忌**：若检索到的上下文无法回答用户问题，请明确告知“当前知识库中未找到相关资料”，切勿臆造。"
)

GRADE_PROMPT = (
    "Task: Assess the relevance of a retrieved document to a user question.\n"
    "Retrieved document:\n{context}\n\nUser question: {question}\n\n"
    "Return 'yes' if relevant, otherwise 'no'."
)

ANSWER_WITH_CONTEXT = (
    "请基于提供的【海洋设备技术文档或学术文献】上下文回答用户问题。\n\n"
    "问题：\n{question}\n\n上下文：\n{context}\n\n"
    "**回答要求**：\n"
    "1. **专业视角**：使用专家口吻，针对实操问题侧重“操作/排查”，针对理论问题侧重“原理/方法/结论”。\n"
    "2. **结构清晰**：建议使用列表、加粗关键词等方式提升可读性。\n"
    "3. **必须标注来源**：引用格式为 `[文件名 (页码)]`。\n"
    "4. **图片引用**：如有相关图片，必须内联展示。"
)

ANSWER_NO_CONTEXT = (
    "当前知识库中未找到与您问题直接相关的文档或论文片段。\n"
    "问题：\n{question}"
)


# ---------------- 模型/向量函数 ----------------
def _get_llm():
    return init_chat_model(
        model=MODEL_NAME, 
        model_provider=MODEL_PROVIDER, 
        openai_api_base=SILICON_BASE_URL,
        temperature=TEMPERATURE
    )

def _get_grader():
    return init_chat_model(
        model=MODEL_NAME, 
        model_provider=MODEL_PROVIDER, 
        openai_api_base=SILICON_BASE_URL,
        temperature=0
    )

def _get_embeddings():
    """优先使用本地 BGE 模型，失败回退到 OpenAI"""
    embedding_model = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-small-zh-v1.5")
    try:
        return HuggingFaceBgeEmbeddings(
            model_name=embedding_model,
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
    except Exception as e:
        print(f"❌ 本地 Embedding 加载失败: {e}，回退到 OpenAI")
        openai_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
        return OpenAIEmbeddings(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL"),
            model=openai_model,
        )

def _load_global_vs() -> FAISS:
    """加载全局索引"""
    if not (GLOBAL_INDEX_DIR / "index.faiss").exists():
        raise FileNotFoundError(f"Global FAISS index not found at {GLOBAL_INDEX_DIR}; please run ingestion first.")
    
    # allow_dangerous_deserialization=True is needed for locally saved FAISS
    return FAISS.load_local(str(GLOBAL_INDEX_DIR), _get_embeddings(), allow_dangerous_deserialization=True)

def _score_ok(scores: List[float]) -> bool:
    if not scores:
        return False
    top1 = scores[0]
    mean3 = sum(scores[:3]) / min(3, len(scores))
    return (top1 <= SCORE_TAU_TOP1) or (mean3 <= SCORE_TAU_MEAN3)

# ---------------- 主流程：检索 + 判定 + 生成 ----------------
async def retrieve(question: str, file_id: Optional[str] = None) -> tuple[list[dict], str]:
    """
    检索函数。
    :param file_id: 若提供，则仅检索该文件；否则检索全局知识库。
    """
    try:
        vs = _load_global_vs()
    except Exception as e:
        print(f"Index load error: {e}")
        return [], ""

    # 构造过滤器
    search_kwargs = {"k": K}
    if file_id:
        # FAISS (LangChain wrapper) 支持 filter 参数
        # 假设 metadata 中包含 'file_id' 字段
        search_kwargs["filter"] = {"file_id": file_id}
        
    hits = vs.similarity_search_with_score(question, **search_kwargs)
    
    citations = []
    ctx_snippets = []
    scores = []
    
    for i, (doc, score) in enumerate(hits, start=1):
        snippet_short = (doc.page_content or "").strip()
        # 截断过长的 context 用于 prompt，但保留原本用于 citation
        if len(snippet_short) > 500:
            snippet_short = snippet_short[:500] + "..."
            
        meta = doc.metadata
        f_id = meta.get("file_id", "unknown")
        source = meta.get("source", f_id)
        page = meta.get("page", "?")
        
        # 构造 Citation 对象
        citations.append({
            "citation_id": f"{f_id}-c{i}",
            "fileId": f_id,
            "sourceName": source,
            "rank": i,
            "page": page,
            "snippet": (doc.page_content or "")[:4000],
            "score": float(score),
            "previewUrl": f"/api/v1/pdf/page?fileId={f_id}&page={page}&type=original",
        })
        
        # 构造 Context 文本 (包含元数据以便 LLM 引用)
        ctx_snippets.append(f"Document: {source} (Page {page})\nContent: {snippet_short}")
        scores.append(float(score))
        
    context_text = "\n\n".join(ctx_snippets) if ctx_snippets else ""

    # 这里我们简化逻辑：只要有检索结果且分数达标，从 Score 判断即可。
    # Phase 3 我们主要关注检索逻辑，Grader 暂时保留但作为辅助。
    ok_by_score = _score_ok(scores)
    
    # 也可以选择总是相信检索结果，交给 LLM 决定是否回答
    # 这里保持原有逻辑：如果分数太差，用 LLM judge 一下
    ok_by_llm = True
    if context_text and not ok_by_score:
        try:
            grader = _get_grader()
            grade_prompt = GRADE_PROMPT.format(context=context_text, question=question)
            decision = await grader.ainvoke([{"role": "user", "content": grade_prompt}])
            ok_by_llm = "yes" in (decision.content or "").lower()
        except:
            ok_by_llm = True # 降级：如果 Grader 失败，倾向于信任检索

    print(f"[Retrieval Debug] Query: {question}, Filter: {file_id}, Hits: {len(hits)}, ScoreOK: {ok_by_score}, LLM_OK: {ok_by_llm}")

    branch = "with_context" if (context_text and ok_by_llm) else "no_context"
    return citations, context_text if branch == "with_context" else ""

async def answer_stream(
    question: str,
    citations: list[dict],
    context_text: str,
    branch: str,
    session_id: str | None = None
) -> AsyncGenerator[dict, None]:
    
    # 1. 发送 Citations
    if branch == "with_context" and citations:
        for c in citations:
            yield {"type": "citation", "data": c}

    llm = _get_llm()
    history_msgs = get_history(session_id) if session_id else []

    if branch == "with_context" and context_text:
        user_prompt = ANSWER_WITH_CONTEXT.format(question=question, context=context_text)
    else:
        user_prompt = ANSWER_NO_CONTEXT.format(question=question)

    msgs = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
    msgs.extend(history_msgs)
    msgs.append({"role": "user", "content": user_prompt})

    final_text_parts: list[str] = []

    try:
        async for chunk in llm.astream(msgs):
            delta = getattr(chunk, "content", None)
            if delta:
                final_text_parts.append(delta)
                yield {"type": "token", "data": delta}
    except Exception as e:
        print(f"Error in stream: {e}")
        resp = await llm.ainvoke(msgs)
        text = resp.content or ""
        final_text_parts.append(text)
        yield {"type": "token", "data": text}

    # 尾部可以追加相关图片(如果 Citations 里有)，但现在的 Prompt 已经让 LLM 内联了。
    # 保留此逻辑以防 LLM 没插入
    # ... (可选)

    if session_id:
        append_history(session_id, "user", question)
        append_history(session_id, "assistant", "".join(final_text_parts))

    yield {"type": "done", "data": {"used_retrieval": branch == "with_context"}}

# ---------------- CLI 测试入口 ----------------
if __name__ == "__main__":
    async def main():
        parser = argparse.ArgumentParser(description="RAG 服务测试 (Phase 3)")
        parser.add_argument("--question", type=str, required=True, help="用户问题")
        parser.add_argument("--file_id", type=str, help="可选：指定 File ID 进行过滤")
        args = parser.parse_args()

        print(f"\n>>> 提问: {args.question}")
        if args.file_id:
            print(f">>> 过滤范围: {args.file_id}")
        else:
            print(f">>> 范围: 全局知识库")
        
        # 1. 检索
        citations, ctx_text = await retrieve(args.question, args.file_id)
        print(f">>> 检索结果: {len(citations)} 条引用")
        
        if citations:
            print("--- Top 1 Context ---")
            print(ctx_text.split('\n\n')[0][:200] + "...")
            print("---------------------")

        branch = "with_context" if ctx_text else "no_context"
        
        # 2. 生成回答
        print(">>> 正在生成回答...")
        print("-" * 50)
        async for event in answer_stream(args.question, citations, ctx_text, branch, "cli_test_session"):
            if event["type"] == "token":
                print(event["data"], end="", flush=True)
            # elif event["type"] == "citation":
            #     print(f" [Ref: {event['data']['sourceName']} p.{event['data']['page']}]")
        
        print(f"\n{'-' * 50}")
        print("\n>>> 结束")

    asyncio.run(main())
