from fastapi import FastAPI, UploadFile, File, Query, Body, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio, time, os, random, string, json
import fitz
from typing import Optional, Dict, Any, List
from pathlib import Path

# 导入我们的 Service 模块
from services.pdf_service import (
    save_upload_file, convert_pdf_to_markdown,
    get_original_pdf_path, get_images_dir,
    get_original_pdf_path, get_images_dir,
    render_parsed_page, delete_file
)
from services.index_service import build_faiss_index, search_faiss
from services.rag_service import retrieve, answer_stream, clear_history

app = FastAPI(
    title="Sea-RAG API",
    version="0.3.0",
    description="Sea-RAG 海洋装备智能问答系统后端 API。支持多模态 PDF 解析与 RAG 检索。"
)

# 允许前端本地联调 (Cross-Origin Resource Sharing)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 开发环境中允许所有源，生产环境请配置具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"

# ---------------- 内存态存储 (Memory State) ----------------
# [Mock] 用于简单演示单个 PDF 的处理状态。
# 在生产环境或多用户场景中，应使用 Redis 或数据库持久化任务状态。
current_pdf_state: Dict[str, Any] = {
    "fileId": None,
    "name": None,
    "pages": 0,
    "status": "idle",      # idle | parsing | ready | error
    "progress": 0,
    "errorMsg": None
}

# ---------------- 工具函数 ----------------
def rid(prefix: str) -> str:
    return f"{prefix}_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))

def now_ts() -> int:
    return int(time.time())

def err(code: str, message: str) -> Dict[str, Any]:
    return {"error": {"code": code, "message": message}, "requestId": rid("req"), "ts": now_ts()}

# ---------------- Health ----------------
@app.get(f"{API_PREFIX}/health", tags=["Health"])
async def health():
    return {"ok": True, "version": "1.0.0"}

# ---------------- Chat（SSE，POST 返回 event-stream） ----------------
class ChatRequest(BaseModel):
    message: str
    sessionId: Optional[str] = None
    pdfFileId: Optional[str] = None

@app.post(f"{API_PREFIX}/chat", tags=["Chat"])
async def chat_stream(req: ChatRequest):
    """
    SSE 事件：token | citation | done | error
    """
    async def gen():
        try:
            question = (req.message or "").strip()
            session_id = (req.sessionId or "default").strip()
            file_id = (req.pdfFileId or "").strip()

            citations, context_text = [], ""
            branch = "no_context"
            
            # 尝试检索
            # 修改逻辑：默认为 Global RAG；如果传了 file_id 则为 Single Doc RAG
            # 只有当明确不需要 RAG 时（例如纯聊天模式，暂未实现）才跳过
            should_retrieve = True 
            
            if should_retrieve:
                try:
                    # retrieve 内部 logic: if file_id is None, it ignores filter (Global Search)
                    citations, context_text = await retrieve(question, file_id if file_id else None)
                    branch = "with_context" if context_text else "no_context"
                except Exception as e:
                    print(f"Retrieval error: {e}")
                    branch = "no_context"

            # 先推送引用（若有）
            if branch == "with_context" and citations:
                for c in citations:
                    # 确保 JSON 序列化
                    import json
                    c_json = json.dumps(c, ensure_ascii=False)
                    yield f"event: citation\n"
                    yield f"data: {c_json}\n\n"

            # 再推送 token 流（内部会写入历史）
            async for evt in answer_stream(
                question=question,
                citations=citations,
                context_text=context_text,
                branch=branch,
                session_id=session_id
            ):
                if evt["type"] == "token":
                    yield "event: token\n"
                    # 注意：这里确保 data 是合法 JSON 字符串
                    text = evt["data"].replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
                    yield f'data: {{"text":"{text}"}}\n\n'
                elif evt["type"] == "citation":
                    # rag_service 也会 yield citation，这里可能会重复，前端需去重或只取一处
                    # 这里选择再次发送也没关系，或者忽略
                    pass
                elif evt["type"] == "done":
                    used = "true" if evt["data"].get("used_retrieval") else "false"
                    yield "event: done\n"
                    yield f"data: {{\"used_retrieval\": {used}}}\n\n"

        except Exception as e:
            yield "event: error\n"
            esc = str(e).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
            yield f'data: {{"message":"{esc}"}}\n\n'

    headers = {"Cache-Control": "no-cache, no-transform", "Connection": "keep-alive"}
    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)

# ---------------- Chat: 清除对话 ----------------
class ClearChatRequest(BaseModel):
    sessionId: Optional[str] = None

