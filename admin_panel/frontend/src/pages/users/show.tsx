import { Show, TagField } from '@refinedev/antd';
import { useShow, useCustom } from '@refinedev/core';
import { Typography, Descriptions, Card, Space, Button, Select, Input, message, Modal } from 'antd';
import { StopOutlined, CheckOutlined } from '@ant-design/icons';
import { useState } from 'react';
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

export const UserShow = () => {
  const { queryResult } = useShow<User>();
  const { data, isLoading, refetch } = queryResult;
  const record = data?.data;

  const [banModalVisible, setBanModalVisible] = useState(false);
  const [banReason, setBanReason] = useState('');
  const [selectedRole, setSelectedRole] = useState<string | undefined>();

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

      {/* Ban Modal */}
      <Modal
        title="Ban User"
        open={banModalVisible}
        onOk={handleBan}
        onCancel={() => setBanModalVisible(false)}
        okText="Ban"
        okButtonProps={{ danger: true }}
      >
        <Input.TextArea
          placeholder="Ban reason (optional)"
          value={banReason}
          onChange={(e) => setBanReason(e.target.value)}
          rows={3}
        />
      </Modal>
    </Show>
  );
};
