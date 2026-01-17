import { Show, TagField } from '@refinedev/antd';
import { useShow, useCustom } from '@refinedev/core';
import { Typography, Descriptions, Card, Row, Col, Progress, Space, Button, message } from 'antd';
import { PlayCircleOutlined, StopOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';

const { Title, Paragraph } = Typography;

interface Broadcast {
  id: number;
  name: string;
  text: string;
  image_url: string | null;
  buttons: Array<Array<{ text: string; url?: string }>> | null;
  target_bots: number[] | null;
  target_languages: string[] | null;
  status: 'draft' | 'scheduled' | 'running' | 'completed' | 'cancelled';
  scheduled_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  total_recipients: number;
  sent_count: number;
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

export const BroadcastShow = () => {
  const { queryResult } = useShow<Broadcast>();
  const { data, isLoading, refetch } = queryResult;
  const record = data?.data;

  const progress = record?.total_recipients
    ? Math.round(((record.sent_count + record.failed_count) / record.total_recipients) * 100)
    : 0;

  return (
    <Show isLoading={isLoading}>
      <Row gutter={24}>
        <Col span={16}>
          <Card title="Message Preview" style={{ marginBottom: 16 }}>
            <Title level={5}>{record?.name}</Title>
            <Paragraph style={{ whiteSpace: 'pre-wrap' }}>
              {record?.text}
            </Paragraph>
            {record?.image_url && (
              <img
                src={record.image_url}
                alt="Broadcast image"
                style={{ maxWidth: '100%', maxHeight: 300 }}
              />
            )}
            {record?.buttons && record.buttons.length > 0 && (
              <Space direction="vertical" style={{ marginTop: 16 }}>
                {record.buttons.flat().map((btn, idx) => (
                  <Button key={idx} type="primary" ghost>
                    {btn.text}
                  </Button>
                ))}
              </Space>
            )}
          </Card>
        </Col>

        <Col span={8}>
          <Card title="Status" style={{ marginBottom: 16 }}>
            <Space direction="vertical" style={{ width: '100%' }}>
              <TagField
                color={statusColors[record?.status || 'draft']}
                value={record?.status?.toUpperCase()}
              />
              {record?.status === 'running' && (
                <Progress percent={progress} status="active" />
              )}
              {record?.status === 'completed' && (
                <Progress percent={100} status="success" />
              )}

              <Descriptions column={1} size="small">
                <Descriptions.Item label="Total">
                  {record?.total_recipients || 0}
                </Descriptions.Item>
                <Descriptions.Item label="Sent">
                  {record?.sent_count || 0}
                </Descriptions.Item>
                <Descriptions.Item label="Failed">
                  {record?.failed_count || 0}
                </Descriptions.Item>
              </Descriptions>

              {(record?.status === 'draft' || record?.status === 'scheduled') && (
                <Button type="primary" icon={<PlayCircleOutlined />} block>
                  Start Now
                </Button>
              )}
              {record?.status === 'running' && (
                <Button danger icon={<StopOutlined />} block>
                  Cancel
                </Button>
              )}
            </Space>
          </Card>

          <Card title="Details">
            <Descriptions column={1} size="small">
              <Descriptions.Item label="Scheduled">
                {record?.scheduled_at
                  ? dayjs(record.scheduled_at).format('YYYY-MM-DD HH:mm')
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="Started">
                {record?.started_at
                  ? dayjs(record.started_at).format('YYYY-MM-DD HH:mm')
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="Completed">
                {record?.completed_at
                  ? dayjs(record.completed_at).format('YYYY-MM-DD HH:mm')
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="Target Bots">
                {record?.target_bots?.length || 'All'}
              </Descriptions.Item>
              <Descriptions.Item label="Target Languages">
                {record?.target_languages?.join(', ') || 'All'}
              </Descriptions.Item>
              <Descriptions.Item label="Created">
                {record?.created_at
                  ? dayjs(record.created_at).format('YYYY-MM-DD HH:mm')
                  : '-'}
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
      </Row>
    </Show>
  );
};
