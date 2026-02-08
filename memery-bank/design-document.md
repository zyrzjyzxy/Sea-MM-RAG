# 系统架构升级设计文档 (System Architecture Refactor Design)

**Version**: 1.0
**Status**: Implementation in Progress
**Author**: Sea-RAG Team

## 1. 项目概述 (Overview)
Sea-RAG 当前实现了单 PDF 文档的解析、索引与问答。为了支持“预存 50+ PDF 知识库”及“后续增量上传”的需求，系统需要从“单索引模式”升级为“全局统一向量库模式”。本设计文档详细阐述了从单文档处理向知识库管理系统的演进路线。

## 2. 核心改进目标
*   **全局检索**：支持跨多个 PDF 文档进行综合问答。
*   **增量更新**：实现在不重建整个库的情况下，动态添加新文档。
*   **溯源能力**：在检索结果和 AI 回答中明确标注知识来源（文件名、页码）。
*   **批量处理**：提供自动化脚本，一次性处理存量的 50+ PDF 文件。

## 3. 详细实施计划

### 第一阶段：索引服务重构 (Index Service Refactor)
*   **目标**：将 `index_service.py` 从“单文件覆盖模式”改为“全局增量模式”。
*   **关键任务**：
    1.  **统一索引路径**：定义 `data/global_index/` 作为主向量数据库存放地。
    2.  **实现 `Upsert` 逻辑**：
        *   加载现有 FAISS 索引（若不存在则初始化空库）。
        *   使用 `index.add_documents()` 拼接新向量。
        *   保存回磁盘。
    3.  **元数据增强**：在向量化切片（Chunk）时，强制注入以下 Metadata：
        *   `file_id`: 用于系统关联。
        *   `source`: 原始 PDF 文件名。
        *   `page`: 对应 PDF 页码。

### 第二阶段：批量导入机制 (Bulk Ingestion)
*   **目标**：自动处理存量的 PDF 文件。
*   **关键任务**：
    1.  **建立待处理区**：创建 `data/raw_pdf_ingestion/` 文件夹。
    2.  **开发 `ingest_all.py` 脚本**：
        *   扫描指定文件夹下的所有 `.pdf` 文件。
        *   逐个调用 `pdf_service` 进行 Markdown 解析。
        *   调用 `index_service` 将解析后的内容追加到全局索引。
        *   记录已处理文件清单，避免重复解析。

### 第三阶段：检索与 RAG 逻辑升级 (RAG Logic Enhancement)
*   **目标**：支持跨库检索与精准过滤。
*   **关键任务**：
    1.  **全局库加载**：修改 `rag_service.py`，默认检索 `data/global_index/`。
    2.  **引用机制优化**：
        *   在 `Answer` 生成过程中，将检索到的 Metadata（文件名和页码）传递给 LLM。
        *   修改 Prompt，要求 LLM 在回答中以 `[文件名 (页码)]` 的形式引用参考来源。
    3.  **多路选择能力**：
        *   API 支持传入 `file_id` 列表，实现针对特定几个文件的“限定范围搜索”。

### 第四阶段：API 与前端集成 (API & UI Integration)
*   **目标**：提供知识库管理界面。
*   **关键任务**：
    1.  **文档管理 API**：
        *   `GET /api/v1/files/list`：获取知识库内所有文件名及其状态。
        *   `DELETE /api/v1/files/{id}`：从向量库中删除指定文件的向量。
    2.  **前端展示**：
        *   在侧边栏增加“知识库列表”组件。
        *   聊天窗口增加“知识来源”标注。

## 4. 技术栈抉择方案
*   **向量数据库**：继续使用 **FAISS**。
    *   *理由*：50+ PDF 产生的向量数量在 10 万级以内，FAISS 在本地内存中处理该规模的检索效率极高（毫秒级），无需外部数据库运维成本。
*   **文本处理**：继续使用 **LangChain + PyMuPDF + Doc2X (可选)**。
*   **元数据存储**：使用本地 `data/file_registry.json` 记录所有已索引文件的元数据索引。


## 6. 业务落地执行计划 (Business Deployment Plan)
此章节规划了将通用 RAG 系统转化为“海洋设备专家系统”的具体落地步骤。

