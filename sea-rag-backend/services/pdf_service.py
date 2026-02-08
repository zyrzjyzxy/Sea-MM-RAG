from __future__ import annotations
import os
import shutil
import io
import math
import json
import argparse
import glob
from pathlib import Path
from typing import Dict, Any, List, Optional
import fitz  # PyMuPDF
from PIL import Image
from langchain_unstructured import UnstructuredLoader
from unstructured.partition.pdf import partition_pdf
from html2text import html2text
from dotenv import load_dotenv
import matplotlib
matplotlib.use('Agg')
import matplotlib.patches as patches
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
import numpy as np
import base64
import requests
import time

# 加载环境变量 (如果需要)
load_dotenv(override=True)

# ---------------------------------------------------------------------------
# 1. 环境配置 (Poppler 路径等)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 1. 环境配置 (Poppler 路径等)
# ---------------------------------------------------------------------------

# 优先从环境变量读取，其次使用硬编码路径
POPPLER_PATH = os.getenv("POPPLER_PATH", r"V:\RAG\tools\poppler-25.12.0\Library\bin")
TESSERACT_PATH = os.getenv("TESSERACT_PATH", r"C:\Program Files\Tesseract-OCR\tesseract.exe")

def setup_environment():
    """配置运行所需的环境变量"""
    # 1. Poppler
    if os.path.exists(POPPLER_PATH):
        if POPPLER_PATH not in os.environ["PATH"]:
            os.environ["PATH"] += os.pathsep + POPPLER_PATH
            print(f"✅ Poppler 路径已临时添加: {POPPLER_PATH}")
    else:
        # 仅当默认路径也不存在时才警告，避免误报
        if not shutil.which("pdftoppm"): # 简单检查
             print(f"❌ 警告：未找到 Poppler 路径，且未在 PATH 中发现相关工具。PDF解析可能失败。")
             print(f"    当前配置路径: {POPPLER_PATH}")

    # 2. Tesseract
    # 检查是否已在 PATH 中
    if not shutil.which("tesseract"):
        # 如果 TESSERACT_PATH 指向文件，取其目录
        tess_dir = TESSERACT_PATH
        if os.path.isfile(TESSERACT_PATH):
            tess_dir = os.path.dirname(TESSERACT_PATH)
        
        if os.path.exists(tess_dir):
            if tess_dir not in os.environ["PATH"]:
                os.environ["PATH"] += os.pathsep + tess_dir
                print(f"✅ Tesseract 路径已临时添加: {tess_dir}")
        else:
             print(f"❌ 警告：未找到 Tesseract，且未在 PATH 中发现。OCR 可能无法使用。")
             print(f"    当前尝试路径: {TESSERACT_PATH}")
             print(f"    请安装 Tesseract-OCR 并添加到 PATH，或在 .env 中设置 TESSERACT_PATH")

setup_environment()

# ---------------------------------------------------------------------------
# 2. 目录管理
# ---------------------------------------------------------------------------

# 将 Path 转换为绝对路径，避免运行目录不同导致找不到文件
# 优先读取环境变量配置
DATA_ROOT = Path(os.getenv("DATA_ROOT", "data")).resolve()

def set_data_root(path: str):
    global DATA_ROOT
    DATA_ROOT = Path(path).resolve() # 强制转为绝对路径

def get_workdir(file_id: str) -> Path:
    d = DATA_ROOT / file_id
    d.mkdir(parents=True, exist_ok=True)
    return d

def get_original_pdf_path(file_id: str) -> Path:
    return get_workdir(file_id) / "original.pdf"

def find_pdf_file(file_id: str) -> Path:
    """查找目录下的 PDF 文件。优先找 original.pdf，如果没有，找第一个 .pdf 文件"""
    workdir = get_workdir(file_id)
    
    # 1. 优先检查标准命名
    original_path = workdir / "original.pdf"
    if original_path.exists():
        return original_path
        
    # 2. 否则查找任意 PDF
    pdf_files = list(workdir.glob("*.pdf"))
    if pdf_files:
        return pdf_files[0] # 返回第一个找到的 PDF
        
    # 3. 默认返回标准路径（虽然不存在，但用于报错提示）
    return original_path

def get_markdown_output_path(file_id: str) -> Path:
    return get_workdir(file_id) / "output.md"

def get_segments_path(file_id: str) -> Path:
    return get_workdir(file_id) / "segments.json"

def get_images_dir(file_id: str) -> Path:
    p = get_workdir(file_id) / "images"
    p.mkdir(parents=True, exist_ok=True)
    return p