@app.post(f"{API_PREFIX}/chat/clear", tags=["Chat"])
async def chat_clear(req: ClearChatRequest):
    sid = (req.sessionId or "default").strip()
    clear_history(sid)
    return {"ok": True, "sessionId": sid, "cleared": True}


# ---------------- PDF: 上传 ----------------
@app.post(f"{API_PREFIX}/pdf/upload", tags=["PDF"])
async def pdf_upload(file: UploadFile = File(...), replace: Optional[bool] = True):
    if not file:
        return JSONResponse(err("NO_FILE", "缺少文件"), status_code=400)
    
    # 生成新的 fileId
    fid = rid("f")
    content = await file.read()
    
    # 调用 PDF Service 保存
    saved_info = save_upload_file(fid, content, file.filename)
    
    # 更新全局状态
    current_pdf_state.update({
        "fileId": fid,
        "name": file.filename,
        "pages": saved_info["page_count"],
        "status": "idle",
        "progress": 0,
        "errorMsg": None
    })
    
    return {
        "fileId": fid,
        "name": file.filename,
        "pages": saved_info["page_count"]
    }

# ---------------- Pydantic 模型（用于文档和校验） ----------------
class ParseRequest(BaseModel):
    fileId: Optional[str] = None  # 调试时可不填，默认使用当前最新上传的文件

# ---------------- PDF: 触发解析 ----------------
@app.post(f"{API_PREFIX}/pdf/parse", tags=["PDF"])
async def pdf_parse(req: ParseRequest, bg: BackgroundTasks = None):
    # 逻辑：如果请求没传 fileId，或者传的是 Swagger 默认的 "string"，则回退
    file_id = req.fileId
    if not file_id or file_id.strip() == "" or file_id.lower() == "string":
        file_id = current_pdf_state["fileId"]
    
    if not file_id:
        return JSONResponse(err("NO_FILE_ID", "请先上传文件或提供 fileId"), status_code=400)

    # 如果传了 ID 但不匹配最新文件（仅限单一会话模式）
    if current_pdf_state["fileId"] and current_pdf_state["fileId"] != file_id:
        # 这里为了灵活也可以允许它解析，但目前逻辑只维护一个活跃状态
        pass 

    current_pdf_state["status"] = "parsing"
    current_pdf_state["progress"] = 5
    current_pdf_state["errorMsg"] = None

    def _job():
        try:
            # 阶段 1: 解析 PDF to Markdown
            current_pdf_state["progress"] = 20
            # 默认使用 fast 策略，如需 OCR 可改为 hi_res
            convert_pdf_to_markdown(file_id, strategy="fast")
            
            # 阶段 2: 构建索引
            current_pdf_state["progress"] = 60
            idx_res = build_faiss_index(file_id)
            if not idx_res.get("ok"):
                raise Exception(f"Index build failed: {idx_res.get('error')}")
            
            current_pdf_state["progress"] = 100
            current_pdf_state["status"] = "ready"
        except Exception as e:
            current_pdf_state["status"] = "error"
            current_pdf_state["progress"] = 0
            current_pdf_state["errorMsg"] = str(e)
            print(f"Parse job error: {e}")

    if bg is not None:
        bg.add_task(_job)
    else:
        _job()

    return {"jobId": rid("j"), "fileId": file_id, "status": "started"}

# ---------------- PDF: 状态查询 ----------------
@app.get(f"{API_PREFIX}/pdf/status", tags=["PDF"])
async def pdf_status(fileId: Optional[str] = Query(None)):
    target_id = fileId or current_pdf_state["fileId"]
    
    if not target_id:
        return {"status": "idle", "progress": 0, "msg": "No active file"}
        
    # 如果查询的是当前活跃文件
    if target_id == current_pdf_state["fileId"]:
        resp = {
            "fileId": target_id,
            "status": current_pdf_state["status"],
            "progress": current_pdf_state["progress"]
        }
        if current_pdf_state["errorMsg"]:
            resp["errorMsg"] = current_pdf_state["errorMsg"]
        return resp
    
    # 如果查询的是硬盘上已有的旧文件（状态不可靠，仅能判断是否存在索引）
    return {"fileId": target_id, "status": "unknown"}

