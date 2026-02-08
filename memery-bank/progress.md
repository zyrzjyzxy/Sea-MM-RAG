# 项目开发进度与变更日志 (Project Roadmap & Changelog)

## 📌 开发路线图 (Roadmap)

### Phase 1: 基础架构搭建 (Base Infrastructure) - ✅ 已完成
- [x] **索引服务重构**: 支持向量化存储与元数据关联，统一 `data/global_index` 存储。
- [x] **后端服务**: FastAPI 基础框架搭建，集成 FAISS 向量库。
- [x] **PDF 解析**: 集成 PyMuPDF 和 Unstructured，实现基础 PDF 转 Markdown。

### Phase 2: 数据处理流水线 (Data Pipeline) - ✅ 已完成
- [x] **批量导入机制**: 开发 `ingest_all.py` 脚本，支持增量处理 PDF。
- [x] **注册表管理**: 实现 `file_registry.json` 记录文件处理状态。
- [x] **自动化测试**: 验证批量导入的稳定性与容错性。

### Phase 3: RAG 核心逻辑增强 (Advanced RAG) - ✅ 已完成
- [x] **全局检索**: 支持跨文档检索，从单点问答升级为知识库问答。
- [x] **精准过滤**: 实现基于 `file_id` 的元数据过滤。
- [x] **引用溯源**: 实现 `[文件名(页码)]` 格式的自动引用标注。

### Phase 4: 前端交互与集成 (Frontend Integration) - ✅ 已完成
- [x] **多模态展示**: 实现图片引用的缩略图展示与点击预览 (Lightbox)。
- [x] **流式响应**: 优化 SSE 通信，解决流式生成时的页面抖动问题。
- [x] **知识库管理**: 完善侧边栏文件列表，支持多选操作与状态筛选。
- [x] **用户体验**: 进一步优化移动端适配与暗色模式细节。

---

## 📝 变更日志 (Changelog)

### [Unreleased]
- 正在进行前端 UI 的细节打磨与移动端兼容性测试。

### [v0.3.0] - RAG 逻辑升级
- **Added**: 支持跨文档的全局检索能力。
- **Added**: 新增图片提取与 VLM 语义化描述 (Captioning)。
- **Fixed**: 修复了引用卡片点击后的跳转逻辑错误。

### [v0.2.0] - 批量处理能力
- **Added**: `ingest_all.py` 批量导入脚本。
- **Added**: `file_registry.json` 用于追踪文件索引状态。
- **Changed**: 优化了 PDF 解析策略，支持 `fast` 和 `hi_res` 模式切换。

### [v0.1.0] - 初始化版本
- **Added**: 基础 RAG 问答链路 (PDF -> Text -> Vector -> LLM)。
- **Added**: 简单的 React 前端界面。

---

## 🐛 已修复问题 (Resolved Issues)

### 界面交互
- **Fixed**: 三栏布局在不同屏幕尺寸下的堆叠异常问题 (通过强制 Grid 布局修复)。
- **Fixed**: 文件列表过长导致无法滚动的问题 (修复 Flex 容器层级)。
- **Fixed**: 流式生成时的自动滚动与用户手动滚动的冲突问题 (引入智能意图感知)。

### 通信与数据
- **Fixed**: 引用图片点击 404 错误 (重构引用组件，改用流式传递图片元数据)。
- **Fixed**: 后端跨域 (CORS) 配置问题。


