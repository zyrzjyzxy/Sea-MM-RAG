import { useEffect, useState } from 'react';
import { listFiles, KnowledgeFile, deleteFile } from '@/services/api';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Button } from '@/components/ui/button';
import { cn } from '@/components/ui/utils';
import {
    FileText,
    Loader2,
    AlertCircle,
    Clock,
    RefreshCw,
    Search,
    Trash2
} from 'lucide-react';
import { toast } from 'sonner';

interface FileSidebarProps {
    onFileSelect: (fileId: string, fileName: string, totalPages: number) => void;
    className?: string;
    currentFileId?: string;
}

export function FileSidebar({ onFileSelect, className, currentFileId }: FileSidebarProps) {
    const [files, setFiles] = useState<KnowledgeFile[]>([]);
    const [loading, setLoading] = useState(true);

    // 刷新文件列表
    const refreshFiles = async () => {
        try {
            setLoading(true);
            const res = await listFiles();
            setFiles(res.files);
        } catch (err) {
            toast.error('Failed to load knowledge base');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        refreshFiles();
    }, []);

    const handleDelete = async (e: React.MouseEvent, fileId: string) => {
        e.stopPropagation();
        if (window.confirm('Are you sure you want to delete this file?')) {
            try {
                await deleteFile(fileId);
                toast.success('File deleted');
                refreshFiles();
                // 如果删除了当前选中的文件，可能需要通知父组件，这里简化处理暂不通知
            } catch (err) {
                toast.error('Failed to delete file');
                console.error(err);
            }
        }
    };

    return (
        <div className={cn("flex flex-col h-full overflow-hidden bg-card/50 backdrop-blur-sm border-r border-border/40", className)}>
            <div className="p-4 border-b border-border/40 flex items-center justify-between shrink-0">
                <div className="flex items-center gap-2">
                    <Search className="w-4 h-4 text-primary" />
                    <span className="font-semibold text-sm">Knowledge Base</span>
                </div>
                <Button variant="ghost" size="icon" className="h-8 w-8" onClick={refreshFiles}>
                    <RefreshCw className={cn("w-3 h-3", loading && "animate-spin")} />
                </Button>
            </div>

            <ScrollArea className="flex-1 min-h-0 p-2">
                <div className="space-y-1">
                    {loading && files.length === 0 ? (
                        <div className="flex flex-col items-center justify-center p-8 text-muted-foreground">
                            <Loader2 className="w-6 h-6 animate-spin mb-2" />
                            <span className="text-xs">Loading files...</span>
                        </div>
                    ) : files.length === 0 ? (
                        <div className="text-center p-8 text-muted-foreground text-sm">
                            No documents yet.
                            <br />
                            Upload a PDF in the Document panel.
                        </div>
                    ) : (
                        files.map((file) => (
                            <div
                                key={file.id}
                                role="button"
                                tabIndex={0}
                                onClick={() => onFileSelect(file.id, file.name, file.pageCount || 0)}
                                className={cn(
                                    "flex items-start gap-3 p-3 rounded-md transition-colors text-left group min-w-full w-max cursor-pointer outline-none focus:bg-accent/50",
                                    "hover:bg-accent/50",
                                    currentFileId === file.id ? "bg-accent text-accent-foreground" : "text-muted-foreground"
                                )}
                            >
                                <div className="mt-1 shrink-0">
                                    {file.status === 'ready' ? (
                                        <FileText className="w-4 h-4 text-emerald-500" />
                                    ) : file.status === 'error' ? (
                                        <AlertCircle className="w-4 h-4 text-destructive" />
                                    ) : (
                                        <Clock className="w-4 h-4 text-yellow-500" />
                                    )}
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="whitespace-nowrap text-sm font-medium text-foreground">
                                        {file.name}
                                    </div>
                                    <div className="flex items-center gap-2 text-xs opacity-70 mt-1 whitespace-nowrap">
                                        <span>{new Date(file.uploadTime * 1000).toLocaleDateString()}</span>
                                        {file.status !== 'ready' && (
                                            <span className="capitalize text-[10px] px-1.5 py-0.5 rounded-full bg-background border">
                                                {file.status}
                                            </span>
                                        )}
                                    </div>
                                </div>

                                <div
                                    role="button"
                                    className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive shrink-0"
                                    onClick={(e) => handleDelete(e, file.id)}
                                >
                                    <Trash2 className="w-4 h-4" />
                                </div>
                            </div>
                        ))
                    )}
                </div>
            </ScrollArea>
        </div>
    );
}