# ---------------- PDF: 页面预览（原始图/解析图） ----------------
# 注意：v2版本中我们目前只支持从 original 生成的图片预览
# 这里提供一个简化版，直接返回 original 页面图片
@app.get(f"{API_PREFIX}/pdf/page", tags=["PDF"])
async def pdf_page(
    fileId: str = Query(...),
    page: int = Query(..., ge=1),
    type: str = Query("original") # original | parsed
):
    # 此处简化处理：无论是 original 还是 parsed，都返回 images 目录下的对应页图片
    # 因为我们的 pdf_service.py 中 convert_pdf_to_markdown 会生成每个页面的截图
    
    # 验证 fileId
    # if current_pdf_state["fileId"] != fileId: ... (可选校验)

    # 图片命名规则: page{page}_img1.png? 不，PyMuPDF生成的是 page-0001.png 这种格式比较好管理
    # 但 pdf_service.py 目前逻辑是提取内嵌图片...
    # 为了支持页面预览，我们需要 pdf_service.py 支持“渲染整页为图片”
    # 幸好我们有原始 PDF，可以实时渲染（或者预先渲染）
    
    if type == "parsed":
        # 调用 pdf_service 的渲染函数
        # 注意：这需要 PDF 已经通过 parse 流程生成了 segments.json
        img_bytes = render_parsed_page(fileId, page)
        if img_bytes:
            return StreamingResponse(io.BytesIO(img_bytes), media_type="image/png")
        else:
            # 如果没有解析结果（比如还没解析），暂时回退到原始图，或者返回 404
            # return JSONResponse(err("PARSED_NOT_READY", "解析结果未就绪"), status_code=404)
            pass # 继续下面逻辑，作为 fallback 显示原始图

    # 这里为了演示简单，我们实时渲染一帧（性能较低但够用）
    import fitz
    try:
        pdf_path = get_original_pdf_path(fileId)
        if not pdf_path.exists():
            return JSONResponse(err("FILE_NOT_FOUND", "PDF 文件不存在"), status_code=404)
            
        doc = fitz.open(pdf_path)
        if page > len(doc):
            return JSONResponse(err("PAGE_OUT_OF_RANGE", "页码超出范围"), status_code=404)
            
        # 渲染指定页
        pix = doc[page-1].get_pixmap(matrix=fitz.Matrix(2, 2)) # 2x 缩放清晰度
        img_bytes = pix.tobytes("png")
        
        return StreamingResponse(io.BytesIO(img_bytes), media_type="image/png")
    except Exception as e:
        return JSONResponse(err("RENDER_ERROR", str(e)), status_code=500)

import io
import re as regex_module

# ---------------- PDF: 获取某页的图片列表 ----------------
@app.get(f"{API_PREFIX}/pdf/page-images", tags=["PDF"])
async def pdf_page_images(
    fileId: str = Query(...),
    page: int = Query(..., ge=1)
):
    """获取指定文件指定页面的所有图片文件名列表"""
    img_dir = get_images_dir(fileId)
    
    if not img_dir.exists():
        return {"images": []}
    
    # 查找该页的所有图片 (格式: page{N}_img{M}.png)
    pattern = regex_module.compile(rf"^page{page}_img\d+\.(png|jpg|jpeg|gif|webp)$", regex_module.IGNORECASE)
    images = []
    
    for f in img_dir.iterdir():
        if f.is_file() and pattern.match(f.name):
            images.append(f.name)
    
    # 按图片编号排序
    images.sort(key=lambda x: int(regex_module.search(r"img(\d+)", x).group(1)) if regex_module.search(r"img(\d+)", x) else 0)
    
    return {"images": images}

# ---------------- PDF: 获取提取的图片（Markdown 中引用的） ----------------
@app.get(f"{API_PREFIX}/pdf/images", tags=["PDF"])
async def pdf_images(
    fileId: str = Query(...),
    imagePath: str = Query(...) # e.g. "page1_img1.png"
):
    img_dir = get_images_dir(fileId)
    target = img_dir / imagePath
    
    # 安全检查
    try:
        target.resolve().relative_to(img_dir.resolve())
    except:
        return JSONResponse(err("FORBIDDEN", "非法路径"), status_code=403)

    if not target.exists():
        return JSONResponse(err("NOT_FOUND", "图片不存在"), status_code=404)
        
    return FileResponse(str(target))

# ---------------- Index: 构建与搜索 ----------------
class IndexBuildRequest(BaseModel):
    fileId: str

@app.post(f"{API_PREFIX}/index/build", tags=["Index"])
async def index_build(req: IndexBuildRequest):
    res = build_faiss_index(req.fileId)
    if not res.get("ok"):
        return JSONResponse(err("INDEX_BUILD_FAIL", res.get("error", "unknown")), status_code=500)
    return res

class IndexSearchRequest(BaseModel):
    fileId: str
    query: str
    k: int = 5

