import { useState } from "react";
import { Header } from "./components/Header";
import { ChatInterface } from "./components/ChatInterface";
import { PDFPanel } from "./components/PDFPanel";
import { FileSidebar } from "./components/FileSidebar";
import { Toaster } from "./components/ui/sonner";

export default function App() {
  const [chatKey, setChatKey] = useState(0);
  const [currentFileId, setCurrentFileId] = useState<string>('');
  const [currentFileName, setCurrentFileName] = useState<string>('');
  const [currentTotalPages, setCurrentTotalPages] = useState<number>(0);
  const [targetPage, setTargetPage] = useState<number>(0);

  const handleClearChat = () => {
    setChatKey((prev) => prev + 1);
  };

  const handleFileReady = (fileId: string, fileName: string, totalPages: number) => {
    setCurrentFileId(fileId);
    setCurrentFileName(fileName);
    setCurrentTotalPages(totalPages);
  };

  const handleFileSelect = (fileId: string, fileName: string, totalPages: number) => {
    setCurrentFileId(fileId);
    setCurrentFileName(fileName);
    setCurrentTotalPages(totalPages);
    setTargetPage(0); // Reset target page on file change
  };

  const handleCitationClick = (page: number, fileId?: string) => {
    // 如果引用来自其他文件，先切换文件
    if (fileId && fileId !== currentFileId) {
      setCurrentFileId(fileId);
      setCurrentFileName("Loading..."); // 临时名称，等待 onFileReady 更新
      setCurrentTotalPages(0); // 重置页数，触发 PDFPanel 重新加载逻辑
    }

    if (page > 0) {
      setTargetPage(page);
    }
  };

  return (
    <div className="dark min-h-screen bg-background text-foreground relative overflow-auto">
      {/* Enhanced background system */}
      <div className="background-system">
        {/* Floating orbs */}
        <div className="floating-elements">
          <div className="floating-orb floating-orb-1"></div>
          <div className="floating-orb floating-orb-2"></div>
          <div className="floating-orb floating-orb-3"></div>
          <div className="floating-orb floating-orb-4"></div>
        </div>

        {/* Geometric decorations */}
        <div className="geometric-decorations">
          <div className="geometric-line geometric-line-1"></div>
          <div className="geometric-line geometric-line-2"></div>
          <div className="geometric-line geometric-line-3"></div>
          <div className="geometric-polygon geometric-polygon-1"></div>
          <div className="geometric-polygon geometric-polygon-2"></div>
          <div className="geometric-circle geometric-circle-1"></div>
          <div className="geometric-circle geometric-circle-2"></div>
        </div>

        {/* Particle system */}
        <div className="particle-system">
          {Array.from({ length: 15 }).map((_, i) => (
            <div key={i} className={`particle particle-${i + 1}`}></div>
          ))}
        </div>

        {/* Light beams */}
        <div className="light-beams">
          <div className="light-beam light-beam-1"></div>
          <div className="light-beam light-beam-2"></div>
          <div className="light-beam light-beam-3"></div>
        </div>

        {/* Grid overlay */}
        <div className="grid-overlay"></div>
      </div>

      <div className="relative z-10">
        <div className="min-h-screen flex flex-col">
          {/* Header with reduced bottom margin */}
          <div className="max-w-7xl mx-auto w-full">
            <Header />
          </div>

          {/* Main Content - Three columns: Sidebar | PDF | Chat */}
          <div
            className="gap-4 px-4 pb-4"
            style={{
              display: 'grid',
              gridTemplateColumns: '260px 1fr 1fr',
              height: 'calc(100vh - 80px)'
            }}
          >

            {/* Left Column - Knowledge Base (Sidebar) */}
            <div className="flex flex-col overflow-hidden rounded-xl shadow-2xl border border-white/5 bg-black/20 backdrop-blur-xl">
              <FileSidebar
                onFileSelect={handleFileSelect}
                currentFileId={currentFileId}
              />
            </div>

            {/* Middle Column - PDF Panel */}
            <div className="flex flex-col overflow-hidden">
              <PDFPanel
                onFileReady={handleFileReady}
                activeFileId={currentFileId}
                activeFileName={currentFileName}
                activeTotalPages={currentTotalPages}
                jumptoPage={targetPage}
              />
            </div>

            {/* Right Column - Chat Interface */}
            <div className="flex flex-col overflow-hidden">
              <ChatInterface
                key={chatKey}
                onClearChat={handleClearChat}
                fileId={currentFileId}
                fileName={currentFileName}
                onCitationClick={handleCitationClick}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Toast notifications */}
      <Toaster
        position="top-right"
        expand={false}
        richColors
        closeButton
        theme="dark"
      />
    </div>
  );
}