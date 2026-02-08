# Sea-RAG 技术架构文档 (Technical Architecture)

> **项目定位**：基于多模态大模型（VLM）与 RAG 技术的垂直领域智能问答系统，旨在解决海洋工程设备运维场景下的复杂文档检索与多模态内容理解问题。

## 1. 技术栈概览 (Technology Stack)

### 后端 (Backend)
-   **核心框架**: `FastAPI` (Python/AsyncIO) - 高并发异步 API 服务
-   **PDF 处理流水线**:
    -   `PyMuPDF (Fitz)`: 高速 PDF 渲染与元数据提取
    -   `Unstructured`: 文档版面分析与切片 (Chunking)
    -   `Matplotlib (Agg)`: 后端动态生成 PDF 解析可视化视图
-   **RAG & AI 引擎**:
    -   **向量数据库**: `FAISS` - 本地高性能向量索引库
    -   **编排框架**: `LangChain` - 检索流程编排
    -   **多模态模型**: `SiliconFlow API (DeepSeek-VL2)` - 用于图表/设备图的语义分析
    -   **Embedding**: `BGE-M3` / `OpenAI` - 文本向量化

### 前端 (Frontend)
-   **核心框架**: `React 18` + `TypeScript` + `Vite`
-   **UI 系统**: `TailwindCSS` + `Shadcn/UI` (@radix-ui) - 现代化响应式组件库
-   **交互实现**:
    -   `EventSource (SSE)`: 实现打字机流式响应与实时引用推送
    -   `React-Markdown / Rehype`: Markdown 渲染与安全过滤
    -   `Sonner`: 状态通知管理

## 2. 核心特性与实现机制 (Key Features)

### 🌟 多模态文档解析 (Multimodal RAG)
-   **挑战**: 传统 RAG 仅能检索文本，无法理解工程文档中大量的设备构造图、电路图和状态统计表。
-   **解决方案**: "Text-Image Dual Pathway" 解析流。
    -   **图像处理**: 自动提取 PDF 内嵌图片，调用 **Visual Language Model (VLM)** 生成语义化 Caption（例如："图示为柴油机燃油喷射泵结构，包含柱塞与出油阀..."），并将其向量化存入索引。
    -   **可视化验证**: 后端集成 Matplotlib，自动绘制 PDF 版面分析框（Parsed View），提供解析结果的可视化验证。

### 🌟 流式引文溯源 (Streaming Citations)
-   **挑战**: 大模型生成内容容易产生幻觉，专业领域需要严格的原文依据。
-   **解决方案**: 自研 SSE 通信协议。
    -   并行推送 `citation` (JSON 对象) 和 `token` (增量文本) 事件。
    -   前端实时渲染引用锚点，支持 **毫秒级** 点击跳转到 PDF 原文对应页面的高亮区域。

### 🌟 混合版面分析策略
-   **策略**: 针对不同文档类型支持 `fast` (基于规则) 和 `hi_res` (基于 OCR/VLM) 两种解析策略。
-   **数据管理**: 自定义 `ingest_all.py` 批处理脚本，支持增量构建索引与元数据管理 (`file_registry.json`)，确保持久化存储的一致性。

