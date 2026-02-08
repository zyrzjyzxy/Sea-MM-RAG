import { useState, useEffect } from "react";
import { Badge } from "./ui/badge";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import { checkHealth } from "../services/api";

export function HealthCheck() {
  const [status, setStatus] = useState<'checking' | 'healthy' | 'unhealthy'>('checking');

  useEffect(() => {
    const checkApiHealth = async () => {
      try {
        await checkHealth();
        setStatus('healthy');
      } catch (error) {
        // 静默处理API连接失败，不在控制台输出错误
        setStatus('unhealthy');
      }
    };

    checkApiHealth();
    
    // 每30秒检查一次
    const interval = setInterval(checkApiHealth, 30000);
    
    return () => clearInterval(interval);
  }, []);

  const getStatusIcon = () => {
    switch (status) {
      case 'checking':
        return <Loader2 className="w-3 h-3 animate-spin" />;
      case 'healthy':
        return <CheckCircle2 className="w-3 h-3 text-green-500" />;
      case 'unhealthy':
        return <AlertCircle className="w-3 h-3 text-red-500" />;
    }
  };

  const getStatusText = () => {
    switch (status) {
      case 'checking':
        return 'Checking';
      case 'healthy':
        return 'API Online';
      case 'unhealthy':
        return 'API Offline';
    }
  };

  const getStatusVariant = (): "default" | "secondary" | "destructive" | "outline" => {
    switch (status) {
      case 'healthy':
        return 'default';
      case 'unhealthy':
        return 'destructive';
      default:
        return 'secondary';
    }
  };

  return (
    <Badge variant={getStatusVariant()} className="flex items-center gap-2 px-3 py-1 shadow-sm text-xs">
      {getStatusIcon()}
      <span>{getStatusText()}</span>
    </Badge>
  );
}