# ---------------------------------------------------------------------------
# 3. VLM 图像理解功能
# ---------------------------------------------------------------------------

MODEL_NAME = os.getenv("VLM_MODEL_NAME", "deepseek-ai/deepseek-vl2")

def encode_image_to_base64(image_path: str) -> Optional[str]:
    """将图片文件转换为 Base64 编码"""
    if not os.path.exists(image_path):
        print(f"❌ [DEBUG] encode_image_to_base64: 找不到文件 {image_path} (PWD: {os.getcwd()})")
        return None
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def get_vlm_caption(image_path: str) -> str:
    """调用 API 解析图片，获取 Caption"""
    # 优先读取 SILICONFLOW_API_KEY，其次 SILICON_API_KEY (兼容 .env)
    api_key = os.getenv("SILICONFLOW_API_KEY") or os.getenv("SILICON_API_KEY")
    
    if not api_key:
        print("⚠️ [DEBUG] 未配置 API Key，跳过")
        return "> **AI视觉解析**：(未配置 API Key，无法解析)"

    b64_img = encode_image_to_base64(image_path)
    if not b64_img: 
        print(f"⚠️ [DEBUG] 图片转 Base64 失败: {image_path}")
        return ""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 针对运维场景优化的 Prompt (参考 notebook)
    system_prompt = "你是一个精通海洋工程与无人艇设备的运维专家。请简明扼要地解析图片。"
    user_prompt = "分析这张图片。如果是设备部件，请识别名称和状态（如腐蚀、断裂）；如果是图表，请提取关键数值；如果是电路图，请说明连接关系。请直接输出结论。"

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}},
                {"type": "text", "text": user_prompt}
            ]}
        ],
        "temperature": 0.1,
        "max_tokens": 512
    }

    # API URL
    api_url = os.getenv("VLM_API_URL", "https://api.siliconflow.cn/v1/chat/completions")
    
    max_retries = 3
    retry_delay = 2 # seconds

    for attempt in range(max_retries + 1):
        try:
            start_time = time.time()
            # 打印日志 (仅首次)
            if attempt == 0:
                print(f"    [VLM] 正在分析图片: {os.path.basename(image_path)} ...")
            else:
                print(f"    ⚠️ [VLM] 重试 ({attempt}/{max_retries}): {os.path.basename(image_path)} ...")

            response = requests.post(api_url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            content = result['choices'][0]['message']['content'].strip()
            
            duration = time.time() - start_time
            print(f"    ✅ VLM 分析完成 (耗时 {duration:.2f}s, 尝试 {attempt+1}次): {content[:30]}...")
            return content
            
        except (requests.exceptions.RequestException, requests.exceptions.HTTPError, ConnectionError) as e:
            # 如果不是最后一次尝试，则等待并重试
            if attempt < max_retries:
                wait_time = retry_delay * (2 ** attempt)
                print(f"    ⚠️ VLM 调用失败: {e}. 等待 {wait_time}秒后重试...")
                time.sleep(wait_time)
            else:
                # 最后一次尝试失败
                print(f"    ❌ VLM 最终失败: {e}")
                return f"(VLM 处理发生错误，已重试{max_retries}次: {str(e)})"
                
        except Exception as e:
            # 非网络/HTTP错误，不重试，直接返回
            print(f"    ❌ VLM 非期待错误: {e}")
            return f"(VLM 处理发生错误: {str(e)})"

# ---------------------------------------------------------------------------
# 4. 核心功能函数
# ---------------------------------------------------------------------------

def save_upload_file(file_id: str, upload_bytes: bytes, filename: str) -> Dict[str, Any]:
    """保存上传的 PDF 文件"""
    # 这里我们还是倾向于保存为 original.pdf 以保持标准化，
    # 但也可以修改为保存原文件名，只要后续 find_pdf_file 能找到即可。
    # 为了兼容性，这里暂时保持保存为 original.pdf，
    # 但你也完全可以改为: save_path = get_workdir(file_id) / filename
    
    work_dir = get_workdir(file_id)
    pdf_path = work_dir / "original.pdf"
    pdf_path.write_bytes(upload_bytes)
    
    with fitz.open(pdf_path) as doc:
        pages = doc.page_count
        
    # 保存元数据 (新增)
    meta_path = work_dir / "meta.json"
    meta_data = {
        "id": file_id,
        "original_filename": filename,
        "upload_time": time.time(),
        "size_bytes": len(upload_bytes),
        "page_count": pages
    }
    try:
        meta_path.write_text(json.dumps(meta_data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"⚠️ Warning: Failed to save meta.json: {e}")
        
    return {
        "file_id": file_id,
        "filename": filename,
        "page_count": pages,
        "local_path": str(pdf_path)
    }

def delete_file(file_id: str) -> bool:
    """删除指定文件 ID 的所有数据"""
    work_dir = get_workdir(file_id)
    if work_dir.exists():
        try:
            shutil.rmtree(work_dir)
            print(f"✅ 已删除文件目录: {work_dir}")
            return True
        except Exception as e:
            print(f"❌ 删除文件目录失败: {e}")
            return False
    return False

def convert_pdf_to_markdown(file_id: str, strategy: str = "hi_res") -> Dict[str, Any]:
    """完整流程：提取 PDF 内容并转换为 Markdown"""
    
    # 自动查找 PDF 文件
    pdf_path_obj = find_pdf_file(file_id)
    pdf_path = str(pdf_path_obj)
    
    out_md_path = get_markdown_output_path(file_id)
    img_dir = get_images_dir(file_id)
    
    print(f"[*] 正在开始处理: {file_id}")
    print(f"    PDF路径: {pdf_path}")
    print(f"    策略: {strategy}")
    
    if not pdf_path_obj.exists():
        raise FileNotFoundError(f"在目录 {pdf_path_obj.parent} 下未找到任何 PDF 文件")

    # 1. 解析元素
    partition_kwargs = {
        "filename": pdf_path,
        "strategy": strategy,
        "infer_table_structure": (strategy == "hi_res"),
    }
    
    # 根据需要启用 OCR
    if strategy == "hi_res":
        # partition_kwargs["ocr_languages"] = ["chi_sim", "eng"]
        pass

    elements = partition_pdf(**partition_kwargs)

    # 保存解析结果（Segments）到 JSON，用于后续可视化
    try:
        segments = []
        for el in elements:
            if hasattr(el, "to_dict"):
                segments.append(el.to_dict())
            else:
                # Fallback if to_dict not available
                segments.append({
                    "category": getattr(el, "category", "Uncategorized"),
                    "text": str(el),
                    "metadata": getattr(el, "metadata", {}).__dict__ if hasattr(getattr(el, "metadata", None), "__dict__") else {}
                })
        
        segments_path = get_segments_path(file_id)
        segments_path.write_text(json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[*] 解析 Segments 已保存: {segments_path}")
    except Exception as e:
        print(f"⚠️ 保存 Segments 失败: {e}")

    # 2. 提取图片并调用 VLM
    image_map = {}
    image_caption_map = {} # 存储图片描述
    with fitz.open(pdf_path) as doc:
        for page_num, page in enumerate(doc, start=1):
            image_map[page_num] = []
            for img_index, img in enumerate(page.get_images(full=True), start=1):
                xref = img[0]
                pix = fitz.Pixmap(doc, xref)
                img_name = f"page{page_num}_img{img_index}.png"
                img_path = img_dir / img_name
                
                if pix.n < 5:
                    pix.save(str(img_path))
                else:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                    pix.save(str(img_path))
                
                image_map[page_num].append(img_name)
                
                # ------ VLM 调用 ------
                # 提取后立即调用 VLM 获取描述
                caption = get_vlm_caption(str(img_path))
                if caption:
                    image_caption_map[img_name] = caption
                # ---------------------
    
    print(f"[*] 图片提取完成，保存在: {img_dir}")

    # 3. 组装 Markdown
    md_lines: List[str] = []
    inserted_images = set()
    
    def insert_page_images(p_num):
        """Helper: 插入指定页面的所有未插入图片"""
        if p_num in image_map:
            for name in image_map[p_num]:
                if (p_num, name) not in inserted_images:
                    md_lines.append(f"\n![Image](./images/{name})\n")
                    if name in image_caption_map:
                        caption_text = image_caption_map[name]
                        md_lines.append(f"> **AI视觉解析**：{caption_text}\n")
                    inserted_images.add((p_num, name))

    # --- Helper to insert page break marker ---
    def insert_page_break(p_num):
        md_lines.append(f"\n<!-- PAGE_BREAK: {p_num} -->\n")

    last_page_seen = 0
    
    for el in elements:
        category = getattr(el, "category", None)
        text = (getattr(el, "text", "") or "").strip()
        metadata = getattr(el, "metadata", None)
        page_num = getattr(metadata, "page_number", None) if metadata else None

        # --- Check for page transition to flush images of previous pages ---
        if page_num and page_num > last_page_seen:
            start_p = last_page_seen + 1 if last_page_seen > 0 else 1
            
            # 补齐上一页(及中间跳过的页)的图片，并插入对应的分页标记
            for p in range(start_p, page_num):
                insert_page_break(p)
                insert_page_images(p)
            
            # 插入当前页的分页标记
            insert_page_break(page_num)
            last_page_seen = page_num

        if not text and category != "Image":
            continue

        if category == "Title":
            md_lines.append(f"# {text}\n")
        elif category in ["Header", "Subheader"]:
            md_lines.append(f"## {text}\n")
        elif category == "Table":
            html = getattr(metadata, "text_as_html", None) if metadata else None
            if html:
                md_lines.append(html2text(html) + "\n")
            else:
                md_lines.append(text + "\n")
        elif category == "Image" and page_num:
            # 如果 unstructured 识别到了图片占位符，直接在此处插入
            insert_page_images(page_num)
        else:
            md_lines.append(text + "\n")

    # --- Final Flush: 处理最后一页或剩余页面的图片 ---
    max_p = max(image_map.keys()) if image_map else 0
    start_p = last_page_seen if last_page_seen > 0 else 1
    for p in range(start_p, max_p + 1):
        insert_page_images(p)

    # 写入文件
    print(f"[*] 正在写入 Markdown 文件: {out_md_path}")
    markdown_content = "\n".join(md_lines)
    out_md_path.write_text(markdown_content, encoding="utf-8")
    
    return {
        "markdown_path": str(out_md_path),
        "images_dir": str(img_dir),
        "content_preview": markdown_content[:500] if markdown_content else ""
    }

def render_parsed_page(file_id: str, page_number: int) -> Optional[bytes]:
    """
    渲染指定页面的解析结果（带边框），返回 PNG 图片字节流
    """
    try:
        # 1. 加载 Segments
        seg_path = get_segments_path(file_id)
        if not seg_path.exists():
            return None
            
        segments = json.loads(seg_path.read_text(encoding="utf-8"))
        
        # 筛选当前页的 segments (注意 unstructured 的 page_number 可能是1-based)
        page_segments = [
            s for s in segments 
            if s.get("metadata", {}).get("page_number") == page_number
        ]
        
        if not page_segments:
            # 该页没有识别出元素，或者页码不对？
            # 尝试 fallback：如果 segments 里没有 page_number，可能是不支持分页？
            # 但 PDF partition 通常有。如果为空，可能真的是空白页。
            pass

        # 2. 加载原始 PDF 页面作为背景
        pdf_path = find_pdf_file(file_id)
        doc = fitz.open(pdf_path)
        if page_number < 1 or page_number > len(doc):
            return None
            
        page = doc[page_number - 1]
        pix = page.get_pixmap()
        pil_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # 3. 绘图 (Matplotlib)
        # 保持图像原始比例，1px = 1 unit?
        # Matplotlib默认DPI=100. figsize=(w_inch, h_inch).
        # 为了精确对齐，我们直接用像素尺寸。
        
        width_px, height_px = pix.width, pix.height
        dpi = 100
        fig = Figure(figsize=(width_px / dpi, height_px / dpi), dpi=dpi)
        # 去除边距
        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis("off")
        
        ax.imshow(pil_image)
        
        category_to_color = {
            "Title": "orchid",
            "Image": "forestgreen", 
            "Table": "tomato",
            "Header": "orange",
            "Footer": "gray"
        }
        
        for segment in page_segments:
            # 检查是否有坐标
            if "coordinates" not in segment.get("metadata", {}):
                continue
                
            coords = segment["metadata"]["coordinates"]
            points = coords.get("points") # list of [x, y]
            layout_w = coords.get("layout_width")
            layout_h = coords.get("layout_height")
            
            if not points or not layout_w or not layout_h:
                continue
                
            # 坐标转换：Layout -> Image Pixel
            # unstructured points are usually top-left, bottom-left... polygon?
            # points is list of (x, y).
            
            scaled_points = [
                (x * width_px / layout_w, y * height_px / layout_h)
                for x, y in points
            ]
            
            category = segment.get("category", "Uncategorized")
            box_color = category_to_color.get(category, "deepskyblue")
            
            poly = patches.Polygon(
                scaled_points, 
                linewidth=2, 
                edgecolor=box_color, 
                facecolor="none"
            )
            ax.add_patch(poly)
            
            # 可选：绘制标签文字
            # x0, y0 = scaled_points[0]
            # ax.text(x0, y0, category, color=box_color, fontsize=8, backgroundcolor="white")

        # 渲染到 Buffer
        canvas = FigureCanvasAgg(fig)
        buf = io.BytesIO()
        canvas.print_png(buf)
        img_data = buf.getvalue()
        buf.close()
        doc.close()
        
        return img_data
        
    except Exception as e:
        print(f"❌ render_parsed_page 错误: {e}")
        import traceback
        traceback.print_exc()
        return None

# ---------------------------------------------------------------------------
# 4. 命令行入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # --- 测试代码 & 运行指南 ---
    # 你可以通过以下 CMD 命令运行此测试：
    # 
    # 1. 默认快速测试 (Fast 策略):
    #    python v:\RAG\sea-rag-backend\services\pdf_service.py
    # 
    # 2. 高精度测试 (Hi_res 策略，包含表格识别):
    #    python v:\RAG\sea-rag-backend\services\pdf_service.py --strategy hi_res
    # 
    # 3. 指定自定义文件 ID 和数据 root:
    #    python v:\RAG\sea-rag-backend\services\pdf_service.py --file_id my_pdf_01 --data_root ./my_data
    # 
    # 注意：确保已安装依赖：pip install requests pymupdf pillow langchain-unstructured unstructured html2text python-dotenv
    
    parser = argparse.ArgumentParser(description="PDF 转 Markdown + VLM 图像理解 测试工具")
    parser.add_argument("--strategy", type=str, default="fast", choices=["fast", "hi_res"], help="解析策略: fast(快速) 或 hi_res(高精度/带OCR)")
    parser.add_argument("--file_id", type=str, default="test_001", help="测试文件夹名称")
    parser.add_argument("--data_root", type=str, default="data", help="数据根目录")
    args = parser.parse_args()

    # 1. 配置全局变量
    set_data_root(args.data_root)
    file_id = args.file_id
    strategy = args.strategy

    print(f"\n{'='*50}")
    print(f">>> 启动 PDF + VLM 服务测试")
    print(f"    数据根目录: {DATA_ROOT}")
    print(f"    文件 ID:    {file_id}")
    print(f"    解析策略:   {strategy}")
    print(f"    VLM 模型:   {MODEL_NAME}")
    print(f"{'='*50}\n")

    # 2. 准备测试 PDF 文件
    pdf_path_obj = find_pdf_file(file_id)
    if not pdf_path_obj.exists():
        print(f"[!] 目录 {get_workdir(file_id)} 下未找到 PDF 文件")
        print("    正在自动创建包含文字和测试说明的 PDF 文件...")
        try:
            get_workdir(file_id).mkdir(parents=True, exist_ok=True)
            doc = fitz.open()
            page = doc.new_page()
            # 插入一些测试文本
            page.insert_text((50, 72), "VLM Integration Test Document", fontsize=20, color=(0, 0, 1))
            page.insert_text((50, 120), f"Current Strategy: {strategy}", fontsize=12)
            page.insert_text((50, 140), "If there are images in the PDF, they will be processed by VLM.", fontsize=12)
            
            # 提示用户手动放入带图片的 PDF 效果更好
            print("    💡 提示：若需测试图片理解，请手动将含图片的 PDF 放入上述目录并重命名为 original.pdf")
            
            save_path = get_workdir(file_id) / "original.pdf"
            doc.save(str(save_path))
            doc.close()
            print(f"    ✅ 测试 PDF 已生成: {save_path}")
        except Exception as e:
            print(f"❌ 无法创建测试 PDF: {e}")
            exit(1)
    
    # 3. 执行转换流程
    try:
        print("[*] 正在执行 convert_pdf_to_markdown (包含 VLM 调用)...")
        res = convert_pdf_to_markdown(file_id, strategy=strategy)
        
        print(f"\n{'-'*50}")
        print(f"✅ 转换流程已完成！")
        print(f"📄 Markdown 路径: {res['markdown_path']}")
        print(f"🖼️ 图片目录:     {res['images_dir']}")
        print(f"{'-'*50}")
        
        # 检查输出内容中是否包含 AI 描述
        content = res['content_preview']
        if "AI 视觉分析" in content:
            print("🎉 测试成功：在生成的 Markdown 中发现了 VLM 描述内容！")
        
        print(f"\n预览内容 (前 500 字):\n{'.' * 30}\n{content}\n{'.' * 30}")
        
    except Exception as e:
        import traceback
        print(f"\n❌ 测试过程中发生错误:")
        traceback.print_exc()
        exit(1)