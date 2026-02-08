import { useState, useRef, useEffect } from "react";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import { Progress } from "./ui/progress";
import {
  Upload,
  FileText,
  ChevronLeft,
  ChevronRight,
  AlertCircle,
  CheckCircle2,
  Loader2,
  RefreshCw,
  File
} from "lucide-react";
import { uploadPdf, startParse, getParseStatus, getPdfPageUrl } from "../services/api";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "./ui/dialog";
import * as VisuallyHidden from "./ui/visually-hidden";

type UploadStatus = 'idle' | 'uploading' | 'parsing' | 'ready' | 'error';

interface PDFPanelProps {
  className?: string;
  onFileReady?: (fileId: string, fileName: string, totalPages: number) => void;
  activeFileId?: string;
  activeFileName?: string;
  activeTotalPages?: number;
  jumptoPage?: number;
}

export function PDFPanel({ className, onFileReady, activeFileId, activeFileName, activeTotalPages, jumptoPage }: PDFPanelProps) {
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>('idle');
  const [fileName, setFileName] = useState<string>('');
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [fileId, setFileId] = useState<string>('');
  const [errorMessage, setErrorMessage] = useState<string>('');
  const [previewImage, setPreviewImage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const statusCheckInterval = useRef<NodeJS.Timeout | null>(null);

  // Sync with active file from parent
  useEffect(() => {
    if (activeFileId && activeFileId !== fileId) {
      setFileId(activeFileId);
      setFileName(activeFileName || '');
      setTotalPages(activeTotalPages || 0);
      setUploadStatus('ready');
      setCurrentPage(1);
    }
  }, [activeFileId, activeFileName, activeTotalPages]);

  // Jump to specific page if requested
  useEffect(() => {
    if (jumptoPage && jumptoPage > 0 && jumptoPage <= totalPages) {
      setCurrentPage(jumptoPage);
    }
  }, [jumptoPage, totalPages]);

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !file.type.includes('pdf')) {
      toast.error('Please select a valid PDF file');
      return;
    }

    setFileName(file.name);
    setUploadStatus('uploading');
    setUploadProgress(0);
    setErrorMessage('');

    let progressInterval: NodeJS.Timeout | undefined;

    try {
      // 模拟上传进度动画
      progressInterval = setInterval(() => {
        setUploadProgress(prev => Math.min(prev + 15, 90));
      }, 200);

      // 上传PDF
      const uploadResponse = await uploadPdf(file);
      clearInterval(progressInterval);
      setUploadProgress(100);

      setFileId(uploadResponse.fileId);
      setTotalPages(uploadResponse.pages);
      setCurrentPage(1);

      toast.success('PDF uploaded successfully');

      // 开始解析
      setUploadStatus('parsing');
      setUploadProgress(0);
      await startParse(uploadResponse.fileId);

      // 开始轮询解析状态
      startStatusPolling(uploadResponse.fileId);

    } catch (error) {
      console.error('Upload failed:', error);

      // 如果是网络错误（API不可用），提供模拟数据以展示界面功能
      if (error instanceof TypeError && error.message.includes('Failed to fetch')) {
        // 模拟成功上传和处理
        const mockFileId = `demo_${Date.now()}`;
        const mockPages = 8;

        if (progressInterval) clearInterval(progressInterval);
        setUploadProgress(100);
        setFileId(mockFileId);
        setTotalPages(mockPages);
        setCurrentPage(1);

        setTimeout(() => {
          setUploadStatus('parsing');
          setUploadProgress(0);

          // 模拟解析进度
          const parseInterval = setInterval(() => {
            setUploadProgress(prev => {
              if (prev >= 100) {
                clearInterval(parseInterval);
                setUploadStatus('ready');
                toast.success('Document processed successfully (Demo Mode)');
                onFileReady?.(mockFileId, fileName, mockPages);
                return 100;
              }
              return prev + 20;
            });
          }, 500);
        }, 1000);

        toast.success('PDF uploaded successfully (Demo Mode)');
        return;
      }

      setUploadStatus('error');
      setErrorMessage(error instanceof Error ? error.message : 'Upload failed');
      toast.error('Failed to upload PDF');
    }
  };

  const startStatusPolling = (fileId: string) => {
    if (statusCheckInterval.current) {
      clearInterval(statusCheckInterval.current);
    }

    statusCheckInterval.current = setInterval(async () => {
      try {
        const status = await getParseStatus(fileId);
        setUploadProgress(status.progress);

        if (status.status === 'ready') {
          setUploadStatus('ready');
          clearInterval(statusCheckInterval.current!);

          // 解析完成后索引已经构建好了，直接通知上层
          toast.success('Document processed and indexed successfully');
          onFileReady?.(fileId, fileName, totalPages);
        } else if (status.status === 'error') {
          setUploadStatus('error');
          setErrorMessage(status.errorMsg || 'Parsing failed');
          clearInterval(statusCheckInterval.current!);
          toast.error('Failed to process document');
        }
      } catch (error) {
        console.error('Status check failed:', error);
        setUploadStatus('error');
        setErrorMessage('Failed to check processing status');
        clearInterval(statusCheckInterval.current!);
      }
    }, 2000);
  };

  // 清理定时器
  useEffect(() => {
    return () => {
      if (statusCheckInterval.current) {
        clearInterval(statusCheckInterval.current);
      }
    };
  }, []);

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleReplace = () => {
    // 清理定时器
    if (statusCheckInterval.current) {
      clearInterval(statusCheckInterval.current);
    }

    setUploadStatus('idle');
    setFileName('');
    setCurrentPage(1);
    setTotalPages(0);
    setUploadProgress(0);
    setFileId('');
    setErrorMessage('');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const nextPage = () => {
    if (currentPage < totalPages) {
      setCurrentPage(prev => prev + 1);
    }
  };

  const prevPage = () => {
    if (currentPage > 1) {
      setCurrentPage(prev => prev - 1);
    }
  };

  const getStatusIcon = () => {
    switch (uploadStatus) {
      case 'uploading':
      case 'parsing':
        return <Loader2 className="w-4 h-4 animate-spin" />;
      case 'ready':
        return <CheckCircle2 className="w-4 h-4 text-green-500" />;
      case 'error':
        return <AlertCircle className="w-4 h-4 text-red-500" />;
      default:
        return <FileText className="w-4 h-4" />;
    }
  };

  const getStatusText = () => {
    switch (uploadStatus) {
      case 'uploading':
        return 'Uploading...';
      case 'parsing':
        return 'Parsing document...';
      case 'ready':
        return 'Ready';
      case 'error':
        return 'Error';
      default:
        return 'No document';
    }
  };

  const getStatusVariant = (): "default" | "secondary" | "destructive" | "outline" => {
    switch (uploadStatus) {
      case 'ready':
        return 'default';
      case 'error':
        return 'destructive';
      case 'uploading':
      case 'parsing':
        return 'secondary';
      default:
        return 'outline';
    }
  };

  return (
    <div className={`glass-panel-bright h-full flex flex-col relative overflow-hidden ${className}`}>
      {/* Subtle background pattern */}
      <div className="absolute inset-0 opacity-5">
        <div className="absolute inset-0 bg-gradient-to-br from-green-500/20 via-transparent to-blue-500/20"></div>
      </div>

      {/* Header */}
      <div className="relative p-5 border-b border-border/80">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-green-500/15 border border-green-500/30 shadow-lg">
              <File className="w-5 h-5 text-green-500" />
            </div>
            <div>
              <h2 className="elegant-title text-base">Document</h2>
              <p className="text-xs text-muted-foreground/80 mt-1">PDF Analysis</p>
            </div>
          </div>
          <Badge variant={getStatusVariant()} className="flex items-center gap-2 px-3 py-1 shadow-sm">
            {getStatusIcon()}
            <span className="text-xs">{getStatusText()}</span>
          </Badge>
        </div>

        {uploadStatus === 'idle' ? (
          <Button
            onClick={handleUploadClick}
            className="w-full bg-gradient-to-r from-green-500 to-green-600 hover:from-green-600 hover:to-green-700 text-white shadow-lg border border-green-500/30 rounded-xl transition-all duration-200 min-h-[48px] h-[48px] text-base font-medium cursor-pointer"
          >
            <Upload className="w-5 h-5 mr-2 flex-shrink-0" />
            <span className="flex-shrink-0">Upload PDF</span>
          </Button>
        ) : (
          <div className="flex gap-2">
            <div className="flex-1 text-sm text-muted-foreground truncate bg-secondary/40 p-3 rounded-lg border border-border/40 min-h-[48px] flex items-center">
              {fileName}
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleReplace}
              className="shrink-0 min-h-[48px] h-[48px] w-[48px] p-0 border-border/40 hover:bg-destructive/10 transition-all duration-200"
            >
              <RefreshCw className="w-4 h-4" />
            </Button>
          </div>
        )}

        {(uploadStatus === 'uploading' || uploadStatus === 'parsing') && (
          <div className="mt-4">
            <Progress value={uploadProgress} className="h-2" />
            <p className="text-xs text-muted-foreground/80 mt-2">
              {uploadStatus === 'uploading'
                ? `Uploading... ${uploadProgress}%`
                : `Processing document... ${uploadProgress}%`}
            </p>
          </div>
        )}

        {uploadStatus === 'error' && errorMessage && (
          <div className="mt-4 p-3 bg-destructive/10 border border-destructive/30 rounded-lg">
            <p className="text-xs text-destructive">{errorMessage}</p>
          </div>
        )}

        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          onChange={handleFileUpload}
          className="hidden"
        />
      </div>

      {/* Content */}
      {uploadStatus === 'ready' ? (
        <div className="flex-1 flex flex-col relative min-h-0">
          {/* Tabs - 修复超出问题 */}
          <Tabs defaultValue="original" className="flex-1 flex flex-col min-h-0">
            <div className="px-5 pt-4">
              <TabsList className="grid w-full grid-cols-2 h-10 bg-secondary/40 border border-border/40">
                <TabsTrigger value="original" className="text-xs px-2 py-2 data-[state=active]:bg-primary/15 data-[state=active]:text-primary transition-all">
                  Original
                </TabsTrigger>
                <TabsTrigger value="parsed" className="text-xs px-2 py-2 data-[state=active]:bg-primary/15 data-[state=active]:text-primary transition-all">
                  Parsed
                </TabsTrigger>
              </TabsList>
            </div>

            <TabsContent value="original" className="flex-1 flex flex-col mt-4 mx-5 mb-4 min-h-0">
              {/* PDF Viewer */}
              <div className="flex-1 bg-slate-900/40 border border-border/60 rounded-xl flex items-center justify-center shadow-inner overflow-hidden p-4 relative">
                {fileId ? (
                  <div className="w-full h-full flex items-center justify-center">
                    <img
                      src={getPdfPageUrl(fileId, currentPage, 'original')}
                      alt={`PDF Page ${currentPage}`}
                      className="max-w-full max-h-full object-contain shadow-2xl cursor-zoom-in hover:brightness-110 transition-all"
                      onClick={() => setPreviewImage(getPdfPageUrl(fileId, currentPage, 'original'))}
                      onError={(e) => {
                        const target = e.target as HTMLImageElement;
                        target.style.display = 'none';
                      }}
                    />
                  </div>
                ) : (
                  <div className="text-center space-y-3">
                    <FileText className="w-16 h-16 text-muted-foreground/60 mx-auto" />
                    <p className="text-sm text-muted-foreground">No document selected</p>
                    <p className="text-xs text-muted-foreground/80 max-w-48">
                      Select a file from the list below to view
                    </p>
                  </div>
                )}
              </div>
            </TabsContent>

            <TabsContent value="parsed" className="flex-1 flex flex-col mt-4 mx-5 mb-4 min-h-0">
              {/* Parsed Content */}
              <div className="flex-1 bg-slate-900/40 border border-border/60 rounded-xl flex items-center justify-center shadow-inner overflow-hidden p-4 relative">
                {fileId ? (
                  <div className="w-full h-full flex items-center justify-center">
                    <img
                      src={getPdfPageUrl(fileId, currentPage, 'parsed')}
                      alt={`Parsed PDF Page ${currentPage}`}
                      className="max-w-full max-h-full object-contain shadow-2xl cursor-zoom-in hover:brightness-110 transition-all"
                      onClick={() => setPreviewImage(getPdfPageUrl(fileId, currentPage, 'parsed'))}
                      onError={(e) => {
                        const target = e.target as HTMLImageElement;
                        target.style.display = 'none';
                      }}
                    />
                  </div>
                ) : (
                  <div className="text-center space-y-3">
                    <div className="w-16 h-16 bg-primary/15 rounded-full flex items-center justify-center mx-auto border border-primary/30">
                      <FileText className="w-8 h-8 text-primary" />
                    </div>
                    <p className="text-sm text-foreground">No content to display</p>
                  </div>
                )}
              </div>
            </TabsContent>
          </Tabs>

          {/* Pagination */}
          <div className="p-5 border-t border-border/60 bg-card/40">
            <div className="flex items-center justify-between">
              <Button
                variant="outline"
                size="sm"
                onClick={prevPage}
                disabled={currentPage <= 1}
                className="h-10 px-4 border-border/40 hover:bg-primary/10 transition-all"
              >
                <ChevronLeft className="w-4 h-4" />
              </Button>

              <span className="text-sm text-muted-foreground font-medium">
                Page {currentPage} of {totalPages}
              </span>

              <Button
                variant="outline"
                size="sm"
                onClick={nextPage}
                disabled={currentPage >= totalPages}
                className="h-10 px-4 border-border/40 hover:bg-primary/10 transition-all"
              >
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center p-8 relative">
          <div className="text-center space-y-6 max-w-sm">
            {uploadStatus === 'idle' ? (
              <>
                <div className="w-20 h-20 bg-gradient-to-br from-green-500/15 to-blue-500/15 rounded-full flex items-center justify-center mx-auto border border-green-500/30 shadow-lg">
                  <Upload className="w-10 h-10 text-green-500/80" />
                </div>
                <div className="space-y-2">
                  <h3 className="font-semibold text-foreground">No document uploaded</h3>
                  <p className="text-sm text-muted-foreground/80 leading-relaxed">
                    Upload a PDF document to start analyzing and asking questions about its content.
                  </p>
                </div>
              </>
            ) : uploadStatus === 'error' ? (
              <>
                <div className="w-20 h-20 bg-red-500/15 rounded-full flex items-center justify-center mx-auto border border-red-500/30 shadow-lg">
                  <AlertCircle className="w-10 h-10 text-red-500" />
                </div>
                <div className="space-y-2">
                  <h3 className="font-semibold text-foreground">Upload failed</h3>
                  <p className="text-sm text-muted-foreground/80">
                    There was an error processing your document. Please try again.
                  </p>
                </div>
              </>
            ) : (
              <>
                <div className="w-20 h-20 bg-primary/15 rounded-full flex items-center justify-center mx-auto border border-primary/30 shadow-lg">
                  <Loader2 className="w-10 h-10 text-primary animate-spin" />
                </div>
                <div className="space-y-2">
                  <h3 className="font-semibold text-foreground">Processing document</h3>
                  <p className="text-sm text-muted-foreground/80">
                    {uploadStatus === 'uploading'
                      ? 'Uploading your PDF file...'
                      : 'Analyzing and parsing the document content...'}
                  </p>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* 图片预览弹窗 */}
      <Dialog open={!!previewImage} onOpenChange={() => setPreviewImage(null)}>
        <DialogContent
          className="fixed inset-0 w-screen h-screen max-w-none max-h-none m-0 p-0 rounded-none border-none bg-black/95 shadow-none flex items-center justify-center focus:outline-none translate-x-0 translate-y-0 data-[state=open]:slide-in-from-bottom-0 sm:max-w-none"
          onClick={() => setPreviewImage(null)} // 点击任意处关闭
        >
          <VisuallyHidden.Root>
            <DialogTitle>PDF Preview</DialogTitle>
            <DialogDescription>Full size preview of the document page</DialogDescription>
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