### 步骤一：构建海洋设备知识库 (Knowledge Base Construction)
*   **动作**：将准备好的 50+ 篇海洋设备领域相关的 PDF 文档放入 `data/raw_pdf_ingestion/` 目录。
*   **执行**：运行 `python ingest_all.py --strategy hi_res`。
*   **验证**：检查 `file_registry.json` 确认所有文件 status 均为 `indexed`，并抽查检索结果。

### 步骤二：提示词工程优化 (Prompt Engineering)
*   **目标**：将 `rag_service.py` 中的通用教学提示词（System Prompt）调整为海洋设备维护与操作专家的角色设定。
*   **修改点**：
    *   角色设定：从“九天老师”转变为“资深海洋设备运维专家”。
    *   回答风格：更加注重准确性、操作规范和安全警示。
    *   添加领域指令：例如“涉及设备报错时，优先检索故障排查手册”。

### 步骤三：API 接口开发与测试 (API Development)
*   **目标**：更新 `app.py`，暴露后台 RAG 能力给前端。
*   **新增接口**：
    *   `POST /api/v1/query`：核心问答接口（支持 `file_id` 过滤）。
    *   `GET /api/v1/files/list`：获取知识库列表。
    *   `GET /api/v1/pdf/page`：获取 PDF 页面预览图（已存在，需验证引用跳转）。
*   **测试**：使用 FastAPI 自带的 Swagger UI (`/docs`) 进行接口连通性测试。

### 步骤四：前端重构与集成 (Frontend Refactor & Integration)
*   **目标**：基于现有 React + Vite 前端，对接新的后端 API，实现“全局知识库管理”与“溯源问答”界面。
*   **核心功能开发**：
    1.  **知识库侧边栏 (Knowledge Base Sidebar)**：
        *   调用 `GET /api/v1/files/list` 获取文件列表。
        *   展示文件名、上传时间及索引状态。
        *   实现“点击文件”操作：
            *   在右侧预览区加载该 PDF 的第一页（调用 `/api/v1/pdf/page?page=1`）。
            *   （可选）设置 `activeFileId`，为后续聊天提供过滤上下文。
    2.  **溯源聊天组件 (Citation-Aware Chat)**：
        *   优化消息渲染：解析后端返回的 `citation` 事件。
        *   引用卡片：在回答下方展示“参考来源卡片”，展示 Document Source 和 Page。
        *   点击引用跳转：点击卡片时，在中间预览区刷新为对应 PDF 页码图片。
    3.  **上传交互优化**：
        *   支持拖拽上传 PDF，上传后自动刷新文件列表。
        *   上传后自动触发 `/pdf/parse` 并显示简单的加载状态。



### 步骤五：问答界面完善

1. **多模式问答切换 (Mode Switching)**
    - **前端实现**：
        - 在 `ChatInterface.tsx` 头部引入 `Tabs` 或 `Switch` 组件，提供“当前文档 (Selected PDF)”和“全局知识库 (Global KB)”两个选项。
        - 维护一个 `chatMode` 状态（`"single" | "global"`）。
        - 在发送请求时，若为 `"global"` 模式，则将 `pdfFileId` 参数置空，促使后端调用全局向量索引。
    - **交互优化**：
        - 在“全局知识库”模式下，侧边栏不显示选中状态，界面左上角状态标识改为“Global Mode”。
        - 在“当前文档”模式下，若未选中任何文件，自动禁用发送按钮并显示提示信息。

2. **图片预览与渲染增强 (Image Rendering)**
    - **渲染逻辑优化**：
        - 在 `MarkdownRenderer.tsx` 中自定义 `img` 组件。
        - 拦截 Markdown 中的图片路径，利用 `toAbsoluteApiUrl` 将后端返回的相对路径（如 `/api/v1/pdf/images...`）转换为完整的访问链接。
        - 实现点击图片放大预览功能（Lightbox 效果）。
    - **后端支持**：
        - 确保多模态解析（Fast 或 Hi-Res）正确提取 PDF 中的图表并保存在 `images/` 目录下。
        - RAG 检索返回的 `snippet` 中包含 `![alt](/api/v1/pdf/images?...)` 语法的占位符，由 LLM 在回答中根据需求引用。

3. **引用卡片 UI 升级**
    - 增加引用卡片的缩略图预览（若后端提供了页面的 `previewUrl`）。
    - 优化点击跳转时的视觉反馈，例如中间 PDF 面板高亮显示被引用的文本段落（后续扩展）。