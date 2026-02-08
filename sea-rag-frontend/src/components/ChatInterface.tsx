import { useState, useRef, useEffect, useMemo } from "react";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";
import { ScrollArea } from "./ui/scroll-area";
import { Avatar, AvatarFallback } from "./ui/avatar";
import { Send, User, Bot, Sparkles, Globe, FileText } from "lucide-react";
import { Tabs, TabsList, TabsTrigger } from "./ui/tabs";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { processChatStream, clearSession } from "../services/api";
import { toast } from "sonner";

type Reference = {
  id: number;
  text: string;
  page: number;
  citationId?: string;
  rank?: number;
  snippet?: string;
  previewUrl?: string;
  fileId?: string; // Add fileId here
};


type Message = {
  id: string;
  type: "user" | "assistant";
  content: string;
  timestamp: Date;
  references?: Reference[];
};

type ChatInterfaceProps = {
  onClearChat: () => void;
  fileId?: string;
  fileName?: string;
  threadId?: string; // 可选：传给后端存历史（默认 "default"）
  onCitationClick?: (page: number, fileId?: string) => void;
};

export function ChatInterface({
  onClearChat,
  fileId,
  fileName,
  threadId = "default",
  onCitationClick,
}: ChatInterfaceProps) {
  const initialAssistant =
    "Hello! I'm your AI assistant. You can chat directly, and if you upload a PDF I can answer with document-grounded citations.";

  const [messages, setMessages] = useState<Message[]>([
    { id: "welcome", type: "assistant", content: initialAssistant, timestamp: new Date() },
  ]);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [chatMode, setChatMode] = useState<"single" | "global">("single");

  // 当没有选文件时，自动切换到 Global 模式，或者保持 Single 但提示用户
  useEffect(() => {
    if (!fileId) {
      setChatMode("global");
    } else {
      setChatMode("single");
    }
  }, [fileId]);

  // 当前流式生成中的内容与引用
  const [currentResponse, setCurrentResponse] = useState("");
  const [currentReferences, setCurrentReferences] = useState<Reference[]>([]);

  // refs 用于避免闭包 & 在 onDone 时拿到最新值
  const currentResponseRef = useRef("");
  const currentReferencesRef = useRef<Reference[]>([]);
  const citationIdsRef = useRef<Set<string>>(new Set());

  // 终止当前 SSE 的控制器（由 processChatStream 内部使用）
  const abortRef = useRef<AbortController | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 允许发送的条件：Global模式 OR (Single模式且有文件)
  const canSend = useMemo(() => {
    if (input.trim().length === 0 || isTyping) return false;
    if (chatMode === "single" && !fileId) return false;
    return true;
  }, [input, isTyping, chatMode, fileId]);

  // 自动滚动到底
  const isAtBottomRef = useRef(true);

  const scrollToBottom = (behavior: ScrollBehavior = "smooth") => {
    messagesEndRef.current?.scrollIntoView({ behavior, block: "end" });
  };

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const target = e.target as HTMLDivElement;
    // 只有当是滚动容器本身触发时才处理 (ViewPort)
    // padding/margin 容差 50px
    const isBottom = target.scrollHeight - target.scrollTop - target.clientHeight < 50;
    isAtBottomRef.current = isBottom;
  };

  // 1. 新消息加入时，强制滚动到底部
  useEffect(() => {
    isAtBottomRef.current = true; // 发送消息后重置为锁定底部
    scrollToBottom("smooth");
  }, [messages]);

  // 2. 流式生成时，只在用户位于底部时自动滚动
  useEffect(() => {
    if (isTyping && isAtBottomRef.current) {
      scrollToBottom("auto");
    }
  }, [currentResponse, currentReferences, isTyping]);

  // 输入框自动高度
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + "px";
    }
  }, [input]);

  // 卸载时中断流
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const handleSend = async () => {
    if (!canSend) return;

    // 若有进行中的流，先中断
    abortRef.current?.abort();

    // 先落地用户消息
    const userMessage: Message = {
      id: Date.now().toString(),
      type: "user",
      content: input,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMessage]);

    // 准备流式状态
    const userText = input;
    setInput("");
    setIsTyping(true);
    setCurrentResponse("");
    setCurrentReferences([]);
    currentResponseRef.current = "";
    currentReferencesRef.current = [];
    citationIdsRef.current = new Set();

    try {
      // 开始流式
      await processChatStream(
        userText,
        // onToken
        (token: string) => {
          setCurrentResponse((prev) => prev + token);
          currentResponseRef.current += token;
        },
        // onCitation
        (c: {
          citation_id: string;
          fileId: string;
          rank: number;
          page: number;
          previewUrl: string;
          snippet?: string;
        }) => {
          // 去重：按 citation_id
          if (!c.citation_id || citationIdsRef.current.has(c.citation_id)) return;
          citationIdsRef.current.add(c.citation_id);

          const newRef: Reference = {
            id: currentReferencesRef.current.length + 1,
            text: `第 ${c.page ?? "?"} 页相关内容`,
            page: c.page ?? 0,
            citationId: c.citation_id,
            rank: c.rank,
            snippet: c.snippet,
            previewUrl: c.previewUrl,
            fileId: c.fileId, // Store fileId
          };

          // 更新 state & ref
          setCurrentReferences((prev) => [...prev, newRef]);
          currentReferencesRef.current = [...currentReferencesRef.current, newRef];
        },
        // onDone
        (meta: { used_retrieval: boolean }) => {
          const finalResponse = currentResponseRef.current;
          const finalRefs = [...currentReferencesRef.current];

          const assistantMessage: Message = {
            id: (Date.now() + 1).toString(),
            type: "assistant",
            content: finalResponse || "_（空响应）_",
            timestamp: new Date(),
            references: finalRefs.length ? finalRefs : undefined,
          };

          setMessages((prev) => [...prev, assistantMessage]);
          setIsTyping(false);
          setCurrentResponse("");
          setCurrentReferences([]);
          currentResponseRef.current = "";
          currentReferencesRef.current = [];
          citationIdsRef.current.clear();

          if (meta?.used_retrieval) {
            toast.success("Response grounded by document context");
          }
          // 重新聚焦输入框
          textareaRef.current?.focus();
        },
        // onError
        (errText: string) => {
          console.error("Chat error:", errText);
          setIsTyping(false);
          setCurrentResponse("");
          setCurrentReferences([]);
          currentResponseRef.current = "";
          currentReferencesRef.current = [];
          citationIdsRef.current.clear();

          const errorMessage: Message = {
            id: (Date.now() + 1).toString(),
            type: "assistant",
            content: `抱歉，处理你的请求时出现错误：${errText}`,
            timestamp: new Date(),
          };
          setMessages((prev) => [...prev, errorMessage]);
          toast.error("Failed to get response");
        },
        // 传递 fileId (Global 模式传空，Single 模式传 fileId)
        chatMode === "single" ? fileId : undefined,
        threadId,
      );
    } catch (e) {
      console.error("Chat request failed:", e);
      setIsTyping(false);
      setCurrentResponse("");
      setCurrentReferences([]);
      currentResponseRef.current = "";
      currentReferencesRef.current = [];
      citationIdsRef.current.clear();
      toast.error("Failed to send message");
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const clearChat = async () => {
    try {
      abortRef.current?.abort();
      await clearSession(threadId);
      setMessages([
        {
          id: "welcome",
          type: "assistant",
          content: initialAssistant,
          timestamp: new Date(),
        },
      ]);
      onClearChat();
      toast.success("Chat history cleared");
    } catch (error) {
      // API 不可达时本地清空
      if (error instanceof TypeError && String(error).includes("Failed to fetch")) {
        setMessages([
          {
            id: "welcome",
            type: "assistant",
            content: initialAssistant,
            timestamp: new Date(),
          },
        ]);
        onClearChat();
        toast.success("Chat history cleared (Local)");
        return;
      }
      console.error("Failed to clear chat:", error);
      toast.error("Failed to clear chat history");
    } finally {
      textareaRef.current?.focus();
    }
  };

  return (
    <div className="glass-panel-bright h-full flex flex-col max-h-full relative overflow-hidden">
      {/* 背景装饰 */}
      <div className="absolute inset-0 opacity-5">
        <div className="absolute inset-0 bg-gradient-to-br from-primary/20 via-transparent to-purple-500/20"></div>
      </div>

      {/* 头部 */}
      <div className="relative p-6 border-b border-border/80 flex-shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/15 border border-primary/30 shadow-lg">
              <Sparkles className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h2 className="elegant-title text-base flex items-center gap-2">
                AI Assistant
                {chatMode === "global" && <span className="text-[10px] bg-purple-500/20 text-purple-300 px-1.5 py-0.5 rounded border border-purple-500/30">Global</span>}
              </h2>
              <p className="text-xs text-muted-foreground/80 mt-1">
                {chatMode === "single"
                  ? (fileId && fileName ? `Analyzing: ${fileName}` : "Please select a document")
                  : "Searching across full knowledge base"}
              </p>
            </div>
          </div>

          <Tabs value={chatMode} onValueChange={(v) => setChatMode(v as "single" | "global")} className="h-8">
            <TabsList className="h-8 bg-black/20 border border-white/5">
              <TabsTrigger value="single" className="text-xs h-6 px-3 data-[state=active]:bg-primary/20 data-[state=active]:text-primary">
                <FileText className="w-3 h-3 mr-1.5" />
                Doc
              </TabsTrigger>
              <TabsTrigger value="global" className="text-xs h-6 px-3 data-[state=active]:bg-purple-500/20 data-[state=active]:text-purple-300">
                <Globe className="w-3 h-3 mr-1.5" />
                Global
              </TabsTrigger>
            </TabsList>
          </Tabs>

          <Button
            variant="outline"
            size="sm"
            onClick={clearChat}
            className="text-muted-foreground hover:text-white hover:bg-destructive/90 hover:border-destructive hover:shadow-lg hover:shadow-destructive/25 border border-border/60 transition-all duration-300 hover:scale-105 cursor-pointer"
          >
            Clear
          </Button>
        </div>
      </div>

      {/* 消息区 */}
      <div className="flex-1 min-h-0 overflow-hidden relative">
        <ScrollArea className="h-full" onScrollCapture={handleScroll}>
          <div className="p-6">
            <div className="space-y-4">
              {messages.map((m) => (
                <div key={m.id} className={`flex gap-4 ${m.type === "user" ? "justify-end" : "justify-start"}`}>
                  {m.type === "assistant" && (
                    <Avatar className="w-9 h-9 border-2 border-primary/30 flex-shrink-0 shadow-lg">
                      <AvatarFallback className="bg-gradient-to-br from-primary/15 to-purple-500/15">
                        <Bot className="w-5 h-5 text-primary" />
                      </AvatarFallback>
                    </Avatar>
                  )}

                  <div className={`max-w-[80%] ${m.type === "user" ? "order-first" : ""}`}>
                    <div
                      className={`p-4 rounded-2xl shadow-xl ${m.type === "user"
                        ? "bg-gradient-to-br from-primary to-primary/80 text-primary-foreground ml-auto border border-primary/30"
                        : "bg-secondary/40 border border-border/40 backdrop-blur-sm"
                        }`}
                    >
                      {m.type === "user" ? (
                        <p className="text-primary-foreground leading-relaxed text-base whitespace-pre-wrap">{m.content}</p>
                      ) : (
                        <MarkdownRenderer
                          content={m.content}
                          references={m.references}
                          onCitationClick={onCitationClick}
                          fallbackFileId={fileId}
                        />
                      )}
                    </div>
                  </div>

                  {m.type === "user" && (
                    <Avatar className="w-9 h-9 border-2 border-border/40 flex-shrink-0 shadow-lg">
                      <AvatarFallback className="bg-gradient-to-br from-muted to-muted/80">
                        <User className="w-5 h-5" />
                      </AvatarFallback>
                    </Avatar>
                  )}
                </div>
              ))}

              {/* 正在生成中的一条 */}
              {isTyping && (
                <div className="flex gap-4">
                  <Avatar className="w-9 h-9 border-2 border-primary/30 flex-shrink-0 shadow-lg">
                    <AvatarFallback className="bg-gradient-to-br from-primary/15 to-purple-500/15">
                      <Bot className="w-5 h-5 text-primary" />
                    </AvatarFallback>
                  </Avatar>
                  <div className="max-w-[80%]">
                    <div className="bg-secondary/40 border border-border/40 backdrop-blur-sm rounded-2xl p-4 shadow-xl">
                      {currentResponse ? (
                        <MarkdownRenderer
                          content={currentResponse}
                          references={currentReferences}
                          onCitationClick={onCitationClick}
                          fallbackFileId={fileId}
                        />
                      ) : (
                        <div className="flex space-x-2">
                          <div className="w-2 h-2 bg-primary/70 rounded-full animate-bounce"></div>
                          <div className="w-2 h-2 bg-primary/70 rounded-full animate-bounce" style={{ animationDelay: "0.1s" }}></div>
                          <div className="w-2 h-2 bg-primary/70 rounded-full animate-bounce" style={{ animationDelay: "0.2s" }}></div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          </div>
        </ScrollArea>
      </div>

      {/* 输入区 */}
      <div className="relative p-6 border-t border-border/60 flex-shrink-0 bg-card/40">
        <div className="flex gap-3 items-end">
          <div className="relative flex-1">
            <Textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyPress}
              placeholder={
                chatMode === "single"
                  ? (fileId ? "Ask about this document..." : "Select a document to start chat")
                  : "Ask anything across all documents..."
              }
              className="flex-1 bg-input/60 border-border/40 focus:border-primary/60 glow-ring text-foreground placeholder:text-muted-foreground/70 rounded-xl px-4 py-3 backdrop-blur-sm resize-none min-h-[52px] max-h-[120px] text-base leading-relaxed flex items-center"
              disabled={isTyping}
              rows={1}
            />
          </div>
          <Button
            onClick={handleSend}
            disabled={!canSend}
            className="bg-gradient-to-r from-primary to-primary/80 hover:from-primary/90 hover:to-primary/70 text-primary-foreground h-[52px] w-[52px] p-0 rounded-xl shadow-lg transition-all duration-200 border border-primary/30 flex-shrink-0"
          >
            <Send className="w-5 h-5" />
          </Button>
        </div>
      </div>
    </div>
  );
}
