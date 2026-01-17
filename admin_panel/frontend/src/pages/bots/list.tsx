import {
  List,
  useTable,
  EditButton,
  ShowButton,
  DeleteButton,
  TagField,
} from '@refinedev/antd';
import { Table, Space, Input, Select, Button, Tooltip, message } from 'antd';
import {
  SearchOutlined,
  ReloadOutlined,
  EyeInvisibleOutlined,
} from '@ant-design/icons';
import { useCustom } from '@refinedev/core';
import { useState } from 'react';

interface Bot {
  id: number;
  name: string;
  bot_username: string | null;
  token_hash: string;
  webhook_url: string | null;
  status: 'active' | 'paused' | 'maintenance' | 'disabled';
  created_at: string;
  users_count: number;
  downloads_count: number;
}

const statusColors: Record<string, string> = {
  active: 'green',
  paused: 'orange',
  maintenance: 'blue',
  disabled: 'red',
};

export const BotList = () => {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | undefined>();

  const { tableProps, tableQueryResult } = useTable<Bot>({
    resource: 'bots',
    syncWithLocation: true,
    filters: {
      permanent: [
        ...(search ? [{ field: 'search', operator: 'eq' as const, value: search }] : []),
        ...(statusFilter ? [{ field: 'status_filter', operator: 'eq' as const, value: statusFilter }] : []),
      ],
    },
  });

  const handleRestart = async (id: number) => {
    try {
      // This would call the restart endpoint
      message.success('Bot restart initiated');
    } catch {
      message.error('Failed to restart bot');
    }
  };

  return (
    <List>
      {/* Filters */}
      <Space style={{ marginBottom: 16 }}>
        <Input
          placeholder="Search bots..."
          prefix={<SearchOutlined />}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: 200 }}
          allowClear
        />
        <Select
          placeholder="Status"
          style={{ width: 150 }}
          allowClear
          value={statusFilter}
          onChange={setStatusFilter}
          options={[
            { label: 'Active', value: 'active' },
            { label: 'Paused', value: 'paused' },
            { label: 'Maintenance', value: 'maintenance' },
            { label: 'Disabled', value: 'disabled' },
          ]}
        />
        <Button
          icon={<ReloadOutlined />}
          onClick={() => tableQueryResult.refetch()}
        >
          Refresh
        </Button>
      </Space>

      <Table {...tableProps} rowKey="id">
        <Table.Column dataIndex="id" title="ID" width={80} />
        <Table.Column dataIndex="name" title="Name" />
        <Table.Column
          dataIndex="bot_username"
          title="Username"
          render={(value) => (value ? `@${value}` : '-')}
        />
        <Table.Column
          dataIndex="status"
          title="Status"
          render={(value: string) => (
            <TagField color={statusColors[value] || 'default'} value={value.toUpperCase()} />
          )}
        />
        <Table.Column
          dataIndex="users_count"
          title="Users"
          render={(value: number) => (
            <span style={{ color: '#1890ff', fontWeight: 500 }}>{value || 0}</span>
          )}
        />
        <Table.Column
          dataIndex="downloads_count"
          title="Downloads"
          render={(value: number) => (
            <span style={{ color: '#52c41a', fontWeight: 500 }}>{value || 0}</span>
          )}
        />
        <Table.Column
          dataIndex="token_hash"
          title="Token"
          render={(value: string) => (
            <Tooltip title={value}>
              <Space>
                <EyeInvisibleOutlined />
                <span>{value.substring(0, 8)}...</span>
              </Space>
            </Tooltip>
          )}
        />
        <Table.Column
          title="Actions"
          render={(_, record: Bot) => (
            <Space>
              <ShowButton hideText size="small" recordItemId={record.id} />
              <EditButton hideText size="small" recordItemId={record.id} />
              <Tooltip title="Restart">
                <Button
                  size="small"
                  icon={<ReloadOutlined />}
                  onClick={() => handleRestart(record.id)}
                />
              </Tooltip>
              <DeleteButton hideText size="small" recordItemId={record.id} />
            </Space>
          )}
        />
      </Table>
    </List>
  );
};
