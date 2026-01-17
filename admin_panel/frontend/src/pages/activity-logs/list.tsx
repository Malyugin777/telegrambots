import { List, useTable, TagField } from '@refinedev/antd';
import { Table, Space, Input, Select, Button, Tooltip } from 'antd';
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import { useCustom } from '@refinedev/core';
import { useState } from 'react';
import dayjs from 'dayjs';

interface Log {
  id: number;
  user_id: number | null;
  bot_id: number | null;
  action: string;
  details: Record<string, unknown> | null;
  created_at: string;
  username: string | null;
  bot_name: string | null;
}

interface Bot {
  id: number;
  name: string;
}

const actionColors: Record<string, string> = {
  download_video: 'green',
  download_audio: 'blue',
  start: 'purple',
  error: 'red',
};

export const LogList = () => {
  const [actionFilter, setActionFilter] = useState<string | undefined>();
  const [botFilter, setBotFilter] = useState<number | undefined>();
  const [daysFilter, setDaysFilter] = useState<number>(7);

  // Fetch bots for filter dropdown
  const { data: botsData } = useCustom<{ data: Bot[] }>({
    url: '/bots',
    method: 'get',
    config: {
      query: { page_size: 100 },
    },
  });

  // Fetch action types
  const { data: actionsData } = useCustom<{ actions: string[] }>({
    url: '/logs/actions',
    method: 'get',
  });

  const { tableProps, tableQueryResult } = useTable<Log>({
    resource: 'logs',
    syncWithLocation: true,
    filters: {
      permanent: [
        ...(actionFilter ? [{ field: 'action', operator: 'eq' as const, value: actionFilter }] : []),
        ...(botFilter ? [{ field: 'bot_id', operator: 'eq' as const, value: botFilter }] : []),
        { field: 'days', operator: 'eq' as const, value: daysFilter },
      ],
    },
    pagination: {
      pageSize: 50,
    },
  });

  const bots = botsData?.data?.data || [];
  const actions = actionsData?.data?.actions || [];

  return (
    <List>
      <Space style={{ marginBottom: 16 }} wrap>
        <Select
          placeholder="Bot"
          style={{ width: 150 }}
          allowClear
          value={botFilter}
          onChange={setBotFilter}
          options={bots.map((bot) => ({
            label: bot.name,
            value: bot.id,
          }))}
        />
        <Select
          placeholder="Action"
          style={{ width: 150 }}
          allowClear
          value={actionFilter}
          onChange={setActionFilter}
          options={actions.map((action) => ({
            label: action,
            value: action,
          }))}
        />
        <Select
          placeholder="Period"
          style={{ width: 120 }}
          value={daysFilter}
          onChange={setDaysFilter}
          options={[
            { label: 'Last 7 days', value: 7 },
            { label: 'Last 14 days', value: 14 },
            { label: 'Last 30 days', value: 30 },
            { label: 'Last 90 days', value: 90 },
          ]}
        />
        <Button
          icon={<ReloadOutlined />}
          onClick={() => tableQueryResult.refetch()}
        >
          Refresh
        </Button>
      </Space>

      <Table {...tableProps} rowKey="id" size="small">
        <Table.Column dataIndex="id" title="ID" width={80} />
        <Table.Column
          dataIndex="created_at"
          title="Time"
          width={160}
          render={(value) => dayjs(value).format('YYYY-MM-DD HH:mm:ss')}
        />
        <Table.Column
          dataIndex="action"
          title="Action"
          width={150}
          render={(value: string) => (
            <TagField
              color={actionColors[value] || 'default'}
              value={value}
            />
          )}
        />
        <Table.Column
          dataIndex="bot_name"
          title="Bot"
          width={120}
          render={(value) => value || '-'}
        />
        <Table.Column
          dataIndex="username"
          title="User"
          width={150}
          render={(value) => (value ? `@${value}` : '-')}
        />
        <Table.Column
          dataIndex="details"
          title="Details"
          render={(value: Record<string, unknown> | null) => {
            if (!value) return '-';
            // Show platform and title for downloads
            const parts = [];
            if (value.platform) parts.push(String(value.platform));
            if (value.title) parts.push(String(value.title).substring(0, 40) + '...');
            if (value.file_size) parts.push(`${Math.round(Number(value.file_size) / 1024 / 1024)}MB`);
            return parts.length > 0 ? (
              <Tooltip title={JSON.stringify(value, null, 2)}>
                <span>{parts.join(' | ')}</span>
              </Tooltip>
            ) : (
              <Tooltip title={JSON.stringify(value, null, 2)}>
                <span style={{ color: '#888' }}>...</span>
              </Tooltip>
            );
          }}
        />
      </Table>
    </List>
  );
};
