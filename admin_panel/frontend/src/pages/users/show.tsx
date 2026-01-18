import { Show, TagField } from '@refinedev/antd';
import { useShow, useCustom } from '@refinedev/core';
import { Typography, Descriptions, Card, Space, Button, Select, Input, message, Modal, Table, Row, Col, Statistic, Timeline } from 'antd';
import { StopOutlined, CheckOutlined, DownloadOutlined, ClockCircleOutlined } from '@ant-design/icons';
import { useState, useEffect } from 'react';
import dayjs from 'dayjs';
import axios from 'axios';

const { Title } = Typography;

interface User {
  id: number;
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  language_code: string | null;
  role: 'user' | 'moderator' | 'admin' | 'owner';
  is_banned: boolean;
  ban_reason: string | null;
  created_at: string;
  updated_at: string;
  last_active_at: string | null;
}

const roleColors: Record<string, string> = {
  user: 'default',
  moderator: 'blue',
  admin: 'purple',
  owner: 'gold',
};

interface UserStats {
  total_downloads: number;
  platforms: Array<{ name: string; count: number }>;
  recent_activity: Array<{
    id: number;
    action: string;
    details: Record<string, unknown> | null;
    created_at: string;
  }>;
}

const platformColors: Record<string, string> = {
  instagram: '#E1306C',
  tiktok: '#00f2ea',
  youtube: '#FF0000',
  pinterest: '#E60023',
};

const actionLabels: Record<string, string> = {
  download_request: 'Запрос скачивания',
  download_success: 'Успешное скачивание',
  audio_extracted: 'Извлечение аудио',
  start: 'Запуск бота',
  help: 'Справка',
  error: 'Ошибка',
};

