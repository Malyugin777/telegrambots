import { Button, message } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import { useState } from 'react';

interface ExportButtonProps {
  resource: 'users' | 'bots' | 'broadcasts' | 'logs' | 'subscriptions';
  filters?: Record<string, any>;
  label?: string;
}

export const ExportButton = ({ resource, filters = {}, label = 'CSV' }: ExportButtonProps) => {
  const [loading, setLoading] = useState(false);

  const handleExport = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      const params = new URLSearchParams();

      Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
          params.append(key, String(value));
        }
      });

      const queryString = params.toString();
      const url = `/api/v1/export/${resource}${queryString ? `?${queryString}` : ''}`;

      const response = await fetch(url, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error('Export failed');
      }

      const blob = await response.blob();
      const contentDisposition = response.headers.get('Content-Disposition');
      let filename = `${resource}_export.csv`;

      if (contentDisposition) {
        const match = contentDisposition.match(/filename=(.+)/);
        if (match) {
          filename = match[1];
        }
      }

      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(downloadUrl);

      message.success('Файл скачан');
    } catch (error) {
      message.error('Ошибка экспорта');
      console.error('Export error:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Button
      icon={<DownloadOutlined />}
      onClick={handleExport}
      loading={loading}
    >
      {label}
    </Button>
  );
};
