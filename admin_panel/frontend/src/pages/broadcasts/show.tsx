import { Show, TagField } from '@refinedev/antd';
import { useShow, useCustomMutation } from '@refinedev/core';
import { Typography, Descriptions, Card, Row, Col, Progress, Space, Button, message, Statistic } from 'antd';
import { PlayCircleOutlined, StopOutlined, ReloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useEffect } from 'react';

const { Title, Paragraph } = Typography;

interface Broadcast {
  id: number;
  name: string;
  text: string;
  image_url: string | null;
  message_video: string | null;
  buttons: Array<{ text: string; url?: string }> | null;
  target_type: string;
  target_bots: number[] | null;
  target_languages: string[] | null;
  target_user_ids: number[] | null;
  status: 'draft' | 'scheduled' | 'running' | 'completed' | 'cancelled';
  scheduled_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  total_recipients: number;
  sent_count: number;
  delivered_count: number;
  failed_count: number;
  created_at: string;
}

const statusColors: Record<string, string> = {
  draft: 'default',
  scheduled: 'blue',
  running: 'processing',
  completed: 'green',
  cancelled: 'red',
};

const statusLabels: Record<string, string> = {
  draft: 'Черновик',
  scheduled: 'Запланирована',
  running: 'Выполняется',
  completed: 'Завершена',
  cancelled: 'Отменена',
};

const targetLabels: Record<string, string> = {
  all: 'Все пользователи',
  segment: 'Сегмент',
  list: 'Список ID',
};

export const BroadcastShow = () => {
  const { queryResult } = useShow<Broadcast>();
  const { data, isLoading, refetch } = queryResult;
  const record = data?.data;

  const { mutate: startBroadcast, isLoading: isStarting } = useCustomMutation();
  const { mutate: cancelBroadcast, isLoading: isCancelling } = useCustomMutation();

  // Автообновление при running статусе
  useEffect(() => {
    if (record?.status === 'running') {
      const interval = setInterval(() => {
        refetch();
      }, 2000);
      return () => clearInterval(interval);
    }
  }, [record?.status, refetch]);

  const progress = record?.total_recipients
    ? Math.round((record.sent_count / record.total_recipients) * 100)
    : 0;

  const handleStart = () => {
    if (!record) return;
    startBroadcast(
      { url: `/broadcasts/${record.id}/start`, method: 'post', values: {} },
      {
        onSuccess: () => {
          message.success('Рассылка запущена');
          refetch();
        },
        onError: () => message.error('Ошибка запуска'),
      }
    );
  };

  const handleCancel = () => {
    if (!record) return;
    cancelBroadcast(
      { url: `/broadcasts/${record.id}/cancel`, method: 'post', values: {} },
      {
        onSuccess: () => {
          message.success('Рассылка отменена');
          refetch();
        },
        onError: () => message.error('Ошибка отмены'),
      }
    );
  };

  return (
    <Show isLoading={isLoading}>
      <Row gutter={24}>
        <Col span={16}>
          <Card title="Превью сообщения" style={{ marginBottom: 16 }}>
            <Title level={5}>{record?.name}</Title>
            <div
              style={{
                background: '#1a1a1a',
                padding: 16,
                borderRadius: 8,
                marginBottom: 16,
              }}
            >
              <Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
                <span dangerouslySetInnerHTML={{ __html: record?.text || '' }} />
              </Paragraph>
            </div>
            {record?.image_url && (
              <img
                src={record.image_url}
                alt="Broadcast image"
                style={{ maxWidth: '100%', maxHeight: 300, borderRadius: 8 }}
              />
            )}
            {record?.message_video && (
              <div style={{ marginTop: 8, color: '#888' }}>
                🎬 Видео: {record.message_video.substring(0, 50)}...
              </div>
            )}
            {record?.buttons && record.buttons.length > 0 && (
              <Space direction="vertical" style={{ marginTop: 16, width: '100%' }}>
                {record.buttons.map((btn, idx) => (
                  <Button key={idx} type="primary" ghost block>
                    {btn.text}
                  </Button>
                ))}
              </Space>
            )}
          </Card>
        </Col>

        <Col span={8}>
          <Card title="Статус" style={{ marginBottom: 16 }}>
            <Space direction="vertical" style={{ width: '100%' }} size="large">
              <div style={{ textAlign: 'center' }}>
                <TagField
                  color={statusColors[record?.status || 'draft']}
                  value={statusLabels[record?.status || 'draft']}
                  style={{ fontSize: 14, padding: '4px 12px' }}
                />
              </div>

              {(record?.status === 'running' || record?.status === 'completed') && (
                <Progress
                  percent={progress}
                  status={record?.status === 'running' ? 'active' : 'success'}
                  strokeColor={record?.failed_count > 0 ? { '0%': '#108ee9', '100%': '#ff4d4f' } : undefined}
                />
              )}

              <Row gutter={16}>
                <Col span={8}>
                  <Statistic
                    title="Всего"
                    value={record?.total_recipients || 0}
                    valueStyle={{ fontSize: 20 }}
                  />
                </Col>
                <Col span={8}>
                  <Statistic
                    title="Доставлено"
                    value={record?.delivered_count || 0}
                    valueStyle={{ fontSize: 20, color: '#52c41a' }}
                  />
                </Col>
                <Col span={8}>
                  <Statistic
                    title="Ошибок"
                    value={record?.failed_count || 0}
                    valueStyle={{ fontSize: 20, color: record?.failed_count ? '#ff4d4f' : undefined }}
                  />
                </Col>
              </Row>

              {(record?.status === 'draft' || record?.status === 'scheduled') && (
                <Button
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  block
                  size="large"
                  loading={isStarting}
                  onClick={handleStart}
                >
                  Запустить сейчас
                </Button>
              )}
              {record?.status === 'running' && (
                <>
                  <Button
                    danger
                    icon={<StopOutlined />}
                    block
                    size="large"
                    loading={isCancelling}
                    onClick={handleCancel}
                  >
                    Отменить
                  </Button>
                  <Button
                    icon={<ReloadOutlined />}
                    block
                    onClick={() => refetch()}
                  >
                    Обновить
                  </Button>
                </>
              )}
            </Space>
          </Card>

          <Card title="Детали">
            <Descriptions column={1} size="small">
              <Descriptions.Item label="Аудитория">
                {targetLabels[record?.target_type || 'all']}
                {record?.target_user_ids && ` (${record.target_user_ids.length} ID)`}
              </Descriptions.Item>
              <Descriptions.Item label="Запланирована">
                {record?.scheduled_at
                  ? dayjs(record.scheduled_at).format('DD.MM.YYYY HH:mm')
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="Запущена">
                {record?.started_at
                  ? dayjs(record.started_at).format('DD.MM.YYYY HH:mm')
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="Завершена">
                {record?.completed_at
                  ? dayjs(record.completed_at).format('DD.MM.YYYY HH:mm')
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="Боты">
                {record?.target_bots?.length ? record.target_bots.length : 'Все'}
              </Descriptions.Item>
              <Descriptions.Item label="Языки">
                {record?.target_languages?.join(', ') || 'Все'}
              </Descriptions.Item>
              <Descriptions.Item label="Создана">
                {record?.created_at
                  ? dayjs(record.created_at).format('DD.MM.YYYY HH:mm')
                  : '-'}
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
      </Row>
    </Show>
  );
};
