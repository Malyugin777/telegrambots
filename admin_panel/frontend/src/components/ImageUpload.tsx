import { useState, useEffect } from 'react';
import { Upload, message, Button, Space, Image } from 'antd';
import { InboxOutlined, DeleteOutlined, LinkOutlined } from '@ant-design/icons';
import type { UploadProps, RcFile } from 'antd/es/upload';

const { Dragger } = Upload;

interface ImageUploadProps {
  value?: string;
  onChange?: (url: string | undefined) => void;
}

const API_URL = import.meta.env.VITE_API_URL || '/api/v1';

export const ImageUpload: React.FC<ImageUploadProps> = ({ value, onChange }) => {
  const [imageUrl, setImageUrl] = useState<string | undefined>(value);
  const [uploading, setUploading] = useState(false);
  const [mode, setMode] = useState<'upload' | 'url'>(value && value.startsWith('http') ? 'url' : 'upload');
  const [urlInput, setUrlInput] = useState(value || '');

  useEffect(() => {
    setImageUrl(value);
    if (value) {
      setUrlInput(value);
    }
  }, [value]);

  const getAuthToken = () => {
    return localStorage.getItem('access_token') || '';
  };

  const handleUpload = async (file: RcFile) => {
    // Validate file type
    const isImage = file.type.startsWith('image/');
    if (!isImage) {
      message.error('Можно загружать только изображения');
      return false;
    }

    // Validate file size (10MB)
    const isLt10M = file.size / 1024 / 1024 < 10;
    if (!isLt10M) {
      message.error('Изображение должно быть меньше 10MB');
      return false;
    }

    setUploading(true);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`${API_URL}/uploads/image`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${getAuthToken()}`,
        },
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Upload failed');
      }

      const data = await response.json();
      setImageUrl(data.url);
      setUrlInput(data.url);
      onChange?.(data.url);
      message.success('Изображение загружено');
    } catch (error) {
      message.error(`Ошибка загрузки: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setUploading(false);
    }

    return false; // Prevent default upload behavior
  };

  const handleDelete = async () => {
    if (imageUrl && imageUrl.includes('/uploads/broadcasts/')) {
      const filename = imageUrl.split('/').pop();
      if (filename) {
        try {
          await fetch(`${API_URL}/uploads/image/${filename}`, {
            method: 'DELETE',
            headers: {
              'Authorization': `Bearer ${getAuthToken()}`,
            },
          });
        } catch {
          // Ignore delete errors
        }
      }
    }

    setImageUrl(undefined);
    setUrlInput('');
    onChange?.(undefined);
    message.success('Изображение удалено');
  };

  const handleUrlChange = (url: string) => {
    setUrlInput(url);
    if (url && (url.startsWith('http://') || url.startsWith('https://'))) {
      setImageUrl(url);
      onChange?.(url);
    } else if (!url) {
      setImageUrl(undefined);
      onChange?.(undefined);
    }
  };

  const uploadProps: UploadProps = {
    name: 'file',
    multiple: false,
    accept: 'image/*',
    showUploadList: false,
    beforeUpload: handleUpload,
  };

  return (
    <div>
      <Space style={{ marginBottom: 8 }}>
        <Button
          type={mode === 'upload' ? 'primary' : 'default'}
          size="small"
          icon={<InboxOutlined />}
          onClick={() => setMode('upload')}
        >
          Загрузить
        </Button>
        <Button
          type={mode === 'url' ? 'primary' : 'default'}
          size="small"
          icon={<LinkOutlined />}
          onClick={() => setMode('url')}
        >
          URL
        </Button>
      </Space>

      {mode === 'upload' ? (
        imageUrl ? (
          <div style={{ position: 'relative' }}>
            <Image
              src={imageUrl}
              alt="Preview"
              style={{ maxWidth: '100%', maxHeight: 200, objectFit: 'contain' }}
              fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAMIAAADDCAYAAADQvc6UAAABRWlDQ1BJQ0MgUHJvZmlsZQAAKJFjYGASSSwoyGFhYGDIzSspCnJ3UoiIjFJgf8LAwSDCIMogwMCcmFxc4BgQ4ANUwgCjUcG3awyMIPqyLsis7PPOq3QdDFcvjV3jOD1boQVTPQrgSkktTgbSf4A4LbmgqISBgTEFyFYuLykAsTuAbJEioKOA7DkgdjqEvQHEToKwj4DVhAQ5A9k3gGyB5IxEoBmML4BsnSQk8XQkNtReEOBxcfXxUQg1Mjc0dyHgXNJBSWpFCYh2zi+oLMpMzyhRcASGUqqCZ16yno6CkYGRAQMDKMwhqj/fAIcloxgHQqxAjIHBEugw5sUIsSQpBobtQPdLciLEVJYzMPBHMDBsayhILEqEO4DxG0txmrERhM29nYGBddr//5/DGRjYNRkY/l7////39v///y4Dmn+LgesAxxPJz4AAAABnSURBVHgB7cEBAQAAAIIg/69uSEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGBpY2UAATxFgWIAAAAASUVORK5CYII="
            />
            <Button
              danger
              size="small"
              icon={<DeleteOutlined />}
              onClick={handleDelete}
              style={{ position: 'absolute', top: 8, right: 8 }}
            >
              Удалить
            </Button>
          </div>
        ) : (
          <Dragger {...uploadProps} disabled={uploading}>
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">
              {uploading ? 'Загрузка...' : 'Нажмите или перетащите файл'}
            </p>
            <p className="ant-upload-hint">
              JPG, PNG, GIF, WebP до 10MB
            </p>
          </Dragger>
        )
      ) : (
        <div>
          <input
            type="text"
            value={urlInput}
            onChange={(e) => handleUrlChange(e.target.value)}
            placeholder="https://example.com/image.jpg"
            style={{
              width: '100%',
              padding: '8px 12px',
              border: '1px solid #434343',
              borderRadius: 6,
              background: '#1f1f1f',
              color: '#fff',
            }}
          />
          {imageUrl && (
            <div style={{ marginTop: 8 }}>
              <Image
                src={imageUrl}
                alt="Preview"
                style={{ maxWidth: '100%', maxHeight: 200, objectFit: 'contain' }}
                fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAMIAAADDCAYAAADQvc6UAAABRWlDQ1BJQ0MgUHJvZmlsZQAAKJFjYGASSSwoyGFhYGDIzSspCnJ3UoiIjFJgf8LAwSDCIMogwMCcmFxc4BgQ4ANUwgCjUcG3awyMIPqyLsis7PPOq3QdDFcvjV3jOD1boQVTPQrgSkktTgbSf4A4LbmgqISBgTEFyFYuLykAsTuAbJEioKOA7DkgdjqEvQHEToKwj4DVhAQ5A9k3gGyB5IxEoBmML4BsnSQk8XQkNtReEOBxcfXxUQg1Mjc0dyHgXNJBSWpFCYh2zi+oLMpMzyhRcASGUqqCZ16yno6CkYGRAQMDKMwhqj/fAIcloxgHQqxAjIHBEugw5sUIsSQpBobtQPdLciLEVJYzMPBHMDBsayhILEqEO4DxG0txmrERhM29nYGBddr//5/DGRjYNRkY/l7////39v///y4Dmn+LgeHAcxPJz4AAAABnSURBVHgB7cEBAQAAAIIg/69uSEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGBpY2UAATxFgWIAAAAASUVORK5CYII="
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
};
