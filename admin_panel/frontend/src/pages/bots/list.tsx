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
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

interface Bot {
  id: number;
  name: string;
  username: string | null;
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
  const { t } = useTranslation();
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
      message.success(t('bots.restartInitiated'));
    } catch {
      message.error(t('bots.restartFailed'));
    }
  };

  return (
    <List>
      {/* Filters */}
      <Space style={{ marginBottom: 16 }}>
        <Input
          placeholder={t('bots.searchBots')}
          prefix={<SearchOutlined />}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: 200 }}
          allowClear
        />
        <Select
          placeholder={t('common.status')}
          style={{ width: 150 }}
          allowClear
          value={statusFilter}
          onChange={setStatusFilter}
          options={[
            { label: t('bots.status.active'), value: 'active' },
            { label: t('bots.status.paused'), value: 'paused' },
            { label: t('bots.status.maintenance'), value: 'maintenance' },
            { label: t('bots.status.disabled'), value: 'disabled' },
          ]}
        />
        <Button
          icon={<ReloadOutlined />}
          onClick={() => tableQueryResult.refetch()}
        >
          {t('common.refresh')}
        </Button>
      </Space>

      <Table {...tableProps} rowKey="id">
        <Table.Column dataIndex="id" title={t('common.id')} width={80} />
        <Table.Column dataIndex="name" title={t('common.name')} />
        <Table.Column
          dataIndex="username"
          title={t('bots.botUsername')}
          render={(value) => (value ? `@${value}` : '-')}
        />
        <Table.Column
          dataIndex="status"
          title={t('common.status')}
          render={(value: string) => (
            <TagField color={statusColors[value] || 'default'} value={t(`bots.status.${value}`)} />
          )}
        />
        <Table.Column
          dataIndex="users_count"
          title={t('bots.usersCount')}
          render={(value: number) => (
            <span style={{ color: '#1890ff', fontWeight: 500 }}>{value || 0}</span>
          )}
        />
        <Table.Column
          dataIndex="downloads_count"
          title={t('bots.downloadsCount')}
          render={(value: number) => (
            <span style={{ color: '#52c41a', fontWeight: 500 }}>{value || 0}</span>
          )}
        />
        <Table.Column
          dataIndex="token_hash"
          title={t('bots.token')}
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
          title={t('common.actions')}
          render={(_, record: Bot) => (
            <Space>
              <ShowButton hideText size="small" recordItemId={record.id} />
              <EditButton hideText size="small" recordItemId={record.id} />
              <Tooltip title={t('bots.restart')}>
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