@app.post(f"{API_PREFIX}/index/search", tags=["Index"])
async def index_search(req: IndexSearchRequest):
    res = search_faiss(req.fileId, req.query, req.k)
    if not res.get("ok"):
        return JSONResponse(err("INDEX_SEARCH_FAIL", res.get("error", "unknown")), status_code=500)
    return res

# ---------------- Files: 列表查询 ----------------
@app.get(f"{API_PREFIX}/files/list", tags=["Files"])
async def files_list():
    """获取知识库文件列表"""
    data_root = Path("data").resolve()
    if not data_root.exists():
        return {"files": []}
    
    files = []
    # 遍历 data 目录下的子文件夹
    for item in data_root.iterdir():
        if item.is_dir() and item.name != "global_index":
            fid = item.name
            
            # 读取 meta.json
            meta_path = item / "meta.json"
            display_name = fid
            upload_time = 0
            page_count = 0
            
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    display_name = meta.get("original_filename", fid)
                    upload_time = meta.get("upload_time", 0)
                    page_count = meta.get("page_count", 0)
                except:
                    pass
            
            # 如果没有页数或没有时间，尝试修复
            if page_count == 0 or upload_time == 0:
                try:
                    pdf_path = item / "original.pdf"
                    if pdf_path.exists():
                        # 获取文件时间作为兜底
                        file_mtime = item.stat().st_mtime
                        if upload_time == 0:
                            upload_time = file_mtime
                            
                        # 获取页数
                        if page_count == 0:
                            try:
                                with fitz.open(pdf_path) as doc:
                                    page_count = doc.page_count
                            except:
                                pass
                        
                        # 更新/创建 meta.json
                        new_meta = {
                            "id": fid,
                            "original_filename": display_name,
                            "upload_time": upload_time,
                            "page_count": page_count,
                            "size_bytes": pdf_path.stat().st_size
                        }
                        # 如果原meta存在，保留其他字段
                        if meta_path.exists():
                            try:
                                existing_meta = json.loads(meta_path.read_text(encoding="utf-8"))
                                existing_meta.update(new_meta)
                                new_meta = existing_meta
                            except:
                                pass
                                
                        meta_path.write_text(json.dumps(new_meta, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception as e:
                    print(f"Error repairing meta for {fid}: {e}")

            # 判断状态
            is_indexed = (item / "output.md").exists() # 简单判断是否解析过
            
            files.append({
                "id": fid,
                "name": display_name,
                "uploadTime": upload_time,
                "pageCount": page_count,
                "status": "ready" if is_indexed else "uploaded" # 简化状态
            })
            
    # 按时间倒序
    files.sort(key=lambda x: x["uploadTime"], reverse=True)
    return {"files": files}

# ---------------- Files: 删除文件 ----------------
@app.delete(f"{API_PREFIX}/files/{{fileId}}", tags=["Files"])
async def file_delete(fileId: str):
    """删除文件"""
    # 如果删除的是当前活跃文件，重置状态
    if current_pdf_state.get("fileId") == fileId:
        current_pdf_state.update({
            "fileId": None,
            "name": None,
            "pages": 0,
            "status": "idle",
            "progress": 0,
            "errorMsg": None
        })
        
    success = delete_file(fileId)
    if success:
        return {"ok": True, "fileId": fileId}
    else:
        return JSONResponse(err("DELETE_FAIL", "文件不存在或删除失败"), status_code=404)

# ---------------- Query: 普通问答接口 (非流式) ----------------
class QueryRequest(BaseModel):
    question: str
    fileId: Optional[str] = None

@app.post(f"{API_PREFIX}/query", tags=["Chat"])
async def query_endpoint(req: QueryRequest):
    """
    非流式问答接口，用于一次性获取结果
    """
    question = req.question.strip()
    if not question:
        return JSONResponse(err("EMPTY_QUESTION", "问题不能为空"), status_code=400)
    
    try:
        # 1. 检索
        citations, context_text = await retrieve(question, req.fileId)
        branch = "with_context" if context_text else "no_context"
        
        # 2. 生成 (聚合流式输出)
        answer_parts = []
        async for evt in answer_stream(
            question=question,
            citations=citations,
            context_text=context_text,
            branch=branch,
            session_id=None # 不记录历史，或按需记录
        ):
            if evt["type"] == "token":
                answer_parts.append(evt["data"])
        
        full_answer = "".join(answer_parts)
        
        return {
            "answer": full_answer,
            "citations": citations,
            "used_retrieval": branch == "with_context"
        }
        
    except Exception as e:
        return JSONResponse(err("QUERY_ERROR", str(e)), status_code=500)


if __name__ == "__main__":
    import uvicorn
    # 为了支持开发调试，reload=True
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)