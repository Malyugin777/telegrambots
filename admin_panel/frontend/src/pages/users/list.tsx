import { List, useTable, ShowButton, TagField } from '@refinedev/antd';
import { Table, Space, Input, Select, Button, Switch, message } from 'antd';
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import { useUpdate } from '@refinedev/core';
import { useState } from 'react';
import dayjs from 'dayjs';

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
  last_active_at: string | null;
}

const roleColors: Record<string, string> = {
  user: 'default',
  moderator: 'blue',
  admin: 'purple',
  owner: 'gold',
};

export const UserList = () => {
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState<string | undefined>();
  const [bannedFilter, setBannedFilter] = useState<boolean | undefined>();

  const { tableProps, tableQueryResult } = useTable<User>({
    resource: 'users',
    syncWithLocation: true,
    filters: {
      permanent: [
        ...(search ? [{ field: 'search', operator: 'eq' as const, value: search }] : []),
        ...(roleFilter ? [{ field: 'role', operator: 'eq' as const, value: roleFilter }] : []),
        ...(bannedFilter !== undefined ? [{ field: 'is_banned', operator: 'eq' as const, value: bannedFilter }] : []),
      ],
    },
  });

  return (
    <List>
      <Space style={{ marginBottom: 16 }}>
        <Input
          placeholder="Search users..."
          prefix={<SearchOutlined />}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: 200 }}
          allowClear
        />
        <Select
          placeholder="Role"
          style={{ width: 130 }}
          allowClear
          value={roleFilter}
          onChange={setRoleFilter}
          options={[
            { label: 'User', value: 'user' },
            { label: 'Moderator', value: 'moderator' },
            { label: 'Admin', value: 'admin' },
            { label: 'Owner', value: 'owner' },
          ]}
        />
        <Select
          placeholder="Ban status"
          style={{ width: 130 }}
          allowClear
          value={bannedFilter}
          onChange={setBannedFilter}
          options={[
            { label: 'Banned', value: true },
            { label: 'Active', value: false },
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
        <Table.Column
          dataIndex="telegram_id"
          title="Telegram ID"
          render={(value) => <code>{value}</code>}
        />
        <Table.Column
          dataIndex="username"
          title="Username"
          render={(value) => (value ? `@${value}` : '-')}
        />
        <Table.Column
          title="Name"
          render={(_, record: User) =>
            [record.first_name, record.last_name].filter(Boolean).join(' ') || '-'
          }
        />
        <Table.Column
          dataIndex="role"
          title="Role"
          render={(value: string) => (
            <TagField color={roleColors[value] || 'default'} value={value.toUpperCase()} />
          )}
        />
        <Table.Column
          dataIndex="is_banned"
          title="Banned"
          render={(value: boolean) => (
            <TagField color={value ? 'red' : 'green'} value={value ? 'Yes' : 'No'} />
          )}
        />
        <Table.Column
          dataIndex="last_active_at"
          title="Last Active"
          render={(value) =>
            value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '-'
          }
        />
        <Table.Column
          title="Actions"
          render={(_, record: User) => (
            <Space>
              <ShowButton hideText size="small" recordItemId={record.id} />
            </Space>
          )}
        />
      </Table>
    </List>
  );
};