export const UserShow = () => {
  const { queryResult } = useShow<User>();
  const { data, isLoading, refetch } = queryResult;
  const record = data?.data;

  const [banModalVisible, setBanModalVisible] = useState(false);
  const [banReason, setBanReason] = useState('');
  const [selectedRole, setSelectedRole] = useState<string | undefined>();
  const [userStats, setUserStats] = useState<UserStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  useEffect(() => {
    if (record?.id) {
      fetchUserStats(record.id);
    }
  }, [record?.id]);

  const fetchUserStats = async (userId: number) => {
    setStatsLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      const response = await axios.get(`/api/v1/users/${userId}/stats`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setUserStats(response.data);
    } catch {
      // Stats loading failed, ignore
    } finally {
      setStatsLoading(false);
    }
  };

  const handleBan = async () => {
    try {
      const token = localStorage.getItem('access_token');
      await axios.patch(
        `/api/v1/users/${record?.id}/ban`,
        { is_banned: true, ban_reason: banReason },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      message.success('User banned');
      setBanModalVisible(false);
      setBanReason('');
      refetch();
    } catch {
      message.error('Failed to ban user');
    }
  };

  const handleUnban = async () => {
    try {
      const token = localStorage.getItem('access_token');
      await axios.patch(
        `/api/v1/users/${record?.id}/ban`,
        { is_banned: false },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      message.success('User unbanned');
      refetch();
    } catch {
      message.error('Failed to unban user');
    }
  };

  const handleRoleChange = async (role: string) => {
    try {
      const token = localStorage.getItem('access_token');
      await axios.patch(
        `/api/v1/users/${record?.id}/role`,
        { role },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      message.success('Role updated');
      refetch();
    } catch {
      message.error('Failed to update role');
    }
  };

  return (
    <Show isLoading={isLoading}>
      <Title level={5}>User Details</Title>

      <Descriptions bordered column={2}>
        <Descriptions.Item label="ID">{record?.id}</Descriptions.Item>
        <Descriptions.Item label="Telegram ID">
          <code>{record?.telegram_id}</code>
        </Descriptions.Item>
        <Descriptions.Item label="Username">
          {record?.username ? `@${record.username}` : '-'}
        </Descriptions.Item>
        <Descriptions.Item label="Name">
          {[record?.first_name, record?.last_name].filter(Boolean).join(' ') || '-'}
        </Descriptions.Item>
        <Descriptions.Item label="Language">
          {record?.language_code || '-'}
        </Descriptions.Item>
        <Descriptions.Item label="Role">
          <TagField
            color={roleColors[record?.role || 'user']}
            value={record?.role?.toUpperCase()}
          />
        </Descriptions.Item>
        <Descriptions.Item label="Status">
          <TagField
            color={record?.is_banned ? 'red' : 'green'}
            value={record?.is_banned ? 'BANNED' : 'ACTIVE'}
          />
        </Descriptions.Item>
        <Descriptions.Item label="Ban Reason">
          {record?.ban_reason || '-'}
        </Descriptions.Item>
        <Descriptions.Item label="Registered">
          {record?.created_at ? dayjs(record.created_at).format('YYYY-MM-DD HH:mm:ss') : '-'}
        </Descriptions.Item>
        <Descriptions.Item label="Last Active">
          {record?.last_active_at ? dayjs(record.last_active_at).format('YYYY-MM-DD HH:mm:ss') : '-'}
        </Descriptions.Item>
      </Descriptions>

      <Card title="Actions" style={{ marginTop: 16 }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          {/* Role change */}
          <Space>
            <span>Change Role:</span>
            <Select
              style={{ width: 150 }}
              value={record?.role}
              onChange={handleRoleChange}
              disabled={record?.role === 'owner'}
              options={[
                { label: 'User', value: 'user' },
                { label: 'Moderator', value: 'moderator' },
                { label: 'Admin', value: 'admin' },
              ]}
            />
          </Space>

          {/* Ban/Unban */}
          {record?.is_banned ? (
            <Button
              type="primary"
              icon={<CheckOutlined />}
              onClick={handleUnban}
            >
              Unban User
            </Button>
          ) : (
            <Button
              danger
              icon={<StopOutlined />}
              onClick={() => setBanModalVisible(true)}
              disabled={record?.role === 'owner'}
            >
              Ban User
            </Button>
          )}
        </Space>
      </Card>

      {/* Stats Row */}
      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={8}>
          <Card>
            <Statistic
              title="Всего скачиваний"
              value={userStats?.total_downloads || 0}
              prefix={<DownloadOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col span={16}>
          <Card title="По платформам" loading={statsLoading}>
            {userStats?.platforms && userStats.platforms.length > 0 ? (
              <Space wrap>
                {userStats.platforms.map((p) => (
                  <TagField
                    key={p.name}
                    color={platformColors[p.name] || 'default'}
                    value={`${p.name}: ${p.count}`}
                  />
                ))}
              </Space>
            ) : (
              <span style={{ color: '#888' }}>Нет данных</span>
            )}
          </Card>
        </Col>
      </Row>

      {/* Recent Activity */}
      <Card title="Последняя активность" style={{ marginTop: 16 }} loading={statsLoading}>
        {userStats?.recent_activity && userStats.recent_activity.length > 0 ? (
          <Timeline
            items={userStats.recent_activity.map((log) => ({
              color: log.action === 'download_success' ? 'green' :
                     log.action === 'error' ? 'red' : 'blue',
              children: (
                <div>
                  <strong>{actionLabels[log.action] || log.action}</strong>
                  <span style={{ marginLeft: 8, color: '#888' }}>
                    {dayjs(log.created_at).format('DD.MM.YYYY HH:mm')}
                  </span>
                  {log.details && 'info' in log.details && (
                    <div style={{ fontSize: 12, color: '#aaa' }}>
                      {String(log.details.info)}
                    </div>
                  )}
                </div>
              ),
            }))}
          />
        ) : (
          <span style={{ color: '#888' }}>Нет активности</span>
        )}
      </Card>

      {/* Ban Modal */}
      <Modal
        title="Заблокировать пользователя"
        open={banModalVisible}
        onOk={handleBan}
        onCancel={() => setBanModalVisible(false)}
        okText="Заблокировать"
        okButtonProps={{ danger: true }}
      >
        <Input.TextArea
          placeholder="Причина блокировки (опционально)"
          value={banReason}
          onChange={(e) => setBanReason(e.target.value)}
          rows={3}
        />
      </Modal>
    </Show>
  );
};
