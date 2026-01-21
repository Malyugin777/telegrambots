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
  download_request: 'blue',
  download_success: 'green',
  audio_extracted: 'cyan',
  start: 'purple',
  help: 'orange',
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
          ellipsis
          render={(value: Record<string, unknown> | null) => {
            if (!value) return '-';

            // Parse our format: {"info": "platform:url"} or {"info": "type:platform"}
            if (value.info && typeof value.info === 'string') {
              const info = value.info;
              // Check if it's a URL (download_request)
              if (info.includes('http')) {
                const [platform, ...urlParts] = info.split(':');
                const url = urlParts.join(':'); // Reconstruct URL
                return (
                  <Tooltip title={url}>
                    <span>
                      <TagField color="blue" value={platform} style={{ marginRight: 4 }} />
                      <a href={url} target="_blank" rel="noopener noreferrer">
                        {url.substring(0, 35)}...
                      </a>
                    </span>
                  </Tooltip>
                );
              }
              // Otherwise it's type:platform (e.g., "video:instagram")
              return <span>{info}</span>;
            }

            // Fallback for other formats
            return (
              <Tooltip title={JSON.stringify(value, null, 2)}>
                <code style={{ fontSize: 11 }}>{JSON.stringify(value).substring(0, 50)}</code>
              </Tooltip>
            );
          }}
        />
      </Table>
    </List>
  );
};
