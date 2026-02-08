import React, { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import rehypeSanitize from "rehype-sanitize";
import { defaultSchema } from "hast-util-sanitize"; // ⭐ 新增
import { FileText, ZoomIn } from "lucide-react";
import { Dialog, DialogContent, DialogTrigger, DialogTitle, DialogDescription } from "./ui/dialog";
import * as VisuallyHidden from "./ui/visually-hidden";

/** 可改成从 .env 读取 */
const API_BASE = "http://localhost:8000/api/v1";
const API_HOST = String(API_BASE).replace(/\/api\/v\d+$/, ""); // http://localhost:8000
// ⭐ 允许 <img> 的自定义 schema（在组件外或组件内 useMemo 都可）
const sanitizeSchema = {
  ...defaultSchema,
  tagNames: [...(defaultSchema.tagNames || []), "img"],
  attributes: {
    ...(defaultSchema.attributes || {}),
    "*": [...((defaultSchema.attributes && defaultSchema.attributes["*"]) || []), "className"],
    img: [
      "src",
      "alt",
      "title",
      "loading",
      "width",
      "height",
      "className",
    ],
    a: [
      ...((defaultSchema.attributes && defaultSchema.attributes["a"]) || []),
      "target",
      "rel",
    ],
  },
  protocols: {
    ...(defaultSchema.protocols || {}),
    src: ["http", "https", "data", "blob"],
    href: ["http", "https", "mailto", "tel"],
  },
};

/** /api/v1/... 相对路径 -> 绝对地址 */
function toAbsoluteApiUrl(src: string) {
  if (!src) return "";
  if (src.startsWith("http://") || src.startsWith("https://")) return src;
  if (src.startsWith("/api/")) return `${API_HOST}${src}`;
  return src;
}

/** 代码块（带复制） */
function Code(props: any) {
  const { inline, className, children } = props;
  const language = (className || "").replace("language-", "") || "code";
  const content = String(children).replace(/\n$/, "");

  // 判断是否应该显示为行内样式：
  // 1. 本身被识别为 inline
  // 2. 没有指定语言（默认是 code）且内容只有一行
  const isInline = inline || (language === "code" && !content.includes("\n"));

  if (isInline) {
    return (
      <code className="bg-muted/50 px-1.5 py-0.5 rounded text-sm font-mono text-primary-foreground/90 mx-0.5 border border-border/20">
        {content}
      </code>
    );
  }

  return (
    <div className="my-3 group">
      <div className="flex items-center justify-between mb-1.5 px-3 py-1.5 bg-slate-900/50 rounded-t-lg border-x border-t border-slate-700/50">
        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground/70">{language}</span>
        <button
          className="text-[10px] px-2 py-1 rounded bg-white/5 hover:bg-white/10 transition-colors opacity-0 group-hover:opacity-100"
          onClick={() => navigator.clipboard.writeText(content)}
        >
          Copy
        </button>
      </div>
      <pre className="text-sm overflow-x-auto bg-slate-900/80 p-4 rounded-b-lg border border-slate-700/50 mt-0">
        <code className="text-slate-200">{content}</code>
      </pre>
    </div>
  );
}

/** 引用卡片：展示 snippet + 页码 + 该页图片缩略图 */
function ReferenceCard({
  citationId,
  index,
  snippet,
  page,
  fileId,
  onCitationClick,
  onImageClick
}: {
  citationId: string;
  index: number;
  snippet?: string;
  page: number;
  fileId?: string;
  onCitationClick?: (page: number, fileId?: string) => void;
  onImageClick?: (url: string) => void;
}) {
  const [images, setImages] = React.useState<string[]>([]);
  const [loadedImages, setLoadedImages] = React.useState<Set<string>>(new Set());

  // 获取该页的图片列表
  React.useEffect(() => {
    if (!fileId || page <= 0) return;

    const fetchImages = async () => {
      try {
        const response = await fetch(
          `${API_BASE}/pdf/page-images?fileId=${encodeURIComponent(fileId)}&page=${page}`
        );
        if (response.ok) {
          const data = await response.json();
          setImages(data.images || []);
        }
      } catch (e) {
        console.error("[ReferenceCard] Failed to fetch page images:", e);
      }
    };

    fetchImages();
  }, [fileId, page]);

  const getImageUrl = (imageName: string) =>
    `${API_BASE}/pdf/images?fileId=${encodeURIComponent(fileId || "")}&imagePath=${encodeURIComponent(imageName)}`;

  return (
    <div
      className="bg-muted/20 rounded-lg p-3 border border-border/30 cursor-pointer hover:bg-muted/40 transition-colors"
      data-citation-id={citationId}
      onClick={() => {
        if (page > 0) {
          onCitationClick?.(page, fileId);
        }
      }}
    >
      <div className="flex items-start gap-3">
        <span className="inline-flex items-center justify-center w-6 h-6 text-xs font-medium bg-primary/20 text-primary rounded-full shrink-0">
          {index + 1}
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">
            {snippet ? (snippet.length > 200 ? snippet.slice(0, 200) + "…" : snippet) : "（无文本片段）"}
          </div>

          {/* 图片缩略图区域 */}
          {images.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {images.slice(0, 4).map((imgName) => (
                <div
                  key={imgName}
                  className="relative group cursor-zoom-in"
                  onClick={(e) => {
                    e.stopPropagation();
                    onImageClick?.(getImageUrl(imgName));
                  }}
                >
                  <img
                    src={getImageUrl(imgName)}
                    alt={`Page ${page} - ${imgName}`}
                    className={`w-16 h-16 object-cover rounded-md border border-border/40 transition-all ${loadedImages.has(imgName) ? "opacity-100" : "opacity-0"
                      } group-hover:border-primary/50 group-hover:shadow-md`}
                    loading="lazy"
                    onLoad={() => setLoadedImages((prev) => new Set(prev).add(imgName))}
                    onError={(e) => {
                      (e.target as HTMLImageElement).style.display = "none";
                    }}
                  />
                  {!loadedImages.has(imgName) && (
                    <div className="w-16 h-16 bg-muted/50 rounded-md animate-pulse" />
                  )}
                  <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/20 rounded-md">
                    <ZoomIn className="w-4 h-4 text-white drop-shadow" />
                  </div>
                </div>
              ))}
              {images.length > 4 && (
                <div className="w-16 h-16 flex items-center justify-center bg-muted/30 rounded-md border border-border/40 text-xs text-muted-foreground">
                  +{images.length - 4}
                </div>
              )}
            </div>
          )}

          <div className="mt-2 flex items-center gap-2">
            <span className="text-xs text-primary/70 bg-primary/5 px-1.5 py-0.5 rounded flex items-center gap-1">
              <FileText className="w-3 h-3" />
              第 {page} 页
            </span>
            {images.length > 0 && (
              <span className="text-xs text-muted-foreground opacity-60">
                {images.length} 张图片
              </span>
            )}
            <span className="text-xs text-muted-foreground opacity-60">点击跳转</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export type Reference = {
  id: number;
  text?: string;
  page?: number;
  citationId?: string;
  rank?: number;
  snippet?: string;
  previewUrl?: string;
  fileId?: string;
};

export function MarkdownRenderer({
  content,
  references = [],
  onCitationClick,
  fallbackFileId,
}: {
  content: string;
  references?: {
    id: number;
    text?: string;
    citationId?: string;
    rank?: number;
    snippet?: string;
    previewUrl?: string;
    page?: number;
    fileId?: string;
  }[];
  onCitationClick?: (page: number, fileId?: string) => void;
  fallbackFileId?: string;
}) {
  const [previewImage, setPreviewImage] = useState<string | null>(null);

  // 智能记忆 imageFileId (最近一次提到的文件ID)
  const imageFileId = useMemo(() => {
    if (references && references.length > 0) {
      const refWithFileId = references.find(r => r.fileId);
      if (refWithFileId?.fileId) return refWithFileId.fileId;
    }
    return fallbackFileId || "";
  }, [references, fallbackFileId]);

  // 在进入渲染前预处理内容：
  // 1. 移除 HTML img 标签
  // 2. 将相对图片路径转换为绝对 URL (避免 rehype-sanitize 过滤)
  const sanitizedContent = useMemo(() => {
    let processed = content
      .replace(/<img[\s\S]*?>/gi, ""); // 移除 HTML img 标签


    // 将 ![xxx](./images/yyy.png) 转换为绝对 URL
    if (imageFileId) {
      processed = processed.replace(
        /!\[([^\]]*)\]\(\.\/(images\/[^)]+)\)/g,
        (_match, alt, imagePath) => {
          const filename = imagePath.split("/").pop();
          const url = `${API_BASE}/pdf/images?fileId=${encodeURIComponent(imageFileId)}&imagePath=${encodeURIComponent(filename)}`;
          return `![${alt}](${url})`;
        }
      );
    }

    return processed;
  }, [content, imageFileId]);

  /** 图片：处理 API 图片及相对路径 */
  const Img = useMemo(() => {
    return function ImgComponent(props: React.ImgHTMLAttributes<HTMLImageElement>) {
      const fixedSrc = useMemo(() => {
        const src = String(props.src || "");
        if (!src) return "";

        // case 1: 绝对路径或 API 路径
        if (src.startsWith("http") || src.startsWith("/api/")) {
          return toAbsoluteApiUrl(src);
        }

        // case 2: 相对路径 (images/xx.png)
        // 尝试从 references 中找到归属的文件 ID，或者使用 fallbackFileId
        if (src.includes("images/")) {
          const filename = src.split("/").pop(); // page22_img1.png
          if (!filename) return "";

          // 从文件名中提取页码 (page22_img1.png -> 22)
          const pageMatch = filename.match(/page(\d+)/i);
          const imgPage = pageMatch ? parseInt(pageMatch[1], 10) : null;

          // 尝试从引用中找到对应的文件
          let targetFileId = fallbackFileId;

          if (references && references.length > 0) {
            // 优先：按页码匹配
            if (imgPage !== null) {
              const matchedRef = references.find(r => r.page === imgPage && r.fileId);
              if (matchedRef && matchedRef.fileId) {
                targetFileId = matchedRef.fileId;
              }
            }

            // 兜底：使用第一个有 fileId 的引用
            if (!targetFileId) {
              const anyRef = references.find(r => r.fileId);
              if (anyRef && anyRef.fileId) {
                targetFileId = anyRef.fileId;
              }
            }
          }

          if (targetFileId) {
            // 构造后端图片获取接口: /api/v1/pdf/images?fileId=xxx&imagePath=page22_img1.png
            return `${API_BASE}/pdf/images?fileId=${targetFileId}&imagePath=${filename}`;
          }
        }

        return "";
      }, [props.src, references, fallbackFileId]);

      const [err, setErr] = useState(false);

      // 如果没有有效的图片URL，显示占位符而非隐藏
      if (!fixedSrc) {
        return (
          <span className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-amber-500/20 text-amber-400 rounded border border-amber-500/30">
            🖼️ 需要选择文档以加载图片
          </span>
        );
      }

      if (err) {
        return (
          <span className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-red-500/20 text-red-400 rounded border border-red-500/30">
            ❌ 图片加载失败
          </span>
        );
      }

      // 使用 span 而非 div，避免 DOM 嵌套警告 (p > div 无效)
      // 使用 onClick 触发外部预览
      return (
        <span
          className="relative group cursor-zoom-in inline-block my-2"
          onClick={() => setPreviewImage(fixedSrc)}
        >
          <img
            {...props}
            src={fixedSrc}
            onError={() => setErr(true)}
            className={"max-w-full h-auto rounded-lg border border-border/30 shadow-sm transition-all duration-300 group-hover:shadow-md group-hover:brightness-[0.95] " + (props.className ?? "")}
            loading="lazy"
          />
          <span className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/10 rounded-lg">
            <ZoomIn className="w-8 h-8 text-white drop-shadow-md opacity-80" />
          </span>
        </span>
      );
    };
  }, [references, fallbackFileId]); // Re-create component when refs/fileId change

  return (
    <div className="space-y-3 text-foreground leading-relaxed prose prose-invert max-w-none">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw, [rehypeSanitize, sanitizeSchema]]}
        components={{
          img: Img,
          code: Code,
          table: (p) => <table {...p} className="w-full border-collapse border border-border/30 rounded-lg overflow-hidden" />,
          thead: (p) => <thead {...p} className="bg-muted/30" />,
          th: (p) => <th {...p} className="px-3 py-2 border border-border/30 text-left font-medium" />,
          td: (p) => <td {...p} className="px-3 py-2 border border-border/30 text-sm" />,
          h1: (p) => <h1 {...p} className="text-2xl font-medium mt-4 mb-3" />,
          h2: (p) => <h2 {...p} className="text-xl font-medium mt-4 mb-2" />,
          h3: (p) => <h3 {...p} className="text-lg font-medium mt-3 mb-2" />,
          ul: (p) => <ul {...p} className="list-disc pl-5 space-y-1" />,
          ol: (p) => <ol {...p} className="list-decimal pl-5 space-y-1" />,
          a: (p) => <a {...p} className="text-primary underline underline-offset-4" target="_blank" />,
          // 自定义段落：如果内部包含块级元素 (pre/div/table 等)，则渲染为 div 避免 DOM 嵌套错误
          p: ({ children, ...rest }) => {
            // 检查 children 是否包含块级元素
            const hasBlockChild = React.Children.toArray(children).some(child => {
              if (React.isValidElement(child)) {
                const type = child.type;
                // 检查是否为块级标签或我们的自定义组件
                if (typeof type === 'string') {
                  return ['div', 'pre', 'table', 'ul', 'ol', 'blockquote', 'figure'].includes(type);
                }
                // 检查是否为 Code 组件（会渲染 div+pre）
                if (type === Code) return true;
              }
              return false;
            });
            return hasBlockChild
              ? <div {...rest} className="my-2">{children}</div>
              : <p {...rest} className="my-2">{children}</p>;
          },
        }}
      >
        {sanitizedContent}
      </ReactMarkdown>

      {/* 相关文档片段（只展示 snippet + 查看原页），不再渲整页大图 */}
      {references?.length > 0 && (
        <div className="mt-4 pt-4 border-t border-border/30">
          <div className="flex items-center gap-2 mb-2">
            <FileText className="w-4 h-4 text-primary" />
            <span className="text-sm font-medium">相关文档片段</span>
            <span className="text-xs text-muted-foreground">({references.length})</span>
          </div>
          <div className="space-y-2">
            {references
              .filter((r) => !!r.citationId)
              .map((r, i) => (
                <ReferenceCard
                  key={r.citationId!}
                  citationId={r.citationId!}
                  index={i}
                  snippet={r.snippet}
                  page={r.page || 0}
                  fileId={r.fileId}
                  onCitationClick={onCitationClick}
                  onImageClick={setPreviewImage}
                />
              ))}
          </div>
        </div>
      )}

      {/* 全局图片预览弹窗 */}
      <Dialog open={!!previewImage} onOpenChange={() => setPreviewImage(null)}>
        <DialogContent
          className="fixed inset-0 w-screen h-screen max-w-none max-h-none m-0 p-0 rounded-none border-none bg-black/95 shadow-none flex items-center justify-center focus:outline-none translate-x-0 translate-y-0 data-[state=open]:slide-in-from-bottom-0 sm:max-w-none"
          onClick={() => setPreviewImage(null)}
        >
          <VisuallyHidden.Root>
            <DialogTitle>Image Preview</DialogTitle>
            <DialogDescription>Full size preview of the image</DialogDescription>
          </VisuallyHidden.Root>
          {previewImage && (
            <img
              src={previewImage}
              alt="Preview"
              className="w-auto h-auto max-w-full max-h-full object-contain"
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
